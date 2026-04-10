from __future__ import annotations

import copy
import unittest

from cockpit.safe_bench import (
    RiskZone,
    build_cockpit_safe_bench,
    build_fallback_generalization_bench,
    build_fallback_bench,
    build_held_out_generalization_bench,
    validate_generalization_bench,
    validate_cockpit_safe_bench,
    validate_fallback_bench,
)
from cockpit.safe_route import GatewayStatus, SafeRouteRuntime
from cockpit.state import INITIAL_STATE


class SafetyBenchTests(unittest.TestCase):
    def test_suite_is_valid_and_has_all_risk_zones(self) -> None:
        cases = build_cockpit_safe_bench()
        validate_cockpit_safe_bench(cases)

        zones = {case.risk_zone for case in cases}
        self.assertEqual(zones, {RiskZone.GREEN, RiskZone.YELLOW, RiskZone.RED})
        self.assertGreaterEqual(len(cases), 15)

    def test_gateway_matches_expected_labels_on_suite(self) -> None:
        runtime = SafeRouteRuntime()

        for case in build_cockpit_safe_bench():
            state = copy.deepcopy(INITIAL_STATE)
            state["vehicle"].update(case.vehicle_state)
            if "biometric_verified" in case.auth_context:
                state["auth"]["biometric_verified"] = bool(case.auth_context["biometric_verified"])

            contract = runtime.compiler.compile_task(case.task, prompt=case.prompt)
            decision = runtime.gateway.authorize(
                contract,
                state,
                auth_context=case.auth_context,
            )
            self.assertEqual(
                decision.status,
                case.expected_status,
                msg=f"{case.case_id}: expected {case.expected_status.value}, got {decision.status.value}",
            )

    def test_fallback_suite_is_valid_and_covers_all_categories(self) -> None:
        cases = build_fallback_bench()
        validate_fallback_bench(cases)

        categories = {case.category for case in cases}
        self.assertEqual(
            categories,
            {"navigation", "media", "climate", "phone", "messages", "settings", "vehicle"},
        )
        self.assertEqual(len(cases), 7)

    def test_held_out_generalization_suite_is_valid(self) -> None:
        cases = build_held_out_generalization_bench()
        validate_generalization_bench(cases)

        categories = {case.category for case in cases}
        self.assertEqual(
            categories,
            {"navigation", "media", "climate", "phone", "messages", "settings", "vehicle"},
        )
        self.assertEqual(len(cases), 10)
        confirmed_cases = [case for case in cases if case.auth_context.get("confirmation_provided")]
        self.assertGreaterEqual(len(confirmed_cases), 2)

    def test_fallback_generalization_suite_is_valid_and_matches_categories(self) -> None:
        cases = build_fallback_generalization_bench()
        validate_fallback_bench(cases)
        self.assertEqual(len(cases), 7)


if __name__ == "__main__":
    unittest.main()
