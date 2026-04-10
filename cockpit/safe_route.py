"""SafeRoute-Cockpit core primitives for contract-routed execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Any, Dict, List, Mapping, Optional

from hybridstress.data_types import Predicate

from .integration import CockpitClient, CockpitExecutor


ACTION_CONTRACT_SCHEMA_VERSION = "1.0"

ACTION_CONTRACT_SCHEMA: Dict[str, Any] = {
    "version": ACTION_CONTRACT_SCHEMA_VERSION,
    "required_fields": [
        "intent",
        "risk_zone",
        "required_signals",
        "required_2fa",
        "allowed_api_paths",
        "gui_fallback_policy",
        "postconditions",
    ],
    "risk_zones": ["green", "yellow", "red"],
    "gui_fallback_policies": ["allow", "challenge", "deny"],
}


class RiskZone(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class GatewayStatus(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    CHALLENGE = "challenge"


@dataclass(frozen=True)
class ActionContract:
    intent: str
    risk_zone: RiskZone
    required_signals: Dict[str, Any]
    required_2fa: bool
    allowed_api_paths: List[str]
    gui_fallback_policy: str
    postconditions: List[Predicate] = field(default_factory=list)
    task_id: Optional[str] = None
    prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": ACTION_CONTRACT_SCHEMA_VERSION,
            "intent": self.intent,
            "risk_zone": self.risk_zone.value,
            "required_signals": self.required_signals,
            "required_2fa": self.required_2fa,
            "allowed_api_paths": self.allowed_api_paths,
            "gui_fallback_policy": self.gui_fallback_policy,
            "postconditions": [str(predicate) for predicate in self.postconditions],
            "task_id": self.task_id,
            "prompt": self.prompt,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GatewayDecision:
    status: GatewayStatus
    reason: str
    checked_signals: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    missing_requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "checked_signals": self.checked_signals,
            "missing_requirements": self.missing_requirements,
        }


RISK_POLICY_BY_PATH: Dict[str, Dict[str, Any]] = {
    "/api/vehicle/ota_start": {
        "intent": "vehicle.ota_start",
        "risk_zone": RiskZone.RED,
        "required_signals": {
            "vehicle.gear": "P",
            "vehicle.speed_kmh": 0,
            "vehicle.battery_percent": ">=30",
        },
        "required_2fa": True,
        "gui_fallback_policy": "deny",
    },
    "/api/vehicle/adas_calibrate": {
        "intent": "vehicle.adas_calibrate",
        "risk_zone": RiskZone.RED,
        "required_signals": {
            "vehicle.gear": "P",
            "vehicle.speed_kmh": 0,
        },
        "required_2fa": True,
        "gui_fallback_policy": "deny",
    },
    "/api/vehicle/trip_reset": {
        "intent": "vehicle.trip_reset",
        "risk_zone": RiskZone.RED,
        "required_signals": {
            "vehicle.gear": "P",
            "vehicle.speed_kmh": 0,
        },
        "required_2fa": True,
        "gui_fallback_policy": "deny",
    },
    "/api/vehicle/unlock_doors": {
        "intent": "vehicle.unlock_doors",
        "risk_zone": RiskZone.YELLOW,
        "required_signals": {"vehicle.speed_kmh": 0},
        "required_2fa": False,
        "gui_fallback_policy": "challenge",
    },
    "/api/vehicle/trunk": {
        "intent": "vehicle.toggle_trunk",
        "risk_zone": RiskZone.YELLOW,
        "required_signals": {"vehicle.speed_kmh": 0},
        "required_2fa": False,
        "gui_fallback_policy": "challenge",
    },
    "/api/vehicle/window": {
        "intent": "vehicle.set_window",
        "risk_zone": RiskZone.YELLOW,
        "required_signals": {"vehicle.speed_kmh": 0},
        "required_2fa": False,
        "gui_fallback_policy": "challenge",
    },
    "/api/vehicle/drive_mode": {
        "intent": "vehicle.set_drive_mode",
        "risk_zone": RiskZone.YELLOW,
        "required_signals": {"vehicle.speed_kmh": 0},
        "required_2fa": False,
        "gui_fallback_policy": "challenge",
    },
}


class RuleBasedContractCompiler:
    """Rule-based compiler from task or prompt into a typed action contract."""

    def compile_task(self, task: Mapping[str, Any], prompt: Optional[str] = None) -> ActionContract:
        api_actions = list(task.get("api_actions", []))
        first_path = api_actions[0]["path"] if api_actions else ""
        policy = self._policy_for_path(first_path)
        effective_prompt = prompt or str(task.get("description") or task.get("instruction") or "")

        return ActionContract(
            intent=policy["intent"],
            risk_zone=policy["risk_zone"],
            required_signals=dict(policy["required_signals"]),
            required_2fa=bool(policy["required_2fa"]),
            allowed_api_paths=[action["path"] for action in api_actions],
            gui_fallback_policy=str(policy["gui_fallback_policy"]),
            postconditions=list(task.get("postconditions", [])),
            task_id=task.get("task_id"),
            prompt=effective_prompt,
            metadata={
                "category": task.get("category"),
                "app": task.get("app"),
            },
        )

    def compile_prompt(
        self,
        prompt: str,
        task: Optional[Mapping[str, Any]] = None,
    ) -> ActionContract:
        if task is not None:
            return self.compile_task(task=task, prompt=prompt)

        lowered = prompt.lower()
        if any(token in lowered for token in ("ota", "update", "升级")):
            policy = self._policy_for_path("/api/vehicle/ota_start")
        elif any(token in lowered for token in ("adas", "calibration", "校准")):
            policy = self._policy_for_path("/api/vehicle/adas_calibrate")
        elif any(token in lowered for token in ("unlock", "解锁", "door")):
            policy = self._policy_for_path("/api/vehicle/unlock_doors")
        elif any(token in lowered for token in ("trunk", "后备箱")):
            policy = self._policy_for_path("/api/vehicle/trunk")
        else:
            policy = {
                "intent": "generic.green_task",
                "risk_zone": RiskZone.GREEN,
                "required_signals": {},
                "required_2fa": False,
                "gui_fallback_policy": "allow",
            }

        return ActionContract(
            intent=policy["intent"],
            risk_zone=policy["risk_zone"],
            required_signals=dict(policy["required_signals"]),
            required_2fa=bool(policy["required_2fa"]),
            allowed_api_paths=[],
            gui_fallback_policy=str(policy["gui_fallback_policy"]),
            postconditions=[],
            task_id=None,
            prompt=prompt,
            metadata={},
        )

    def _policy_for_path(self, api_path: str) -> Dict[str, Any]:
        if api_path in RISK_POLICY_BY_PATH:
            return RISK_POLICY_BY_PATH[api_path]

        intent = self._intent_from_path(api_path)
        return {
            "intent": intent,
            "risk_zone": RiskZone.GREEN,
            "required_signals": {},
            "required_2fa": False,
            "gui_fallback_policy": "allow",
        }

    @staticmethod
    def _intent_from_path(api_path: str) -> str:
        cleaned = api_path.strip("/")
        if not cleaned:
            return "generic.unknown"
        parts = cleaned.split("/")
        if len(parts) >= 3 and parts[0] == "api":
            return f"{parts[1]}.{parts[2]}"
        return cleaned.replace("/", ".")


class DeterministicSafetyGateway:
    """Signal-grounded authorization gate outside the generative model."""

    def authorize(
        self,
        contract: ActionContract,
        state: Mapping[str, Any],
        *,
        auth_context: Optional[Mapping[str, Any]] = None,
    ) -> GatewayDecision:
        auth = dict(auth_context or {})
        checked_signals: Dict[str, Dict[str, Any]] = {}
        missing_requirements: List[str] = []

        for key, expected in contract.required_signals.items():
            actual = self._lookup_state_value(state, key)
            passed = self._matches_requirement(actual, expected)
            checked_signals[key] = {
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
            if not passed:
                missing_requirements.append(f"signal:{key}")

        if missing_requirements:
            return GatewayDecision(
                status=GatewayStatus.BLOCK,
                reason="required_vehicle_signals_not_satisfied",
                checked_signals=checked_signals,
                missing_requirements=missing_requirements,
            )

        biometric_verified = bool(
            auth.get("biometric_verified")
            or self._lookup_state_value(state, "auth.biometric_verified")
        )
        confirmation_provided = bool(auth.get("confirmation_provided"))

        if contract.required_2fa and not biometric_verified:
            return GatewayDecision(
                status=GatewayStatus.CHALLENGE,
                reason="biometric_verification_required",
                checked_signals=checked_signals,
                missing_requirements=["2fa"],
            )

        if contract.risk_zone == RiskZone.YELLOW and not confirmation_provided:
            return GatewayDecision(
                status=GatewayStatus.CHALLENGE,
                reason="explicit_confirmation_required",
                checked_signals=checked_signals,
                missing_requirements=["confirmation"],
            )

        return GatewayDecision(
            status=GatewayStatus.ALLOW,
            reason="all_requirements_satisfied",
            checked_signals=checked_signals,
        )

    @staticmethod
    def _lookup_state_value(state: Mapping[str, Any], dotted_key: str) -> Any:
        current: Any = state
        for part in dotted_key.split("."):
            if not isinstance(current, Mapping):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _matches_requirement(actual: Any, expected: Any) -> bool:
        if isinstance(expected, str):
            match = re.match(r"^(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)$", expected)
            if match:
                op, raw_value = match.groups()
                try:
                    actual_num = float(actual)
                    expected_num = float(raw_value)
                except (TypeError, ValueError):
                    return False
                if op == ">=":
                    return actual_num >= expected_num
                if op == "<=":
                    return actual_num <= expected_num
                if op == ">":
                    return actual_num > expected_num
                if op == "<":
                    return actual_num < expected_num
            return str(actual).lower() == expected.lower()
        return actual == expected


class SafeRouteRuntime:
    """Minimal experiment runtime for contract-routed cockpit execution."""

    def __init__(
        self,
        client: Optional[CockpitClient] = None,
        executor: Optional[CockpitExecutor] = None,
        compiler: Optional[RuleBasedContractCompiler] = None,
        gateway: Optional[DeterministicSafetyGateway] = None,
    ) -> None:
        self.client = client or CockpitClient()
        self.executor = executor or CockpitExecutor()
        self.compiler = compiler or RuleBasedContractCompiler()
        self.gateway = gateway or DeterministicSafetyGateway()

    def execute_task(
        self,
        task: Mapping[str, Any],
        *,
        prompt: Optional[str] = None,
        auth_context: Optional[Mapping[str, Any]] = None,
        force_gui_fallback: bool = False,
    ) -> Dict[str, Any]:
        contract = self.compiler.compile_task(task=task, prompt=prompt)
        state_before = self.client.get_state()
        decision = self.gateway.authorize(contract, state_before, auth_context=auth_context)

        execution_started_at = time.perf_counter()
        route = "blocked"
        execution_result: Dict[str, Any] = {
            "status": decision.status.value,
            "route": route,
        }

        if decision.status == GatewayStatus.ALLOW:
            if force_gui_fallback or not contract.allowed_api_paths:
                route = "gui_fallback"
                execution_result = self.executor.execute_task_gui_only(dict(task))
            else:
                route = "api_first"
                execution_result = self.executor.execute_task_api_only(dict(task))
        elif decision.status == GatewayStatus.CHALLENGE:
            route = "challenge"
        else:
            route = "blocked"

        elapsed_ms = int((time.perf_counter() - execution_started_at) * 1000)
        return {
            "contract": contract.to_dict(),
            "decision": decision.to_dict(),
            "route": route,
            "elapsed_ms": elapsed_ms,
            "execution_result": execution_result,
        }
