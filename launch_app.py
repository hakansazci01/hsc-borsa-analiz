"""Streamlit uygulamasını kalıcı başlatır (zaten ayakta değilse)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent


def app_alive() -> bool:
    me = __import__("os").getpid()
    for p in psutil.process_iter(["pid", "cmdline"]):
        cmd = " ".join(p.info.get("cmdline") or [])
        if ("streamlit" in cmd and "streamlit_app.py" in cmd) and p.info["pid"] != me:
            return True
    return False


def main() -> None:
    if app_alive():
        return
    exe = str(ROOT / ".venv" / "Scripts" / "streamlit.exe")
    subprocess.Popen(
        [exe, "run", "streamlit_app.py", "--server.port", "8501",
         "--server.headless", "true"],
        cwd=str(ROOT),
        creationflags=0x00000008 | 0x00000200,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
