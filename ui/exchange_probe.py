"""
Herkese açık borsa API uçlarından hangilerinin erişilebilir olduğunu test eder.

Yalnızca public (anahtar gerektirmeyen) time/ticker uçlarına GET atılır;
anahtar, bakiye veya emir bilgisi kullanılmaz. Amaç: ağ/bölge engelini
teşhis edip hangi borsaya adapter yazılacağına karar vermek.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pandas as pd
import streamlit as st


ENDPOINTS: dict[str, str] = {
    "Binance TESTNET": "https://testnet.binance.vision/api/v3/ticker/price?symbol=BTCUSDT",
    "Binance CANLI": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
    "Bybit": "https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT",
    "Kraken": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
    "Coinbase": "https://api.coinbase.com/v2/prices/BTC-USD/spot",
    "OKX": "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
    "Gate.io": "https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT",
}


@st.cache_data(ttl="10m", show_spinner=False)
def probe(timeout: float = 6.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, url in ENDPOINTS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HSC-Borsa-Analiz/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(4096).decode(errors="replace")
                json.loads(body)  # geçerli JSON mu?
            rows.append({"Borsa": name, "Erişim": "OK", "Not": "API cevap verdi (anahtar gerekmez)"})
        except urllib.error.HTTPError as exc:
            rows.append({"Borsa": name, "Erişim": "HTTP", "Not": f"HTTP {exc.code} — domain'e ulaşıldı, istek reddedildi"})
        except Exception as exc:
            rows.append({"Borsa": name, "Erişim": "YOK", "Not": type(exc).__name__})
    return rows


def render() -> None:
    with st.expander("Borsa API erişim testi (hangisi çalışıyor?)", icon=":material/wifi:"):
        st.caption(
            "Anahtar gerektirmeyen herkese açık uçlara test isteği atılır. "
            "Bakiye, emir veya kişisel veri kullanılmaz. Sonuçlar 10 dk önbelleğe alınır."
        )
        if st.button("API erişimini test et", key="probe_run", icon=":material/refresh:"):
            probe.clear()
            st.rerun()
        rows = probe()
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, use_container_width=True,
            alt="Halka açık borsa API uçlarının erişilebilirlik testi",
        )
        ok = [r["Borsa"] for r in rows if r["Erişim"] == "OK"]
        st.caption(
            "Erişilebilen borsalar: " + (", ".join(ok) if ok else "hiçbiri")
            + ". Hiçbiri yoksa ağ/bölge engeli var; adapter değiştirmek çözmez."
        )
