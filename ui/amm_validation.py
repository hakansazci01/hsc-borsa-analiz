"""HSC-AMM ÖLÇÜMÜ — walk-forward + 1000 yollu Monte Carlo.

Backtest max DD'yi 'en kötü' sanma; P95 ve ekstrem için 2 katını al.
Sadece ölçer — emir/state değiştirmez.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any

from ui import auth

REPORT = auth.USERS_DIR / "amm_validation.json"
FEE = 0.15          # maker+BNB, gidiş-dönüş yüzde
SPREAD = 0.20       # ortalama spread %
GAMMA = 0.5
TAU = 15.0 / (24 * 60)


def _sim_path(returns: list[float], fill_rate: float = 0.35) -> dict[str, float]:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    trades = 0
    for r in returns:
        if random.random() < fill_rate:
            net = (SPREAD - FEE) / 100.0 + r * 0.02   # spread geliri + envanter etkisi
            equity *= (1 + net)
            trades += 1
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)
    return {"ret_pct": round((equity - 1) * 100, 3),
            "max_dd_pct": round(max_dd * 100, 2), "trades": trades}


def monte_carlo(returns: list[float], paths: int = 1000) -> dict[str, Any]:
    results = [_sim_path(returns) for _ in range(paths)]
    rets = sorted(x["ret_pct"] for x in results)
    dds = sorted(x["max_dd_pct"] for x in results)
    p = lambda arr, q: arr[min(len(arr) - 1, int(len(arr) * q))]
    return {"paths": paths,
            "best_ret_pct": rets[-1], "median_ret_pct": p(rets, 0.5),
            "worst_ret_pct": rets[0],
            "p05_dd_pct": p(dds, 0.05), "p95_dd_pct": p(dds, 0.95),
            "worst_dd_pct": dds[0], "stress_dd_x2_pct": round(p(dds, 0.95) * 2, 2)}


def walk_forward(returns: list[float], train_frac: float = 0.7) -> dict[str, Any]:
    n = len(returns)
    if n < 100:
        return {"ok": False, "reason": f"yetersiz veri: {n}"}
    cut = int(n * train_frac)
    a = _sim_path(returns[:cut])
    b = _sim_path(returns[cut:])
    return {"ok": True, "train": a, "test": b,
            "degradation": round(b["ret_pct"] / a["ret_pct"], 3) if a["ret_pct"] > 0 else 0.0}


def report(wf: dict[str, Any], mc: dict[str, Any]) -> str:
    import json
    data = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "wf": wf, "mc": mc}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    msg = (f"WF: eğitim {wf.get('train', {}).get('ret_pct', 0):+.2f}% / "
           f"test {wf.get('test', {}).get('ret_pct', 0):+.2f}% · "
           f"MC {mc['paths']} yol · MC P95 DD: {mc['p95_dd_pct']:.2f}% · "
           f"En kötü DD: {mc['worst_dd_pct']:.2f}% · Stress x2: {mc['stress_dd_x2_pct']:.2f}%")
    try:
        from ui import autonomous_ops
        autonomous_ops._log(msg)
    except Exception:
        pass
    return msg
