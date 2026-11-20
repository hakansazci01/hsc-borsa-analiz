import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import auth, tr_scalper

LOG = auth.USERS_DIR / "tr_scalper.log"
DURATION = 30 * 60
INTERVAL = 15

start = time.time()
print("CANLI SCALPER BASLADI", time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
print("SINIRLAR: emir=10 TRY | max zarar=3 TRY | max islem=3 | TP=0.45% SL=0.35%", flush=True)

with LOG.open("a", encoding="utf-8") as fh:
    fh.write(f"\n=== SESSION {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    fh.flush()
    while time.time() - start < DURATION:
        if tr_scalper.kill_switch():
            msg = "KILL SWITCH: oturum durduruldu"
            print(msg, flush=True)
            fh.write(msg + "\n")
            fh.flush()
            break
        try:
            lines = tr_scalper.cycle()
            for line in lines:
                ts = time.strftime("%H:%M:%S")
                out = f"[{ts}] {line}"
                print(out, flush=True)
                fh.write(out + "\n")
            fh.flush()
        except Exception as exc:
            out = f"[{time.strftime('%H:%M:%S')}] HATA {type(exc).__name__}: {str(exc)[:120]}"
            print(out, flush=True)
            fh.write(out + "\n")
            fh.flush()
        time.sleep(INTERVAL)

print("SCALPER OTURUMU BITTI", time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
