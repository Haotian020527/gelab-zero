#!/usr/bin/env python3
"""Check M1 experiment log on remote server via paramiko SSH."""

import paramiko
import sys

HOST = "9.tcp.vip.cpolar.cn"
PORT = 14772
USERNAME = "fce"
PASSWORD = "1234"

COMMANDS = [
    ("=== Last 100 lines of /tmp/hs_full.log ===",
     "tail -100 /tmp/hs_full.log"),
    ("=== Error count in hs_full.log ===",
     'grep -c "ERROR\\|FAILED\\|error" /tmp/hs_full.log'),
    ("=== Direct execution / branch / executor errors (last 20) ===",
     'grep "Direct execution failed\\|Branch.*failed\\|executor returned error" /tmp/hs_full.log | tail -20'),
    ("=== Events directory listing ===",
     "ls -la /home/fce/mnt/2T/Frank/LHT/gelab-zero-new/hybridstress_benchmark/events/ 2>/dev/null | head -20"),
]


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Connecting to {HOST}:{PORT} as {USERNAME} ...")
    try:
        client.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD, timeout=30)
        print("Connected successfully.\n")
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    for header, cmd in COMMANDS:
        print(header)
        print("-" * len(header))
        try:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if out:
                print(out)
            if err:
                print(f"[stderr] {err}")
            if not out and not err:
                print("(no output)")
        except Exception as e:
            print(f"[error running command] {e}")
        print()

    client.close()
    print("Done.")


if __name__ == "__main__":
    main()
