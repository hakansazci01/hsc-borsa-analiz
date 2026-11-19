"""
Yönlendirici arayüz bileşenleri.

Kullanıcıya "nerede ne seçeceğini / bilgilerini nereye gireceğini" gösteren
küçük açılır paneller (popover), adım adım rehber penceresi ve seçimlerde
kısa animasyonlar sağlar. Analiz motorlarına dokunmaz; yalnızca arayüzdür.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


CSS = """
<style>
@keyframes hscgIn {
  from { opacity: 0; transform: translateY(12px) scale(.98); }
  to   { opacity: 1; transform: none; }
}
@keyframes hscgPop {
  0%   { opacity: 0; transform: scale(.85); }
  65%  { opacity: 1; transform: scale(1.03); }
  100% { opacity: 1; transform: scale(1); }
}
@keyframes hscgGlow {
  0%   { box-shadow: 0 0 0 0 rgba(52,211,153,.55); background: rgba(52,211,153,.20); }
  100% { box-shadow: 0 0 0 16px rgba(52,211,153,0); background: rgba(52,211,153,.05); }
}
.hscg-tour {
  animation: hscgIn .45s cubic-bezier(.2,.8,.2,1) both;
  border: 1px solid rgba(96,165,250,.35);
  border-radius: 16px; padding: 18px 20px;
  background: linear-gradient(135deg, rgba(30,41,59,.92), rgba(15,23,42,.92));
  box-shadow: 0 12px 32px rgba(2,6,23,.35);
}
.hscg-tour-head { color: #60A5FA; font-weight: 800; font-size: 15px; margin-bottom: 8px; }
.hscg-tour-body { color: #CBD5E1; font-size: 14px; line-height: 1.65; }
.hscg-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #334155; margin-right: 6px; vertical-align: middle;
}
.hscg-dot.on { background: #60A5FA; box-shadow: 0 0 10px #60A5FA; }
.hscg-flash {
  animation: hscgGlow 1.4s ease-out both;
  border: 1px solid rgba(52,211,153,.38); border-radius: 12px;
  padding: 9px 14px; color: #34D399; font-weight: 700; font-size: 14px;
  margin: 6px 0 2px;
}
.hscg-tip-title {
  display: inline-block; animation: hscgPop .4s cubic-bezier(.2,.8,.2,1) both;
  color: #93C5FD; font-weight: 800; font-size: 13px; letter-spacing: .3px;
}
.hscg-mini {
  display: inline-block; border-radius: 8px; padding: 3px 8px;
  background: rgba(96,165,250,.12); border: 1px solid rgba(96,165,250,.3);
  color: #BFDBFE; font-size: 12px; font-weight: 700; margin-right: 6px;
}
@media (prefers-reduced-motion: reduce) {
  .hscg-tour, .hscg-flash, .hscg-tip-title { animation: none; }
}
</style>
"""


def inject_guide_css() -> None:
    """Animasyon stillerini sayfaya enjekte eder (diğer sınıflarla çakışmaz)."""
    st.html(CSS)


def tip(
    title: str,
    lines: list[str],
    key: str,
    label: str = "Nasıl yapılır?",
    icon: str = ":material/help:",
) -> None:
    """Küçük bir yardım popup'ı açar; tıklayınca açılır, tekrar tıklayınca kapanır."""
    with st.popover(label, icon=icon, help=title, key=f"hscg_tip_{key}"):
        st.html(f'<div class="hscg-tip-title">{title}</div>')
        for i, line in enumerate(lines, start=1):
            st.markdown(f"{i}. {line}")
        st.caption("Kapatmak için düğmeye tekrar tıklayın.")


def flash(message: str, key: str = "hscg_flash") -> None:
    """Seçim sonrası kısa, göze çarpan bir onay animasyonu gösterir."""
    st.html(f'<div class="hscg-flash" key="{key}">✨ {message}</div>')


def tour(
    steps: list[tuple[str, str]],
    key: str = "hscg_tour",
    on_close=None,
) -> None:
    """Adım adım rehber kartı. İleri/Geri ile gezinir, noktalar ilerlemeyi gösterir."""
    if not steps:
        return
    state_key = f"{key}_idx"
    idx = int(st.session_state.get(state_key, 0) or 0)
    idx = max(0, min(idx, len(steps) - 1))

    title, body = steps[idx]
    dots = "".join(
        f'<span class="hscg-dot {"on" if i == idx else ""}"></span>'
        for i in range(len(steps))
    )
    st.html(
        f'<div class="hscg-tour">'
        f'<div class="hscg-tour-head">Adım {idx + 1} / {len(steps)} · {title}</div>'
        f'<div class="hscg-tour-body">{body}</div>'
        f'<div style="margin-top:12px">{dots}</div>'
        f"</div>"
    )

    c1, c2, c3 = st.columns([1, 1, 1.4], gap="small")
    with c1:
        if st.button("← Geri", key=f"{key}_prev", disabled=idx == 0, use_container_width=True):
            st.session_state[state_key] = idx - 1
            st.rerun()
    with c2:
        if st.button(
            "İleri →", key=f"{key}_next", disabled=idx == len(steps) - 1,
            use_container_width=True,
        ):
            st.session_state[state_key] = idx + 1
            st.rerun()
    with c3:
        if st.button("Anladım, kapat", key=f"{key}_close", type="primary", use_container_width=True):
            st.session_state[state_key] = 0
            if on_close is not None:
                on_close()
            st.toast("Rehber kapandı. İstediğiniz zaman tekrar açabilirsiniz.", icon=":material/check:")
            st.rerun()


def guide_button(steps: list[tuple[str, str]], label: str = "Rehber", key: str = "hscg_guide") -> None:
    """Rehberi modal pencerede açan düğme (adımlar arasında açık kalır)."""
    open_key = f"{key}_open"

    def _mark_closed() -> None:
        st.session_state[open_key] = False

    @st.dialog("Adım adım rehber", width="large", on_dismiss=_mark_closed)
    def _dialog() -> None:
        st.caption("Bu rehber hiçbir ayarı değiştirmez; sadece nereye ne gireceğinizi gösterir.")
        tour(steps, key=f"{key}_tour", on_close=_mark_closed)

    if st.button(label, icon=":material/school:", key=key, type="primary"):
        st.session_state[open_key] = True
        st.rerun()
    if st.session_state.get(open_key):
        _dialog()


def guide_steps() -> list[tuple[str, str]]:
    """Uygulamanın genel kullanım akışını anlatan adımlar."""
    return [
        (
            "Kayıt ol / Giriş yap",
            "İlk açılışta <b>Kayıt ol</b> sekmesinden bir kullanıcı adı ve en az 10 karakterli "
            "şifre belirleyin. <b>Güçlü şifre öner</b> düğmesi güvenli bir şifre üretir. "
            "Sonraki açılışlarda <b>Giriş yap</b> sekmesinden aynı bilgilerle girin. "
            "Şifreniz tuzlu PBKDF2 ile hash'lenir, düz metin saklanmaz.",
        ),
        (
            "İzleme listesini oluştur",
            "<b>Ayarlar</b> sayfasındaki <b>İzleme listesi</b> alanından hisse ekleyin "
            "(örn. THYAO, GARAN). BIST tarayıcı sayfasından da 804 şirket arasında arama yapabilirsiniz.",
        ),
        (
            "Piyasa durumunu oku",
            "<b>Akıllı Panel</b> açılışta BIST 100 rejimini gösterir. Renkli rozete bakın: "
            "yeşil yükseliş, kırmızı düşüş, sarı yatay, turuncu oynak. Size önerilen yöntemi "
            "ve 'Bugün ne yapmalı?' önerisini okuyun.",
        ),
        (
            "Kararı ver ve işlemi kurgula",
            "Hisse seçin; <b>AL / BEKLE / SAT</b> kartı, güven skoru ve sade gerekçe görünür. "
            "Giriş, stop ve hedef seviyeleri hazırdır. Yalnızca seans içinde ve AL sinyalinde "
            "<b>Kurgusal pozisyon aç</b> düğmesi aktif olur — gerçek emir gönderilmez.",
        ),
        (
            "Sonuçları takip et",
            "Pozisyonu <b>Hesabım</b> sayfasından kapattığınızda sonuç otomatik olarak "
            "<b>Sinyal performansı</b> defterine R çarpanıyla işlenir. Kazanma oranı, net R "
            "ve kümülatif eğriyi oradan izleyin.",
        ),
    ]


def render_global_guide() -> None:
    """Her sayfada görünen kompakt rehber düğmesi + kullanıcı bilgisi popup'ı."""
    inject_guide_css()
    with st.container(horizontal=True, horizontal_alignment="right"):
        tip(
            "Üstteki İngilizce menü nerede?",
            [
                "**Rerun / yeniden çalıştır:** Anlık sinyal sayfasındaki *Verileri yenile* düğmesini kullanın.",
                "**Clear cache / önbelleği temizle:** Piyasa analizi sayfasındaki *Verileri yenile* aynı işi yapar.",
                "**Print / Record screen:** Tarayıcınızın Ctrl+P yazdırma ve ekran kayıt araçlarını kullanın.",
                "**Deploy / yayınla:** Uygulama yerel çalışır; bu seçenek gerekli değildir. İngilizce menü Streamlit'e aittir; Türkçe arayüz için gizlendi.",
            ],
            key="streamlit_menu",
            label="Üst menü",
        )
        tip(
            "Kullanıcı bilgilerini nereye girmeli?",
            [
                "**Kayıt ol:** Üstteki Kayıt ol sekmesinde kullanıcı adı (3-32 karakter) ve şifre (en az 10 karakter) yazın.",
                "**Giriş yap:** Sonraki açılışlarda Giriş yap sekmesinden aynı kullanıcı adı ve şifreyi kullanın.",
                "**Şifre öner:** Güçlü şifre üretmek için Kayıt ol sekmesindeki düğmeye basın.",
                "**Verileriniz:** Ayarlar, kurgusal portföy ve sinyal geçmişi bu kullanıcıya özel saklanır; şifre düz metin tutulmaz.",
            ],
            key="global_userinfo",
            label="Kullanıcı bilgileri",
        )
        guide_button(guide_steps(), label="Rehber", key="global_guide")
