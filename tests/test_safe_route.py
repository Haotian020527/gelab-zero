from __future__ import annotations

import copy
import unittest

from cockpit.safe_route import (
    ACTION_CONTRACT_SCHEMA_VERSION,
    GatewayStatus,
    RuleBasedContractCompiler,
    SafeRouteRuntime,
)
from cockpit.state import INITIAL_STATE
from cockpit.task_definitions import COCKPIT_TASK_BY_ID


class SafeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = RuleBasedContractCompiler()
        self.runtime = SafeRouteRuntime()

    def test_contract_schema_version_is_frozen(self) -> None:
        self.assertEqual(ACTION_CONTRACT_SCHEMA_VERSION, "1.0")

    def test_green_task_compiles_to_allowable_contract(self) -> None:
        task = COCKPIT_TASK_BY_ID["media_play_004"]
        contract = self.compiler.compile_task(task)
        self.assertEqual(contract.risk_zone.value, "green")
        self.assertFalse(contract.required_2fa)
        self.assertEqual(contract.gui_fallback_policy, "allow")

    def test_red_task_blocks_on_bad_gear(self) -> None:
        task = {
            "task_id": "red_ota_seed",
            "description": "Start OTA update now",
            "api_actions": [{"method": "POST", "path": "/api/vehicle/ota_start", "body": {}}],
            "postconditions": [],
        }
        contract = self.compiler.compile_task(task)
        state = copy.deepcopy(INITIAL_STATE)
        state["vehicle"]["gear"] = "D"
        decision = self.runtime.gateway.authorize(contract, state)
        self.assertEqual(decision.status, GatewayStatus.BLOCK)

    def test_red_task_requires_biometric(self) -> None:
        task = {
            "task_id": "red_adas_seed",
            "description": "Calibrate ADAS",
            "api_actions": [{"method": "POST", "path": "/api/vehicle/adas_calibrate", "body": {}}],
            "postconditions": [],
        }
        contract = self.compiler.compile_task(task)
        state = copy.deepcopy(INITIAL_STATE)
        decision = self.runtime.gateway.authorize(contract, state)
        self.assertEqual(decision.status, GatewayStatus.CHALLENGE)
        allow = self.runtime.gateway.authorize(
            contract,
            state,
            auth_context={"biometric_verified": True},
        )
        self.assertEqual(allow.status, GatewayStatus.ALLOW)

    def test_yellow_task_requires_confirmation(self) -> None:
        task = COCKPIT_TASK_BY_ID["veh_unlock_020"]
        contract = self.compiler.compile_task(task)
        state = copy.deepcopy(INITIAL_STATE)
        decision = self.runtime.gateway.authorize(contract, state)
        self.assertEqual(decision.status, GatewayStatus.CHALLENGE)
        allow = self.runtime.gateway.authorize(
            contract,
            state,
            auth_context={"confirmation_provided": True},
        )
        self.assertEqual(allow.status, GatewayStatus.ALLOW)


if __name__ == "__main__":
    unittest.main()
