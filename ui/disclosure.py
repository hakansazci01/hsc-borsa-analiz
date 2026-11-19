"""
İlk kullanım metodoloji ve sınır bildirimi.

Finansal karar destek araçlarında güven, "ystaviyesi değildir" yazısını
bir yere gömmkle değil; veri kaynağını, gecikmeyi ve sistemin yapamayacaklarını
kullanıcı ilk kararla karşılaşmadan önce açıkça söylemekle kurulur.
Kabul kaydı yerel denetim günlüğüne yazılır.
"""

from __future__ import annotations

import streamlit as st

from ui import audit_log, auth


MARKER = "disclosure_accepted.json"


def _marker_path(username: str):
    return auth.user_dir(username) / MARKER


def render_once(username: str) -> None:
    """İlk girişte bir kez gösterilir; 'Anladım' ile kabul kaydedilir."""
    if _marker_path(username).exists():
        return

    @st.dialog("Başlamadan önce — bu sistem ne yapar, ne yapmaz?", width="large")
    def _dialog() -> None:
        st.markdown(
            """
**HSC Borsa Analiz**, BIST hisseleri için *karar destek* amaçlı, **kurgusal (paper)** bir analiz panelidir.

- **Gerçek emir göndermez**, aracı kuruma bağlanmaz, para hareketi yapmaz.
- **Yatırım tavsiyesi vermez.** Gördüğünüz AL / BEKLE / SAT etiketleri teknik ve istatistiksel bir yorumdur.
- Ücretsiz veri kaynakları **yaklaşık 15 dakika gecikmelidir**; canlı fiyat ve anlık emir akışı yoktur.
- Koşullar uymuyorsa sistem **BEKLE** der; sizi harekete geçirmek için sinyal uydurmaz.
- Bekleme süreleri oynaklık temelli **yaklaşık aralıklardır**, garanti değildir.
- Geçmiş performans ve backtest sonuçları **gelecek getiriyi göstermez**.
- Tüm kararlar, kullanılan veri ve doğrulama sonucuyla birlikte yerel denetim kaydına yazılır.

Kabul ederek bu sınırları okuduğunuzu ve anladığınızı bildiriyorsunuz.
"""
        )
        if st.button("Anladım, devam et", type="primary", key="disclosure_accept", width="stretch"):
            auth.write_json(_marker_path(username), {"accepted_at": auth._now()})
            audit_log.append(username, "BILGILENDIRME_KABUL", {
                "decision": "KABUL",
                "source": "yerel",
                "idempotency_key": f"disclosure|{username}",
            })
            st.toast("Bilgilendirme kabul edildi. İyi analizler.", icon=":material/check:")
            st.rerun()

    _dialog()
