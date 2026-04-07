"""
CMV Training Pipeline
======================

Trains the Cross-Modal Verifier using:
- Primary loss: BCE (weight 0.7) on deterministic benchmark labels
- Auxiliary loss: KD (weight 0.3) between CMV logits and VLM soft predictions
- Temperature calibration on validation fold

Usage:
    python -m hybridstress.cmv_trainer \
        --data_dir benchmark_data/events/ \
        --output_dir models/cmv/ \
        --epochs 50 --lr 1e-4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset, random_split

from .cmv_model import CMVModel, PostconditionTokenizer, SigLIPFeatureExtractor
from .data_types import SwitchEvent, SwitchLabel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class HybridStressDataset(Dataset):
    """
    PyTorch Dataset for HybridStress switch events.

    Each sample contains:
    - pre_features: SigLIP features of pre-switch screenshot
    - post_features: SigLIP features of post-switch screenshot
    - text_tokens: tokenized postconditions
    - text_mask: attention mask for postconditions
    - label: 1 if boundary_specific (inconsistent), 0 otherwise
    - vlm_score: VLM teacher's soft prediction (for KD)
    """

    def __init__(
        self,
        events: List[SwitchEvent],
        feature_extractor: SigLIPFeatureExtractor,
        tokenizer: PostconditionTokenizer,
        vlm_scores: Optional[Dict[str, float]] = None,
    ):
        self.events = events
        self.feature_extractor = feature_extractor
        self.tokenizer = tokenizer
        self.vlm_scores = vlm_scores or {}

    def __len__(self) -> int:
        return len(self.events)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        event = self.events[idx]

        # Extract vision features
        pre_feat = self.feature_extractor.extract(event.pre_screenshot_path)
        post_feat = self.feature_extractor.extract(event.post_screenshot_path)

        # Tokenize postconditions
        text_tokens, text_mask = self.tokenizer.tokenize(event.postconditions)

        # Binary label: 1 = boundary-specific inconsistency, 0 = not boundary-specific.
        # Per proposal, CMV detects BOUNDARY_SPECIFIC failures specifically,
        # NOT any failure. Ground truth from deterministic validators ONLY.
        # Events with PARTIAL_FAIL (infrastructure errors) are excluded upstream.
        label = 1.0 if event.label == SwitchLabel.BOUNDARY_SPECIFIC else 0.0

        # VLM teacher score (for KD loss)
        vlm_score = self.vlm_scores.get(event.event_id, label)  # fall back to hard label

        return {
            "pre_features": pre_feat,
            "post_features": post_feat,
            "text_tokens": text_tokens,
            "text_mask": text_mask,
            "label": torch.tensor(label, dtype=torch.float),
            "vlm_score": torch.tensor(vlm_score, dtype=torch.float),
            "event_id": event.event_id,
        }


# ---------------------------------------------------------------------------
# Loss Functions
# ---------------------------------------------------------------------------

class CMVLoss(nn.Module):
    """
    Combined loss: BCE (weight α) + KD (weight 1-α).

    BCE: ground truth from deterministic validators
    KD: soft labels from VLM teacher (Qwen2-VL-7B)
    """

    def __init__(self, alpha: float = 0.7, temperature: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.temperature = temperature

    def forward(
        self,
        logits: torch.Tensor,      # (B, 1) — CMV raw logits
        labels: torch.Tensor,      # (B,) — deterministic ground truth
        vlm_scores: torch.Tensor,  # (B,) — VLM soft predictions
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """Returns (total_loss, loss_components_dict)."""
        logits = logits.squeeze(-1)

        # BCE loss on deterministic labels
        bce = F.binary_cross_entropy_with_logits(logits, labels)

        # KD loss: match CMV's sigmoid output to VLM's soft prediction
        cmv_prob = torch.sigmoid(logits / self.temperature)
        vlm_prob = vlm_scores.clamp(1e-7, 1.0 - 1e-7)
        kd = F.binary_cross_entropy(cmv_prob, vlm_prob)

        total = self.alpha * bce + (1 - self.alpha) * kd

        return total, {
            "bce": bce.item(),
            "kd": kd.item(),
            "total": total.item(),
        }


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class CMVTrainer:
    """
    Training loop for the CMV student model.

    Protocol:
    1. Load events and split 80/20 (stratified by task + fault type)
    2. Train for N epochs with BCE + KD
    3. Temperature calibration on validation fold
    4. Save best model by validation AUPRC
    """

    def __init__(
        self,
        model: CMVModel,
        train_dataset: HybridStressDataset,
        val_dataset: HybridStressDataset,
        output_dir: Path,
        lr: float = 1e-4,
        batch_size: int = 32,
        epochs: int = 50,
        alpha: float = 0.7,
        device: str = "cuda",
    ):
        self.model = model.to(device)
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.output_dir = output_dir
        self.device = device
        self.epochs = epochs

        # Exclude temperature from AdamW — it's calibrated post-hoc
        train_params = [p for n, p in model.named_parameters()
                        if p.requires_grad and "temperature" not in n]
        self.optimizer = torch.optim.AdamW(train_params, lr=lr, weight_decay=1e-4)
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=epochs
        )
        self.criterion = CMVLoss(alpha=alpha)

        # num_workers=0: feature extraction uses CUDA and tokenizer is stateful
        self.train_loader = DataLoader(
            train_dataset, batch_size=batch_size, shuffle=True, num_workers=0
        )
        self.val_loader = DataLoader(
            val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
        )

        self.best_auprc = 0.0
        self.history: List[Dict] = []

    def train(self) -> Dict:
        """Run full training loop. Returns final metrics."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Training CMV: {self.model.count_parameters():,} parameters")
        logger.info(f"Train: {len(self.train_dataset)}, Val: {len(self.val_dataset)}")

        for epoch in range(self.epochs):
            train_metrics = self._train_epoch(epoch)
            val_metrics = self._eval_epoch(epoch)

            self.scheduler.step()

            metrics = {
                "epoch": epoch,
                "train": train_metrics,
                "val": val_metrics,
                "lr": self.scheduler.get_last_lr()[0],
            }
            self.history.append(metrics)

            # Save best model
            if val_metrics["auprc"] > self.best_auprc:
                self.best_auprc = val_metrics["auprc"]
                self._save_checkpoint("best.pt", metrics)

            if (epoch + 1) % 10 == 0:
                logger.info(
                    f"Epoch {epoch+1}/{self.epochs}: "
                    f"train_loss={train_metrics['loss']:.4f}, "
                    f"val_auprc={val_metrics['auprc']:.4f}, "
                    f"val_auroc={val_metrics['auroc']:.4f}"
                )

        # Reload best checkpoint before calibration so we calibrate the best model
        best_path = self.output_dir / "best.pt"
        if best_path.exists():
            best_ckpt = torch.load(best_path, map_location=self.device, weights_only=False)
            self.model.load_state_dict(best_ckpt["model_state_dict"])
            logger.info("Reloaded best checkpoint for temperature calibration")

        # Calibrate temperature on best model
        self._calibrate_temperature()

        # Save calibrated best model (overwrites uncalibrated best.pt)
        self._save_checkpoint("best.pt", self.history[-1])

        # Save final model (calibrated)
        self._save_checkpoint("final.pt", self.history[-1])

        # Save training history
        with open(self.output_dir / "training_history.json", "w") as f:
            json.dump(self.history, f, indent=2)

        final_metrics = {
            "best_auprc": self.best_auprc,
            "final_epoch": self.epochs,
            "parameters": self.model.count_parameters(),
        }
        logger.info(f"Training complete. Best AUPRC: {self.best_auprc:.4f}")
        return final_metrics

    def _train_epoch(self, epoch: int) -> Dict[str, float]:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0
        n_batches = 0

        for batch in self.train_loader:
            pre_feat = batch["pre_features"].to(self.device)
            post_feat = batch["post_features"].to(self.device)
            text_tok = batch["text_tokens"].to(self.device)
            text_mask = batch["text_mask"].to(self.device)
            labels = batch["label"].to(self.device)
            vlm_scores = batch["vlm_score"].to(self.device)

            logits = self.model(pre_feat, post_feat, text_tok, text_mask)
            loss, components = self.criterion(logits, labels, vlm_scores)

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()

            total_loss += components["total"]
            n_batches += 1

        return {"loss": total_loss / max(n_batches, 1)}

    @torch.no_grad()
    def _eval_epoch(self, epoch: int) -> Dict[str, float]:
        """Evaluate on validation set."""
        self.model.eval()
        all_logits = []
        all_labels = []

        for batch in self.val_loader:
            pre_feat = batch["pre_features"].to(self.device)
            post_feat = batch["post_features"].to(self.device)
            text_tok = batch["text_tokens"].to(self.device)
            text_mask = batch["text_mask"].to(self.device)
            labels = batch["label"]

            logits = self.model(pre_feat, post_feat, text_tok, text_mask)
            all_logits.append(logits.cpu().squeeze(-1))
            all_labels.append(labels)

        logits = torch.cat(all_logits)
        labels = torch.cat(all_labels)
        probs = torch.sigmoid(logits)

        metrics = compute_binary_metrics(probs.numpy(), labels.numpy())
        return metrics

    def _calibrate_temperature(self):
        """
        Post-hoc temperature calibration on validation set (Platt scaling).
        forward() returns raw logits, so we optimize temperature directly.
        """
        self.model.eval()
        all_logits = []
        all_labels = []

        with torch.no_grad():
            for batch in self.val_loader:
                pre_feat = batch["pre_features"].to(self.device)
                post_feat = batch["post_features"].to(self.device)
                text_tok = batch["text_tokens"].to(self.device)
                text_mask = batch["text_mask"].to(self.device)
                labels = batch["label"]

                logits = self.model(pre_feat, post_feat, text_tok, text_mask)
                all_logits.append(logits.cpu().squeeze(-1))
                all_labels.append(labels)

        logits = torch.cat(all_logits)
        labels = torch.cat(all_labels)

        # Optimize log_temperature (ensures temperature > 0)
        log_temp = nn.Parameter(torch.zeros(1))
        optimizer = torch.optim.LBFGS([log_temp], lr=0.01, max_iter=50)

        def closure():
            optimizer.zero_grad()
            temp = log_temp.exp()
            loss = F.binary_cross_entropy_with_logits(logits / temp, labels)
            loss.backward()
            return loss

        optimizer.step(closure)

        final_temp = log_temp.exp().item()
        self.model.temperature.data = torch.tensor([final_temp]).to(self.device)
        logger.info(f"Calibrated temperature: {final_temp:.4f}")

    def _save_checkpoint(self, name: str, metrics: Dict):
        """Save model checkpoint."""
        path = self.output_dir / name
        torch.save({
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "metrics": metrics,
        }, path)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_binary_metrics(probs, labels) -> Dict[str, float]:
    """Compute AUPRC, AUROC, ECE, Brier score, false alarm rate."""
    import numpy as np

    probs = np.asarray(probs)
    labels = np.asarray(labels)

    metrics = {}

    try:
        from sklearn.metrics import (
            average_precision_score,
            roc_auc_score,
        )
        metrics["auprc"] = float(average_precision_score(labels, probs))
        metrics["auroc"] = float(roc_auc_score(labels, probs))
    except (ImportError, ValueError) as e:
        logger.warning(f"sklearn metrics failed: {e}")
        metrics["auprc"] = 0.0
        metrics["auroc"] = 0.0

    # Brier score
    metrics["brier"] = float(np.mean((probs - labels) ** 2))

    # ECE (Expected Calibration Error) — 10 bins
    n_bins = 10
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (probs >= lo) & (probs <= hi if i == n_bins - 1 else probs < hi)
        if mask.sum() > 0:
            bin_acc = labels[mask].mean()
            bin_conf = probs[mask].mean()
            ece += mask.sum() / len(probs) * abs(bin_acc - bin_conf)
    metrics["ece"] = float(ece)

    # False alarm rate at threshold 0.5
    preds = (probs >= 0.5).astype(float)
    negatives = (labels == 0)
    if negatives.sum() > 0:
        metrics["false_alarm_rate"] = float(preds[negatives].mean())
    else:
        metrics["false_alarm_rate"] = 0.0

    return metrics


# ---------------------------------------------------------------------------
# Data loading utilities
# ---------------------------------------------------------------------------

def load_events_from_dir(events_dir: Path) -> List[SwitchEvent]:
    """Load all SwitchEvent JSON files from a directory."""
    events = []
    for p in sorted(events_dir.glob("*.json")):
        try:
            events.append(SwitchEvent.load(p))
        except Exception as e:
            logger.warning(f"Failed to load {p}: {e}")
    return events


def load_vlm_scores(vlm_scores_path: Path) -> Dict[str, float]:
    """Load VLM teacher soft predictions."""
    if not vlm_scores_path.exists():
        return {}
    with open(vlm_scores_path) as f:
        return json.load(f)


def stratified_split(
    events: List[SwitchEvent],
    val_ratio: float = 0.2,
    seed: int = 42,
) -> Tuple[List[SwitchEvent], List[SwitchEvent]]:
    """
    Split events into train/val by **task_id groups** (not per-event),
    preserving approximate positive-class rate (BOUNDARY_SPECIFIC prevalence).

    All events from a given task go entirely to train or val, preventing
    correlated event leakage. Tasks are sorted by positive rate, then
    allocated round-robin to ensure balanced class distribution.
    """
    import random
    rng = random.Random(seed)

    # Group all events by task_id
    task_groups: Dict[str, List[SwitchEvent]] = {}
    for e in events:
        task_groups.setdefault(e.task_id, []).append(e)

    # Compute positive rate per task for stratification
    task_ids = sorted(task_groups.keys())
    rng.shuffle(task_ids)

    def pos_rate(tid):
        group = task_groups[tid]
        n_pos = sum(1 for e in group if e.label == SwitchLabel.BOUNDARY_SPECIFIC)
        return n_pos / max(len(group), 1)

    # Sort tasks by positive rate (alternating high/low ensures balance)
    task_ids_sorted = sorted(task_ids, key=pos_rate)

    n_total = len(events)
    n_val_target = int(n_total * val_ratio)

    val_events = []
    train_events = []
    val_count = 0

    # Alternate allocation: every Nth task goes to val to preserve distribution
    n_tasks = len(task_ids_sorted)
    n_val_tasks = max(1, int(n_tasks * val_ratio))
    # Pick every k-th task for val (spread across positive-rate spectrum)
    step = max(1, n_tasks // n_val_tasks)
    val_task_indices = set(range(0, n_tasks, step))

    for idx, tid in enumerate(task_ids_sorted):
        group = task_groups[tid]
        if idx in val_task_indices and val_count < n_val_target * 1.5:
            val_events.extend(group)
            val_count += len(group)
        else:
            train_events.extend(group)

    # Ensure at least 1 task in val
    if not val_events and train_events:
        last_tid = train_events[-1].task_id
        val_events = [e for e in train_events if e.task_id == last_tid]
        train_events = [e for e in train_events if e.task_id != last_tid]

    return train_events, val_events


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CMV Training Pipeline")
    parser.add_argument("--data_dir", type=str, required=True,
                        help="Directory containing switch event JSON files")
    parser.add_argument("--vlm_scores", type=str, default=None,
                        help="Path to VLM teacher scores JSON")
    parser.add_argument("--output_dir", type=str, default="models/cmv",
                        help="Output directory for model checkpoints")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--alpha", type=float, default=0.7,
                        help="BCE weight (1-alpha = KD weight)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="cuda")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # Full reproducibility seeding
    import random, numpy as np
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    # Load data
    events_dir = Path(args.data_dir)
    events = load_events_from_dir(events_dir)
    # Exclude PARTIAL_FAIL events (infrastructure errors — unreliable labels)
    events = [e for e in events if e.label != SwitchLabel.PARTIAL_FAIL]
    logger.info(f"Loaded {len(events)} valid events from {events_dir}")

    vlm_scores = {}
    if args.vlm_scores:
        vlm_scores = load_vlm_scores(Path(args.vlm_scores))
        logger.info(f"Loaded {len(vlm_scores)} VLM scores")

    # Split data
    train_events, val_events = stratified_split(events)
    logger.info(f"Train: {len(train_events)}, Val: {len(val_events)}")

    # Initialize components
    feature_extractor = SigLIPFeatureExtractor(device=args.device)

    # Build tokenizer vocab on training split ONLY, then freeze
    tokenizer = PostconditionTokenizer()
    all_train_preds = [p for e in train_events for p in e.postconditions]
    tokenizer.build_vocab(all_train_preds)
    tokenizer.freeze()
    logger.info(f"Tokenizer vocab size: {len(tokenizer.vocab)}")

    train_dataset = HybridStressDataset(
        train_events, feature_extractor, tokenizer, vlm_scores
    )
    val_dataset = HybridStressDataset(
        val_events, feature_extractor, tokenizer, vlm_scores
    )

    model = CMVModel()
    logger.info(f"CMV parameters: {model.count_parameters():,}")

    # Train
    output_dir = Path(args.output_dir)
    trainer = CMVTrainer(
        model=model,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        output_dir=output_dir,
        lr=args.lr,
        batch_size=args.batch_size,
        epochs=args.epochs,
        alpha=args.alpha,
        device=args.device,
    )
    final_metrics = trainer.train()

    # Save tokenizer
    tokenizer.save(output_dir / "tokenizer.json")

    # Save final metrics
    with open(output_dir / "final_metrics.json", "w") as f:
        json.dump(final_metrics, f, indent=2)

    logger.info("Training pipeline complete.")


if __name__ == "__main__":
    main()
