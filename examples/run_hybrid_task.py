from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_default_mcp_url() -> str:
    env_url = os.getenv("GELAB_MCP_URL")
    if env_url:
        return env_url

    config_path = Path(__file__).resolve().parents[1] / "mcp_server_config.yaml"
    default_port = 8704

    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
        port = int(config.get("server_config", {}).get("mcp_server_port", default_port))
    except Exception:
        port = default_port

    return f"http://localhost:{port}/mcp"


def _extract_devices(raw: Any) -> List[str]:
    list_candidate = _extract_list_candidate(raw)
    if list_candidate is None:
        raise ValueError(f"Unexpected device response from MCP: {raw!r}")
    return [str(item) for item in list_candidate if str(item).strip()]


def _extract_list_candidate(raw: Any) -> List[Any] | None:
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        for key in ("devices", "data", "result"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return None

    for attr in ("structured_content", "data", "result"):
        if not hasattr(raw, attr):
            continue
        value = getattr(raw, attr)
        candidate = _extract_list_candidate(value)
        if candidate is not None:
            return candidate

    return None


def _normalize_tool_result(raw: Any) -> Any:
    if isinstance(raw, (dict, list, str, int, float, bool)) or raw is None:
        return raw

    if hasattr(raw, "structured_content"):
        structured_content = getattr(raw, "structured_content")
        if isinstance(structured_content, dict):
            if "result" in structured_content:
                return structured_content["result"]
            return structured_content

    if hasattr(raw, "result"):
        result = getattr(raw, "result")
        if result is not None:
            return result

    if hasattr(raw, "data"):
        data = getattr(raw, "data")
        if data is not None:
            return data

    if hasattr(raw, "model_dump"):
        try:
            return raw.model_dump()
        except Exception:
            pass

    return str(raw)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a Hybrid Cockpit task via ask_agent_hybrid MCP tool."
    )
    parser.add_argument(
        "task",
        nargs="?",
        default=None,
        help='Task text, e.g. "Play Hotel California on Spotify".',
    )
    parser.add_argument(
        "--mcp-url",
        default=_load_default_mcp_url(),
        help="MCP endpoint URL. Default reads mcp_server_config.yaml or GELAB_MCP_URL.",
    )
    parser.add_argument(
        "--device-id",
        default=None,
        help="Device ID. If omitted, the first connected device is used.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Max steps for GUI fallback execution.",
    )
    parser.add_argument(
        "--spotify-device-id",
        default=None,
        help="Optional Spotify Connect device id for API-first route.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session id to continue previous task.",
    )
    parser.add_argument(
        "--reply-from-client",
        default=None,
        help="Reply text for continue mode when previous step ended with INFO.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.task is None and args.session_id is None:
        raise ValueError("Either task or --session-id must be provided.")
    if args.task is not None and args.session_id is not None:
        raise ValueError("Do not provide both task and --session-id together.")

    try:
        from fastmcp import Client
    except ImportError as exc:
        raise RuntimeError("Missing dependency fastmcp. Run: pip install -r requirements.txt") from exc

    async with Client(args.mcp_url) as client:
        devices_raw = await client.call_tool("list_connected_devices", {})
        devices = _extract_devices(devices_raw)
        if not devices:
            raise RuntimeError("No connected devices found. Check `adb devices` first.")

        device_id = args.device_id or devices[0]
        payload: Dict[str, Any] = {
            "device_id": device_id,
            "task": args.task,
            "max_steps": args.max_steps,
            "session_id": args.session_id,
            "reply_from_client": args.reply_from_client,
        }
        if args.spotify_device_id:
            payload["spotify_device_id"] = args.spotify_device_id

        result_raw = await client.call_tool("ask_agent_hybrid", payload)
        result = _normalize_tool_result(result_raw)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"Run failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
