"""
Simülasyon/istatistik yöntemlerinin şeffaf açıklaması.

Buradaki rastgelelik **piyasa verisi üretmek için değil**, gerçek veriden
hesaplanmış sonuçların ne kadar şansa bağlı olabileceğini ölçmek içindir.
Kullanıcıya girdinin kaynağı, örneklem büyüklüğü ve sınırlar açıkça gösterilir.
"""

from __future__ import annotations

import streamlit as st


def simulation_notes(
    title: str,
    source: str,
    sample: str,
    limit: str,
) -> None:
    with st.expander(title, icon=":material/science:"):
        st.markdown(
            f"""
**Girdi kaynağı (gerçek):** {source}

**Örneklem:** {sample}

**Rastgeleliğin amacı:** Gerçek veriden hesaplanmış sonucun şans eseri ortaya çıkma
olasılığını ölçmek veya olası senaryoların *dağılımını* görmektir. **Piyasa verisi
üretilmez**; fiyatlar, işlemler ve getiriler gerçek kayıtlardan gelir.

**Sınır:** {limit}

Bu bir olasılık/senaryo aracıdır; tek bir tahmin veya yatırım tavsiyesi değildir.
"""
        )
