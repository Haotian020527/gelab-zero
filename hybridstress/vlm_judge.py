"""
VLM Judge — Qwen2-VL-7B Teacher for CMV Knowledge Distillation
================================================================

The VLM judge serves two purposes:
1. Provides soft labels for KD training of CMV student
2. Acts as an evaluation BASELINE (upper bound) — NOT ground truth

Ground truth is ALWAYS from deterministic validators (ADB, UI XML, OCR).
The VLM NEVER generates benchmark labels.

Usage:
    python -m hybridstress.vlm_judge \
        --events_dir benchmark_data/events/ \
        --output vlm_scores.json \
        --model Qwen/Qwen2-VL-7B-Instruct
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VLM Judge
# ---------------------------------------------------------------------------

class VLMJudge:
    """
    Qwen2-VL-7B teacher: given (pre_screenshot, post_screenshot, postconditions),
    outputs a consistency score [0, 1].

    Architecture: Uses Qwen2-VL via transformers pipeline or API.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2-VL-7B-Instruct",
        device: str = "cuda",
    ):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.processor = None

    def load(self):
        """Lazy-load the VLM model."""
        if self.model is not None:
            return

        try:
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            import torch

            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16,
                device_map="auto",
            )
            logger.info(f"VLM loaded: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load VLM: {e}")
            raise

    def judge(
        self,
        pre_screenshot_path: str,
        post_screenshot_path: str,
        postconditions: list,
        action: str = "",
    ) -> float:
        """
        Judge whether a modality switch resulted in consistent state.

        Returns:
            float: Probability of inconsistency (0 = consistent, 1 = inconsistent)
        """
        self.load()

        # Build structured prompt
        postcond_str = "\n".join(
            f"- ({p.subject} {p.relation} {p.object})"
            for p in postconditions
        )

        prompt = f"""You are evaluating whether a GUI agent's modality switch (API ↔ GUI) produced a consistent application state.

## Context
- **Action performed**: {action}
- **Expected postconditions** (structured predicates):
{postcond_str}

## Task
Compare the pre-switch and post-switch screenshots. Determine if the postconditions are satisfied in the post-switch state.

Answer with a single JSON object:
{{"consistent": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}

Only answer with the JSON, nothing else."""

        try:
            # Build message with images
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Pre-switch screenshot:"},
                        {"type": "image", "image": f"file://{pre_screenshot_path}"},
                        {"type": "text", "text": "Post-switch screenshot:"},
                        {"type": "image", "image": f"file://{post_screenshot_path}"},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]

            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            from qwen_vl_utils import process_vision_info
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            ).to(self.device)

            import torch
            with torch.no_grad():
                output_ids = self.model.generate(**inputs, max_new_tokens=256)
            output_text = self.processor.batch_decode(
                output_ids[:, inputs.input_ids.shape[1]:],
                skip_special_tokens=True,
            )[0]

            # Parse response
            return self._parse_response(output_text)

        except Exception as e:
            logger.error(f"VLM inference failed: {e}")
            return 0.5  # Uncertain

    def _parse_response(self, text: str) -> float:
        """Parse VLM response to extract inconsistency probability."""
        try:
            # Try to extract JSON
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)
            consistent = data.get("consistent", True)
            confidence = data.get("confidence", 0.8)

            if consistent:
                return 1.0 - confidence  # Low probability of inconsistency
            else:
                return confidence  # High probability of inconsistency

        except (json.JSONDecodeError, KeyError):
            # Fallback: look for keywords
            text_lower = text.lower()
            if "inconsistent" in text_lower or "not consistent" in text_lower:
                return 0.8
            elif "consistent" in text_lower:
                return 0.2
            return 0.5

    def batch_judge(
        self,
        events: list,
        batch_size: int = 4,
    ) -> Dict[str, float]:
        """
        Judge a batch of switch events.
        Returns {event_id: inconsistency_probability}.
        """
        scores = {}
        for i, event in enumerate(events):
            try:
                score = self.judge(
                    pre_screenshot_path=event.pre_screenshot_path,
                    post_screenshot_path=event.post_screenshot_path,
                    postconditions=event.postconditions,
                    action=event.action,
                )
                scores[event.event_id] = score
                if (i + 1) % 10 == 0:
                    logger.info(f"VLM judged {i+1}/{len(events)} events")
            except Exception as e:
                logger.warning(f"Event {event.event_id} failed: {e}")
                scores[event.event_id] = 0.5

        return scores


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VLM Judge — Qwen2-VL-7B Teacher")
    parser.add_argument("--events_dir", type=str, required=True,
                        help="Directory with switch event JSONs")
    parser.add_argument("--output", type=str, default="vlm_scores.json",
                        help="Output path for VLM scores")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2-VL-7B-Instruct")
    parser.add_argument("--device", type=str, default="cuda")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    from .cmv_trainer import load_events_from_dir
    events = load_events_from_dir(Path(args.events_dir))
    logger.info(f"Loaded {len(events)} events")

    judge = VLMJudge(model_name=args.model, device=args.device)
    scores = judge.batch_judge(events)

    with open(args.output, "w") as f:
        json.dump(scores, f, indent=2)

    logger.info(f"VLM scores saved to {args.output}")
    logger.info(f"Mean score: {sum(scores.values()) / len(scores):.4f}")


if __name__ == "__main__":
    main()
