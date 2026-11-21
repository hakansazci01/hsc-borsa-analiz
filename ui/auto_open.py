"""
Otomatik açma — SADECE testler 28/28 veya üzeri geçerse çalışır.

3 adım:
  a) config.yaml binance_tr.enabled = false -> true
  b) confirmation_phrase HSC-BINANCE-TR-ARM kod içinden doğrulanır (panel beklenmez)
  c) STOP_FILE varsa silinir

Güvenlik kilitleri (dinamik %10, günlük limit, trailing DD %15, kâr kilidi +50,
ani çöküş %5/5dk) DEĞİŞMEZ. Sanal/all-in mod YOK.

Test başarısız olursa HİÇBİR şey değiştirmez, bildirim gönderir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from ui import autonomous_ops as ops
from ui import tr_scalper as t


ROOT = Path(__file__).resolve().parent.parent
MIN_TESTS = 28


def run_tests() -> tuple[bool, int, int, str]:
    """tests/run_all.py çalıştır, 'N/M test geçti' çıktısını ayrıştır."""
    exe = str(ROOT / ".venv" / "Scripts" / "python.exe")
    if not Path(exe).exists():
        exe = sys.executable
    proc = subprocess.run(
        [exe, "tests/run_all.py"], cwd=str(ROOT),
        capture_output=True, text=True, timeout=600,
    )
    out = proc.stdout + proc.stderr
    passed = failed = 0
    for line in out.splitlines():
        line = line.strip()
        if " test geçti" in line:
            # format: "30/30 test geçti"  (passed/total)
            token = line.split()[0]
            try:
                p, total = token.split("/")
                passed, failed = int(p), int(total) - int(p)
            except (ValueError, IndexError):
                pass
    ok = bool(passed >= MIN_TESTS and failed == 0)
    return ok, passed, failed, out[-2000:]


def _set_enabled(true_or_false: bool) -> None:
    """config.yaml içinde YALNIZCA binance_tr.enabled satırını değiştir."""
    p = ROOT / "config.yaml"
    lines = p.read_text(encoding="utf-8").splitlines()
    in_section = False
    out = []
    for line in lines:
        if line.strip() == "binance_tr:":
            in_section = True
        elif line and not line.startswith(" ") and not line.startswith("#"):
            in_section = False
        if in_section and line.strip().startswith("enabled:"):
            out.append("  enabled: true" if true_or_false else "  enabled: false")
        else:
            out.append(line)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def open_robot() -> dict[str, Any]:
    """Test guard + 3 adım + doğrulama + bildirim."""
    ok, passed, failed, log = run_tests()
    if not ok:
        msg = f"TEST BAŞARISIZ — bot AÇILMADI ({passed}/{passed+failed}, min {MIN_TESTS})"
        ops._log(msg)
        ops._send("HSC OTOMATIK AÇMA", msg + "\n" + log[-400:])
        return {"opened": False, "reason": msg, "passed": passed, "failed": failed}
    ops._log(f"test guard geçti: {passed}/{passed+failed}")

    # a) enabled = true
    _set_enabled(True)
    # b) phrase kod içinden doğrula
    confirmed = t.auto_confirm_phrase()
    # c) STOP_FILE sil
    if t.STOP_FILE.exists():
        t.STOP_FILE.unlink()

    gates = t.config_gate()
    state = {
        "opened": not gates and confirmed,
        "config_gate": gates,
        "phrase_confirmed": confirmed,
        "stop_file": t.STOP_FILE.exists(),
        "enabled": t.cfg().get("enabled"),
        "passed": passed, "failed": failed,
    }
    if state["opened"]:
        msg = (f"ROBOT OTOMATIK AÇILDI ✅\nTestler: {passed}/{passed+failed}\n"
               f"config_gate: {gates} (boş = temiz)\n"
               f"Onay ifadesi: doğrulandı\nSTOP_FILE: yok\n"
               f"İşlem boyutu: bakiye %10 · günlük limit %10 · DD %15 · kâr kilidi +50")
        ops._log(msg)
        ops._send("HSC OTOMATIK AÇMA", msg)
    else:
        msg = f"ROBOT AÇILAMADI — kilitler: {gates}"
        ops._log(msg)
        ops._send("HSC OTOMATIK AÇMA", msg)
    return state


if __name__ == "__main__":
    print(open_robot())
