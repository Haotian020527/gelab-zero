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
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]

    if isinstance(raw, dict):
        for key in ("devices", "data", "result"):
            value = raw.get(key)
            if isinstance(value, list):
                return [str(item) for item in value if str(item).strip()]

    raise ValueError(f"Unexpected device response from MCP: {raw!r}")


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

        result = await client.call_tool("ask_agent_hybrid", payload)
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
