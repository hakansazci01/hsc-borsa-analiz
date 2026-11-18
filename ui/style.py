"""
Modern, hafif ve erişilebilir arayüz hareketleri.

CSS yalnızca kullanıcı açıkça istediği için kullanılır ve genel Streamlit
sınıfları yerine key='...' ile oluşturulan `.st-key-*` seçicilerini hedefler.
Animasyonlar kısa, saydamlik/ölçek tabanlı ve azaltılmış hareket tercihine
(reduced-motion) saygılıdır.
"""

from __future__ import annotations

import streamlit as st


CSS = """
<style>
@keyframes softIn {
  from { opacity: 0; transform: translateY(8px) scale(0.995); }
  to   { opacity: 1; transform: none; }
}
.st-key-signal_panel,
.st-key-decision_card,
.st-key-live_market,
.st-key-pnl_panel {
  animation: softIn 380ms cubic-bezier(.2,.7,.2,1) both;
  transition: box-shadow 240ms ease, transform 240ms ease;
}
.st-key-signal_panel:hover,
.st-key-decision_card:hover,
.st-key-live_market:hover,
.st-key-pnl_panel:hover {
  box-shadow: 0 8px 28px rgba(96,165,250,.14);
  transform: translateY(-2px);
}
button {
  transition: transform 140ms ease, filter 140ms ease, box-shadow 140ms ease;
}
button:hover { transform: translateY(-1px); filter: brightness(1.08); }
button:active { transform: translateY(0); }
@media (prefers-reduced-motion: reduce) {
  .st-key-signal_panel, .st-key-decision_card,
  .st-key-live_market, .st-key-pnl_panel { animation: none; transition: none; }
  button { transition: none; }
}
</style>
"""


def inject_modern_style() -> None:
    st.html(CSS)
