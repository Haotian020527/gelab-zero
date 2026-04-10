"""
Cross-Modal Verifier (CMV) — Reference Detector
=================================================

Two-tier architecture:
1. Teacher (Qwen2-VL-7B): VLM judge for soft KD labels
2. Student (CMV, 10M params): SigLIP ViT-B/16 (frozen) + MLP → binary classifier

Training: BCE (0.7) + KD (0.3) on deterministic benchmark labels.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CMV Student Model
# ---------------------------------------------------------------------------

class CMVModel(nn.Module):
    """
    Cross-Modal Verifier (CMV) — 10M parameter student model.

    Architecture:
    - Frozen SigLIP ViT-B/16 encoders for pre/post screenshots
    - Postcondition text encoder (lightweight embedding + projection)
    - MLP scorer → binary consistency output
    """

    def __init__(
        self,
        vision_dim: int = 768,      # SigLIP ViT-B/16 output dim
        text_dim: int = 256,         # Postcondition embedding dim
        hidden_dim: int = 512,
        num_mlp_layers: int = 3,
        dropout: float = 0.1,
    ):
        super().__init__()

        # Projection layers for vision features (pre + post screenshots)
        self.pre_proj = nn.Linear(vision_dim, hidden_dim)
        self.post_proj = nn.Linear(vision_dim, hidden_dim)

        # Postcondition text encoder
        self.text_embed = nn.Embedding(30000, text_dim)  # Simple token embedding
        self.text_proj = nn.Sequential(
            nn.Linear(text_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

        # MLP scorer
        mlp_input_dim = hidden_dim * 3  # pre + post + text
        layers = []
        in_dim = mlp_input_dim
        for i in range(num_mlp_layers - 1):
            out_dim = hidden_dim if i < num_mlp_layers - 2 else hidden_dim // 2
            layers.extend([
                nn.Linear(in_dim, out_dim),
                nn.LayerNorm(out_dim),
                nn.GELU(),
                nn.Dropout(dropout),
            ])
            in_dim = out_dim
        layers.append(nn.Linear(in_dim, 1))
        self.scorer = nn.Sequential(*layers)

        # Temperature for calibration
        self.temperature = nn.Parameter(torch.ones(1))

    def forward(
        self,
        pre_features: torch.Tensor,    # (B, vision_dim) — frozen SigLIP output
        post_features: torch.Tensor,   # (B, vision_dim)
        text_tokens: torch.Tensor,     # (B, max_len) — tokenized postconditions
        text_mask: Optional[torch.Tensor] = None,  # (B, max_len)
    ) -> torch.Tensor:
        """
        Returns RAW logits (B, 1). Temperature scaling is applied only
        in predict_proba() after post-hoc calibration — not during training.
        Positive = inconsistent (boundary failure detected).
        """
        # Project vision features
        pre_h = F.relu(self.pre_proj(pre_features))    # (B, hidden)
        post_h = F.relu(self.post_proj(post_features))  # (B, hidden)

        # Encode postconditions with proper masked mean pooling
        text_emb = self.text_embed(text_tokens)  # (B, L, text_dim)
        if text_mask is not None:
            text_emb = text_emb * text_mask.unsqueeze(-1)
            # Divide by number of valid tokens, not full sequence length
            valid_counts = text_mask.sum(dim=1, keepdim=True).clamp(min=1)  # (B, 1)
            text_pooled = text_emb.sum(dim=1) / valid_counts  # (B, text_dim)
        else:
            text_pooled = text_emb.mean(dim=1)  # (B, text_dim)
        text_h = self.text_proj(text_pooled)  # (B, hidden)

        # Concatenate and score
        combined = torch.cat([pre_h, post_h, text_h], dim=-1)  # (B, hidden*3)
        logits = self.scorer(combined)  # (B, 1)

        # NOTE: No temperature scaling here — raw logits returned.
        # Temperature is applied only in predict_proba() after post-hoc calibration.
        return logits

    def predict_proba(
        self,
        pre_features: torch.Tensor,
        post_features: torch.Tensor,
        text_tokens: torch.Tensor,
        text_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Return calibrated probability of inconsistency.
        Applies post-hoc temperature scaling to raw logits."""
        logits = self.forward(pre_features, post_features, text_tokens, text_mask)
        calibrated = logits / self.temperature
        return torch.sigmoid(calibrated)

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Vision Feature Extractor (frozen SigLIP)
# ---------------------------------------------------------------------------

class SigLIPFeatureExtractor:
    """
    Extract image features using a frozen SigLIP ViT-B/16 model.
    Features are cached to avoid redundant forward passes.
    """

    def __init__(self, model_name: str = "ViT-B-16-SigLIP", device: str = "cuda",
                 allow_dummy: bool = False):
        self.device = device
        self.model = None
        self.preprocess = None
        self.model_name = model_name
        self.allow_dummy = allow_dummy  # Only True for unit tests
        self._cache: Dict[str, torch.Tensor] = {}

    def load(self):
        """Lazy-load the SigLIP model."""
        if self.model is not None:
            return

        try:
            import open_clip
            model, _, preprocess = open_clip.create_model_and_transforms(
                self.model_name, pretrained="webli"
            )
            model = model.to(self.device).eval()
            for p in model.parameters():
                p.requires_grad = False
            self.model = model
            self.preprocess = preprocess
            logger.info(f"SigLIP model loaded: {self.model_name}")
        except ImportError:
            if not self.allow_dummy:
                raise RuntimeError(
                    "open_clip is required for SigLIP features. "
                    "Install: pip install open_clip_torch. "
                    "Set allow_dummy=True only for unit tests."
                )
            logger.warning("open_clip not installed. Using DUMMY features (test only).")
            self.model = None

    @torch.no_grad()
    def extract(self, image_path: str) -> torch.Tensor:
        """Extract features from a single image. Returns (vision_dim,)."""
        if image_path in self._cache:
            return self._cache[image_path]

        if self.model is None:
            self.load()

        if self.model is None:
            # Fallback: random features for testing
            features = torch.randn(768, device=self.device)
            self._cache[image_path] = features
            return features

        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        img_tensor = self.preprocess(img).unsqueeze(0).to(self.device)
        features = self.model.encode_image(img_tensor).squeeze(0)

        self._cache[image_path] = features
        return features

    def clear_cache(self):
        self._cache.clear()


# ---------------------------------------------------------------------------
# Postcondition Tokenizer
# ---------------------------------------------------------------------------

class PostconditionTokenizer:
    """
    Simple tokenizer for postcondition predicates.
    Converts (subject, relation, object) tuples to token sequences.
    """

    def __init__(self, max_len: int = 64):
        self.max_len = max_len
        self.vocab: Dict[str, int] = {"<pad>": 0, "<sep>": 1, "<unk>": 2}
        self._next_id = 3
        self._frozen = False  # When frozen, unseen tokens map to <unk>

    def build_vocab(self, all_predicates: list):
        """Build vocab from all training predicates. Call once before training."""
        for pred in all_predicates:
            for word in pred.subject.split():
                self._get_or_add(word.lower())
            for word in pred.relation.split():
                self._get_or_add(word.lower())
            for word in pred.object.split():
                self._get_or_add(word.lower())

    def freeze(self):
        """Freeze vocab so unseen tokens map to <unk>."""
        self._frozen = True

    def _get_or_add(self, token: str) -> int:
        """Add token to vocab. Only works when not frozen."""
        if token not in self.vocab:
            if self._frozen:
                return self.vocab.get("<unk>", 2)  # Map unseen to <unk>
            self.vocab[token] = self._next_id
            self._next_id += 1
        return self.vocab[token]

    def tokenize(self, predicates: list) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Tokenize a list of Predicate objects.
        Returns (tokens, mask) each of shape (max_len,).
        """
        tokens = []
        for pred in predicates:
            for word in pred.subject.split():
                tokens.append(self._get_or_add(word.lower()))
            tokens.append(self.vocab["<sep>"])
            for word in pred.relation.split():
                tokens.append(self._get_or_add(word.lower()))
            tokens.append(self.vocab["<sep>"])
            for word in pred.object.split():
                tokens.append(self._get_or_add(word.lower()))
            tokens.append(self.vocab["<sep>"])

        # Pad or truncate
        if len(tokens) > self.max_len:
            tokens = tokens[: self.max_len]
        mask = [1] * len(tokens)
        tokens += [0] * (self.max_len - len(tokens))
        mask += [0] * (self.max_len - len(mask))

        return torch.tensor(tokens, dtype=torch.long), torch.tensor(mask, dtype=torch.float)

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump({"vocab": self.vocab, "max_len": self.max_len}, f)

    @classmethod
    def load(cls, path: Path) -> PostconditionTokenizer:
        with open(path) as f:
            data = json.load(f)
        tok = cls(max_len=data["max_len"])
        tok.vocab = data["vocab"]
        tok._next_id = max(data["vocab"].values()) + 1
        return tok


# ---------------------------------------------------------------------------
# Baseline Detectors
# ---------------------------------------------------------------------------

class FixedDelayBaseline:
    """
    Baseline: re-capture screenshot after a fixed delay.
    If the screenshot changes significantly → flag as inconsistent.
    """

    def __init__(self, delay_ms: int = 2000, threshold: float = 0.1):
        self.delay_ms = delay_ms
        self.threshold = threshold

    def predict(self, pre_screenshot: str, post_screenshot: str) -> float:
        """Returns probability of inconsistency (0-1)."""
        try:
            from PIL import Image
            import numpy as np
            pre = np.array(Image.open(pre_screenshot).convert("RGB"))
            post = np.array(Image.open(post_screenshot).convert("RGB"))
            diff = np.abs(pre.astype(float) - post.astype(float)).mean() / 255.0
            return float(diff > self.threshold)
        except Exception:
            return 0.5


class APIStatusBaseline:
    """
    Baseline: naive check based on API response status.
    If API reports success → consistent; otherwise → inconsistent.
    """

    def predict(self, api_response: Dict) -> float:
        """Returns probability of inconsistency (0-1)."""
        status = api_response.get("status", "unknown")
        if status == "success":
            return 0.0
        elif status in ("error", "failed"):
            return 1.0
        return 0.5
