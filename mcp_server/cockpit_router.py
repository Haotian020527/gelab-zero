from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
import traceback
from typing import Any, Callable, Dict, Mapping, Optional, Protocol


@dataclass(frozen=True)
class ToolMatch:
    """Tool match result used by router for ranking and parameter passing."""

    tool_name: str
    score: float
    reason: str
    payload: Dict[str, Any] = field(default_factory=dict)


class CockpitTool(Protocol):
    """Protocol for Cockpit-MCP standard tools."""

    name: str

    def match(self, task: str) -> Optional[ToolMatch]:
        """Return match info if tool can handle task, otherwise None."""
        ...

    def execute(self, task: str, context: Mapping[str, Any], match: ToolMatch) -> Dict[str, Any]:
        """Execute API-first logic and return serializable result."""
        ...


@dataclass
class CockpitRouteResult:
    """Router output with route decision and execution details."""

    status: str
    route: str
    task: str
    selected_tool: Optional[str] = None
    reason: str = ""
    elapsed_ms: int = 0
    tool_result: Optional[Dict[str, Any]] = None
    fallback_result: Optional[Dict[str, Any]] = None
    errors: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "route": self.route,
            "task": self.task,
            "selected_tool": self.selected_tool,
            "reason": self.reason,
            "elapsed_ms": self.elapsed_ms,
            "tool_result": self.tool_result,
            "fallback_result": self.fallback_result,
            "errors": self.errors,
        }


class CockpitRouter:
    """
    API-first, GUI-fallback router.

    Execution priority:
    1) try Cockpit-MCP standard tool by intent match;
    2) if no match OR tool execution fails -> fallback to GUI executor.
    """

    def __init__(
        self,
        gui_fallback_executor: Callable[[str, Mapping[str, Any]], Dict[str, Any]],
        min_match_score: float = 0.60,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._tools: Dict[str, CockpitTool] = {}
        self._gui_fallback_executor = gui_fallback_executor
        self._min_match_score = min_match_score
        self._logger = logger or logging.getLogger(__name__)

    def register_tool(self, tool: CockpitTool) -> None:
        self._tools[tool.name] = tool
        self._logger.info("CockpitRouter registered tool: %s", tool.name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def route(self, task: str, context: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        route_start = time.perf_counter()
        runtime_context: Mapping[str, Any] = context or {}

        try:
            match = self._pick_best_match(task=task)
            if match is None:
                fallback_result = self._run_gui_fallback(
                    task=task,
                    context=runtime_context,
                    reason="no_cockpit_tool_match",
                )
                return CockpitRouteResult(
                    status="success",
                    route="gui_fallback",
                    task=task,
                    reason="no_tool_matched",
                    elapsed_ms=int((time.perf_counter() - route_start) * 1000),
                    fallback_result=fallback_result,
                ).to_dict()

            selected_tool = self._tools[match.tool_name]
            self._logger.info(
                "CockpitRouter selected tool=%s score=%.3f reason=%s",
                match.tool_name,
                match.score,
                match.reason,
            )

            try:
                tool_result = selected_tool.execute(task=task, context=runtime_context, match=match)
                return CockpitRouteResult(
                    status="success",
                    route="api_first",
                    task=task,
                    selected_tool=match.tool_name,
                    reason="tool_executed_successfully",
                    elapsed_ms=int((time.perf_counter() - route_start) * 1000),
                    tool_result=tool_result,
                ).to_dict()
            except Exception as tool_exc:  # pragma: no cover - runtime failure path
                self._logger.exception("Tool execution failed, falling back to GUI. task=%s", task)
                fallback_result = self._run_gui_fallback(
                    task=task,
                    context=runtime_context,
                    reason="tool_execution_failed",
                )
                return CockpitRouteResult(
                    status="success",
                    route="gui_fallback",
                    task=task,
                    selected_tool=match.tool_name,
                    reason="tool_failed_then_gui_fallback",
                    elapsed_ms=int((time.perf_counter() - route_start) * 1000),
                    fallback_result=fallback_result,
                    errors={"tool_error": f"{type(tool_exc).__name__}: {tool_exc}"},
                ).to_dict()

        except Exception as fatal_exc:  # pragma: no cover - fatal failure path
            self._logger.error("CockpitRouter fatal failure: %s", fatal_exc)
            self._logger.debug("CockpitRouter traceback:\n%s", traceback.format_exc())
            return CockpitRouteResult(
                status="failed",
                route="router_error",
                task=task,
                reason="router_fatal_error",
                elapsed_ms=int((time.perf_counter() - route_start) * 1000),
                errors={"router_error": f"{type(fatal_exc).__name__}: {fatal_exc}"},
            ).to_dict()

    def _pick_best_match(self, task: str) -> Optional[ToolMatch]:
        candidates: list[ToolMatch] = []
        for tool in self._tools.values():
            try:
                match = tool.match(task)
                if match is None:
                    continue
                if match.score < self._min_match_score:
                    continue
                candidates.append(match)
            except Exception as exc:  # pragma: no cover - plugin failure path
                self._logger.warning("Tool match skipped for %s due to error: %s", tool.name, exc)

        if not candidates:
            return None
        candidates.sort(key=lambda m: m.score, reverse=True)
        return candidates[0]

    def _run_gui_fallback(
        self,
        task: str,
        context: Mapping[str, Any],
        reason: str,
    ) -> Dict[str, Any]:
        fallback_result = self._gui_fallback_executor(task, context)
        if isinstance(fallback_result, dict) and "route_hint" not in fallback_result:
            fallback_result["route_hint"] = reason
        return fallback_result
