"""
HybridStress Deterministic Validators
======================================

Three independent validators for determining branch outcomes
without any model-in-the-loop:

1. ADB State Query — queries actual app state via ADB commands
2. UI Hierarchy Check — parses UI XML dump for element existence/value
3. Screenshot OCR — extracts text from screenshots and matches predicates

Branch outcome = SUCCESS iff ALL postcondition predicates are satisfied
by at least one validator.
"""

from __future__ import annotations

import logging
import re
import subprocess
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple

from .data_types import Predicate, BranchOutcome

logger = logging.getLogger(__name__)


class Validator(ABC):
    """Base class for deterministic postcondition validators."""

    @abstractmethod
    def check_predicate(self, predicate: Predicate) -> bool:
        """Check if a single predicate is satisfied. Returns True if satisfied."""
        ...

    def check_all(self, predicates: List[Predicate]) -> Tuple[bool, List[bool]]:
        """
        Check all predicates. Returns (all_passed, per_predicate_results).
        """
        results = [self.check_predicate(p) for p in predicates]
        return all(results), results


class ADBValidator(Validator):
    """
    Validates postconditions by querying actual Android app state via ADB.

    Supports:
    - Activity/screen checks: "current_screen is X"
    - Content provider queries: "field value_is X"
    - Package/process checks: "app is_running"
    """

    def __init__(self, adb_serial: Optional[str] = None):
        self.adb_prefix = ["adb"]
        if adb_serial:
            self.adb_prefix = ["adb", "-s", adb_serial]

    def _run_adb(self, *args: str) -> str:
        """Run an ADB command and return stdout."""
        cmd = self.adb_prefix + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            logger.warning(f"ADB command failed: {cmd}, error: {e}")
            return ""

    def check_predicate(self, predicate: Predicate) -> bool:
        """Check predicate via ADB state queries."""
        subject = predicate.subject.lower()
        relation = predicate.relation.lower()
        obj = predicate.object.lower()

        if relation == "is" and subject == "current_screen":
            # Check current activity
            output = self._run_adb("shell", "dumpsys", "activity", "top")
            return obj in output.lower()

        elif relation == "is_running":
            # Check if app process is running
            output = self._run_adb("shell", "ps", "-A")
            return obj in output.lower()

        elif relation == "contains":
            # Generic content check — try dumpsys
            output = self._run_adb("shell", "dumpsys", "activity", "activities")
            return obj in output.lower()

        elif relation == "not_contains":
            output = self._run_adb("shell", "dumpsys", "activity", "activities")
            return obj not in output.lower()

        elif relation == "value_is":
            # Try content provider query
            output = self._run_adb(
                "shell", "content", "query",
                "--uri", f"content://{subject}",
            )
            return obj in output.lower()

        elif relation == "shows":
            # Check notifications or UI text
            output = self._run_adb("shell", "dumpsys", "notification")
            return obj in output.lower()

        else:
            logger.warning(f"Unknown relation for ADB validator: {relation}")
            return False


class UIHierarchyValidator(Validator):
    """
    Validates postconditions by parsing the UI hierarchy XML dump.

    This validator captures the UI layout via `adb shell uiautomator dump`
    and checks for element existence, text content, and properties.
    """

    def __init__(self, adb_serial: Optional[str] = None):
        self.adb_prefix = ["adb"]
        if adb_serial:
            self.adb_prefix = ["adb", "-s", adb_serial]
        self._cached_tree: Optional[ET.Element] = None

    def _dump_ui(self) -> Optional[ET.Element]:
        """Capture UI hierarchy XML."""
        try:
            # Dump UI hierarchy
            subprocess.run(
                self.adb_prefix + ["shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"],
                capture_output=True, text=True, timeout=15
            )
            # Pull the dump
            result = subprocess.run(
                self.adb_prefix + ["shell", "cat", "/sdcard/ui_dump.xml"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                root = ET.fromstring(result.stdout)
                self._cached_tree = root
                return root
        except Exception as e:
            logger.warning(f"UI dump failed: {e}")
        return None

    def _find_element(self, root: ET.Element, text: str) -> bool:
        """Search for an element containing the given text."""
        text_lower = text.lower()
        for elem in root.iter("node"):
            elem_text = (elem.get("text", "") or "").lower()
            elem_desc = (elem.get("content-desc", "") or "").lower()
            elem_id = (elem.get("resource-id", "") or "").lower()
            if text_lower in elem_text or text_lower in elem_desc or text_lower in elem_id:
                return True
        return False

    def check_predicate(self, predicate: Predicate) -> bool:
        """Check predicate against UI hierarchy."""
        root = self._cached_tree or self._dump_ui()
        if root is None:
            return False

        relation = predicate.relation.lower()
        obj = predicate.object

        if relation in ("contains", "shows", "value_is"):
            return self._find_element(root, obj)

        elif relation == "not_contains":
            return not self._find_element(root, obj)

        elif relation == "is":
            # Check if a specific screen/activity is visible
            return self._find_element(root, obj)

        else:
            logger.warning(f"Unknown relation for UI validator: {relation}")
            return False


class OCRValidator(Validator):
    """
    Validates postconditions by extracting text from screenshots via OCR.

    Uses either:
    - pytesseract (if available)
    - easyocr (fallback)
    - ADB screencap + dumpsys as last resort
    """

    def __init__(self, screenshot_path: Optional[str] = None):
        self.screenshot_path = screenshot_path
        self._cached_text: Optional[str] = None
        self._ocr_engine: Optional[str] = None
        self._init_ocr()

    def _init_ocr(self):
        """Detect available OCR engine."""
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
        logger.warning("No OCR engine found. OCR validator will be limited.")
        self._ocr_engine = None

    def _extract_text(self, image_path: str) -> str:
        """Extract text from image using available OCR engine."""
        if self._ocr_engine == "pytesseract":
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            return pytesseract.image_to_string(img)

        elif self._ocr_engine == "easyocr":
            import easyocr
            reader = easyocr.Reader(["en", "ch_sim"], gpu=True)
            results = reader.readtext(image_path)
            return " ".join([r[1] for r in results])

        else:
            # Fallback: return empty (validator will report False)
            return ""

    def set_screenshot(self, path: str):
        """Set screenshot path and invalidate cache."""
        self.screenshot_path = path
        self._cached_text = None

    def check_predicate(self, predicate: Predicate) -> bool:
        """Check if predicate object text appears in the screenshot."""
        if not self.screenshot_path or not Path(self.screenshot_path).exists():
            return False

        if self._cached_text is None:
            self._cached_text = self._extract_text(self.screenshot_path).lower()

        obj_lower = predicate.object.lower()
        relation = predicate.relation.lower()
        if relation == "not_contains":
            return obj_lower not in self._cached_text
        return obj_lower in self._cached_text


class CompositeValidator:
    """
    Composite validator that combines ADB, UI Hierarchy, and OCR validators.

    A predicate is satisfied if ANY of the three validators reports True.
    A branch succeeds if ALL predicates are satisfied.
    """

    def __init__(
        self,
        adb_serial: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ):
        self.adb_validator = ADBValidator(adb_serial=adb_serial)
        self.ui_validator = UIHierarchyValidator(adb_serial=adb_serial)
        self.ocr_validator = OCRValidator(screenshot_path=screenshot_path)
        self.validators = [self.adb_validator, self.ui_validator, self.ocr_validator]

    def validate_predicate(self, predicate: Predicate) -> Tuple[bool, dict]:
        """
        Check a single predicate against all validators.
        Returns (satisfied, per_validator_results).
        """
        results = {}
        for v in self.validators:
            name = v.__class__.__name__
            try:
                results[name] = v.check_predicate(predicate)
            except Exception as e:
                logger.warning(f"Validator {name} failed on {predicate}: {e}")
                results[name] = False

        satisfied = any(results.values())
        return satisfied, results

    def validate_all(self, predicates: List[Predicate]) -> Tuple[BranchOutcome, dict]:
        """
        Validate all postcondition predicates.

        Returns:
            (BranchOutcome.SUCCESS if all satisfied, detailed results dict)
        """
        all_results = {}
        all_passed = True

        for i, pred in enumerate(predicates):
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
        """Update OCR validator's screenshot path and invalidate UI cache."""
        self.ocr_validator.set_screenshot(path)
        self.ui_validator._cached_tree = None  # Force fresh UI dump on next check
