"""
Cockpit Deterministic Validators
==================================

Replaces ADB + UI Hierarchy + OCR validators with:
1. CockpitAPIValidator — queries the cockpit /state endpoint (replaces ADB)
2. CockpitScreenshotValidator — OCR on Playwright screenshots (replaces UIHierarchy+OCR)
3. CockpitCompositeValidator — combines both

The validators implement the same interface as hybridstress.validators
so they can be used as drop-in replacements.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from hybridstress.data_types import BranchOutcome, Predicate

logger = logging.getLogger(__name__)


class CockpitAPIValidator:
    """
    Validates postconditions by querying the cockpit REST API state.
    Replaces ADBValidator — no physical device needed.
    """

    def __init__(self, cockpit_url: str = "http://localhost:8420"):
        self.cockpit_url = cockpit_url.rstrip("/")
        self._cached_state: Optional[Dict] = None

    def _fetch_state(self) -> Dict:
        """Fetch the full cockpit state."""
        try:
            resp = requests.get(f"{self.cockpit_url}/state", timeout=5)
            resp.raise_for_status()
            self._cached_state = resp.json()
            return self._cached_state
        except Exception as e:
            logger.warning(f"Failed to fetch cockpit state: {e}")
            return {}

    def invalidate_cache(self):
        self._cached_state = None

    def check_predicate(self, predicate: Predicate) -> bool:
        """Check a postcondition predicate against the cockpit API state.

        Subject-aware: resolves predicate.subject to the specific state field
        first, then applies the relation only on that field's value.
        """
        state = self._cached_state or self._fetch_state()
        if not state:
            return False

        subject = predicate.subject.lower()
        relation = predicate.relation.lower()
        obj = predicate.object
        obj_lower = obj.lower()

        # Resolve subject → actual field value
        field_value = self._resolve_field(state, subject)

        if relation == "is":
            if subject == "current_screen":
                for app_name, app_state in state.items():
                    if isinstance(app_state, dict) and app_state.get("current_screen") == obj:
                        return True
                return False
            if field_value is None:
                return False
            return str(field_value).lower() == obj_lower

        elif relation == "value_is":
            if field_value is None:
                return False
            return str(field_value).lower() == obj_lower

        elif relation == "contains":
            if field_value is None:
                return False
            field_text = json.dumps(field_value, ensure_ascii=False).lower()
            return obj_lower in field_text

        elif relation == "not_contains":
            if field_value is None:
                # Field doesn't exist → trivially does not contain
                return True
            field_text = json.dumps(field_value, ensure_ascii=False).lower()
            return obj_lower not in field_text

        elif relation == "shows":
            # Global UI check — searches entire state
            state_text = json.dumps(state, ensure_ascii=False).lower()
            return obj_lower in state_text

        else:
            logger.warning(f"Unknown relation for CockpitAPIValidator: {relation}")
            return False

    def _resolve_field(self, state: Dict, field_name: str) -> Optional[object]:
        """Resolve a field name to its value in the cockpit state.

        Search order:
        1. Top-level state key
        2. Direct field in each app subsystem
        3. Not found → None
        """
        # 1. Top-level (e.g., 'active_app')
        if field_name in state:
            return state[field_name]

        # 2. Search app subsystems
        for app_name, app_state in state.items():
            if isinstance(app_state, dict) and field_name in app_state:
                return app_state[field_name]

        return None


class CockpitScreenshotValidator:
    """
    Validates postconditions by extracting text from cockpit screenshots via OCR.
    Replaces the OCR-on-ADB-screenshot approach.
    """

    def __init__(self, screenshot_path: Optional[str] = None):
        self.screenshot_path = screenshot_path
        self._cached_text: Optional[str] = None
        self._ocr_engine: Optional[str] = None
        self._init_ocr()

    def _init_ocr(self):
        try:
            import pytesseract
            self._ocr_engine = "pytesseract"
            return
        except ImportError:
            pass
        try:
            import easyocr
            self._ocr_engine = "easyocr"
            return
        except ImportError:
            pass
        logger.warning("No OCR engine found. Screenshot validator will be limited.")

    def _extract_text(self, image_path: str) -> str:
        if self._ocr_engine == "pytesseract":
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            return pytesseract.image_to_string(img, lang="chi_sim+eng")
        elif self._ocr_engine == "easyocr":
            import easyocr
            reader = easyocr.Reader(["en", "ch_sim"], gpu=True)
            results = reader.readtext(image_path)
            return " ".join([r[1] for r in results])
        return ""

    def set_screenshot(self, path: str):
        self.screenshot_path = path
        self._cached_text = None

    def check_predicate(self, predicate: Predicate) -> bool:
        if not self.screenshot_path or not Path(self.screenshot_path).exists():
            return False
        if self._cached_text is None:
            self._cached_text = self._extract_text(self.screenshot_path).lower()
        obj_lower = predicate.object.lower()
        relation = predicate.relation.lower()
        if relation == "not_contains":
            return obj_lower not in self._cached_text
        return obj_lower in self._cached_text


class CockpitCompositeValidator:
    """
    Composite validator combining API state checking and OCR screenshot checking.
    Drop-in replacement for hybridstress.validators.CompositeValidator.
    """

    def __init__(
        self,
        cockpit_url: str = "http://localhost:8420",
        screenshot_path: Optional[str] = None,
    ):
        self.api_validator = CockpitAPIValidator(cockpit_url)
        self.screenshot_validator = CockpitScreenshotValidator(screenshot_path)

    def validate_predicate(self, predicate: Predicate) -> Tuple[bool, dict]:
        results = {}
        for name, validator in [
            ("CockpitAPIValidator", self.api_validator),
            ("CockpitScreenshotValidator", self.screenshot_validator),
        ]:
            try:
                results[name] = validator.check_predicate(predicate)
            except Exception as e:
                logger.warning(f"Validator {name} failed on {predicate}: {e}")
                results[name] = False
        satisfied = any(results.values())
        return satisfied, results

    def validate_all(self, predicates: List[Predicate]) -> Tuple[BranchOutcome, dict]:
        all_results = {}
        all_passed = True
        for pred in predicates:
            satisfied, per_validator = self.validate_predicate(pred)
            all_results[str(pred)] = {
                "satisfied": satisfied,
                "validators": per_validator,
            }
            if not satisfied:
                all_passed = False
                logger.info(f"Predicate FAILED: {pred} — {per_validator}")
        outcome = BranchOutcome.SUCCESS if all_passed else BranchOutcome.FAILURE
        return outcome, all_results

    def set_screenshot(self, path: str):
        """Update screenshot path and invalidate caches."""
        self.screenshot_validator.set_screenshot(path)
        self.api_validator.invalidate_cache()
