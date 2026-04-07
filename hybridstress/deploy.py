"""
HybridStress Deployment Script
================================

Syncs experiment code to GPU server and manages remote execution.

Usage:
    python -m hybridstress.deploy --action sync
    python -m hybridstress.deploy --action install
    python -m hybridstress.deploy --action run --stage sanity
    python -m hybridstress.deploy --action status
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Server config
SERVER_HOST = "9.tcp.vip.cpolar.cn"
SERVER_PORT = 14772
SERVER_USER = "fce"
SERVER_PASS = "1234"
CONDA_PATH = "/home/fce/miniconda3"
CONDA_ENV = "gelab-zero"
WORK_DIR = "/home/fce/mnt/2T/Frank/LHT/gelab-zero-new"
REMOTE_HYBRIDSTRESS = f"{WORK_DIR}/hybridstress"


def get_ssh_client():
    """Create and return an SSH client connected to the server."""
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USER,
                password=SERVER_PASS, timeout=15)
    return ssh


def exec_remote(ssh, cmd: str, timeout: int = 300) -> str:
    """Execute command on server and return stdout."""
    full_cmd = (
        f'eval "$({CONDA_PATH}/bin/conda shell.bash hook)" && '
        f'conda activate {CONDA_ENV} && '
        f'cd {WORK_DIR} && {cmd}'
    )
    stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if err and "error" in err.lower():
        logger.warning(f"stderr: {err[:500]}")
    return out


def action_sync():
    """Sync hybridstress code to server via SFTP."""
    import paramiko
    ssh = get_ssh_client()
    sftp = ssh.open_sftp()

    # Ensure remote directory exists
    try:
        sftp.stat(REMOTE_HYBRIDSTRESS)
    except FileNotFoundError:
        sftp.mkdir(REMOTE_HYBRIDSTRESS)

    # Upload all Python files
    local_dir = Path(__file__).parent
    for py_file in sorted(local_dir.glob("*.py")):
        remote_path = f"{REMOTE_HYBRIDSTRESS}/{py_file.name}"
        sftp.put(str(py_file), remote_path)
        logger.info(f"  Uploaded: {py_file.name}")

    # Upload requirements
    req_file = local_dir / "requirements.txt"
    if req_file.exists():
        sftp.put(str(req_file), f"{REMOTE_HYBRIDSTRESS}/requirements.txt")
        logger.info("  Uploaded: requirements.txt")

    sftp.close()
    ssh.close()
    logger.info("Sync complete.")


def action_install():
    """Install HybridStress dependencies on server."""
    ssh = get_ssh_client()
    out = exec_remote(
        ssh,
        f"pip install -r {REMOTE_HYBRIDSTRESS}/requirements.txt",
        timeout=600,
    )
    print(out)
    ssh.close()
    logger.info("Install complete.")


def action_run(stage: str, use_tmux: bool = True, extra_args: str = ""):
    """Run a benchmark stage on the server."""
    ssh = get_ssh_client()

    output_map = {
        "sanity": "hybridstress_sanity",
        "full": "hybridstress_benchmark",
        "detector": "hybridstress_detector",
        "transfer": "hybridstress_transfer",
        "utility": "hybridstress_utility",
    }
    output_dir = output_map.get(stage, f"hybridstress_{stage}")

    cmd = (
        f"python -m hybridstress.run_benchmark "
        f"--stage {stage} --output {output_dir} {extra_args}"
    )

    if use_tmux:
        session_name = f"hs_{stage}"
        tmux_cmd = (
            f'tmux new-session -d -s {session_name} '
            f'\'eval "$({CONDA_PATH}/bin/conda shell.bash hook)" && '
            f'conda activate {CONDA_ENV} && '
            f'cd {WORK_DIR} && {cmd} > /tmp/{session_name}.log 2>&1\''
        )
        stdin, stdout, stderr = ssh.exec_command(tmux_cmd, timeout=30)
        out = stdout.read().decode()
        logger.info(f"Started tmux session: {session_name}")
        logger.info(f"Monitor: ssh fce 'tmux attach -t {session_name}'")
        logger.info(f"Logs: ssh fce 'tail -f /tmp/{session_name}.log'")
    else:
        out = exec_remote(ssh, cmd, timeout=7200)
        print(out)

    ssh.close()


def action_status():
    """Check status of running experiments."""
    ssh = get_ssh_client()

    # Check tmux sessions
    stdin, stdout, stderr = ssh.exec_command("tmux ls 2>&1")
    tmux_out = stdout.read().decode()
    print("=== Tmux Sessions ===")
    print(tmux_out if tmux_out.strip() else "(none)")

    # Check GPU usage
    stdin, stdout, stderr = ssh.exec_command(
        "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu "
        "--format=csv,noheader"
    )
    gpu_out = stdout.read().decode()
    print("\n=== GPU Status ===")
    print(gpu_out)

    # Check results directories
    out = exec_remote(
        ssh,
        'for d in hybridstress_*; do [ -d "$d" ] && echo "$d: $(ls "$d" | wc -l) files"; done'
    )
    if out.strip():
        print("\n=== Result Directories ===")
        print(out)

    ssh.close()


def action_fetch_results(stage: str, local_dir: str = "results"):
    """Download results from server."""
    import paramiko
    ssh = get_ssh_client()
    sftp = ssh.open_sftp()

    output_map = {
        "sanity": "hybridstress_sanity",
        "full": "hybridstress_benchmark",
        "detector": "hybridstress_detector",
    }
    remote_dir = f"{WORK_DIR}/{output_map.get(stage, f'hybridstress_{stage}')}"

    local_path = Path(local_dir) / stage
    local_path.mkdir(parents=True, exist_ok=True)

    try:
        files = sftp.listdir(remote_dir)
        for fname in files:
            if fname.endswith((".json", ".csv", ".txt", ".md")):
                sftp.get(f"{remote_dir}/{fname}", str(local_path / fname))
                logger.info(f"  Downloaded: {fname}")
    except FileNotFoundError:
        logger.warning(f"Remote directory not found: {remote_dir}")

    sftp.close()
    ssh.close()


def main():
    parser = argparse.ArgumentParser(description="HybridStress Deployment")
    parser.add_argument("--action", choices=["sync", "install", "run", "status", "fetch"],
                        required=True)
    parser.add_argument("--stage", type=str, default="sanity",
                        help="Stage to run (for run/fetch)")
    parser.add_argument("--no-tmux", action="store_true",
                        help="Run foreground instead of tmux")
    parser.add_argument("--args", type=str, default="",
                        help="Extra args for run_benchmark")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.action == "sync":
        action_sync()
    elif args.action == "install":
        action_install()
    elif args.action == "run":
        action_run(args.stage, use_tmux=not args.no_tmux, extra_args=args.args)
    elif args.action == "status":
        action_status()
    elif args.action == "fetch":
        action_fetch_results(args.stage)


if __name__ == "__main__":
    main()
