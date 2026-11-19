"""
Streamlit'in yerleşik İngilizce arayüz metinlerini Türkçeye çevirir.

Streamlit bu etiketleri derlenmiş ön yüzde sabit tuttuğu için resmi API ile
çeviri yapılamaz. Bu modül, tarayıcıda çalışan küçük bir gözlemci
(MutationObserver) ile menü/toolbar metinlerini anlık olarak değiştirir.
Düğmelerin işlevi (yeniden çalıştırma, önbellek temizleme, yazdırma vb.)
korunur; yalnızca görünen yazı Türkçeleştirilir.
"""

from __future__ import annotations

import streamlit as st


_JS = r"""
<script>
(function () {
  if (window.__hscTrInstalled) return;
  window.__hscTrInstalled = true;

  // Uzun ifadeler önce: "Auto rerun" içindeki "rerun" yanlışlıkla
  // "Yeniden çalıştır" olmasın diye sıralama önemlidir.
  var RULES = [
    ['Auto rerun', 'Otomatik yenile'],
    ['Clear cache', 'Önbelleği temizle'],
    ['Record screen', 'Ekranı kaydet'],
    ['Get help', 'Yardım al'],
    ['Report a Bug', 'Hata bildir'],
    ['Report a bug', 'Hata bildir'],
    ['Main menu', 'Ana menü'],
    ['Rerun', 'Yeniden çalıştır'],
    ['Deploy', 'Yayınla'],
    ['Print', 'Yazdır'],
    ['About', 'Hakkında'],
    ['Theme', 'Tema'],
    ['Settings', 'Ayarlar']
  ];

  function tr(s) {
    if (!s || typeof s !== 'string') return s;
    var trimmed = s.trim();
    for (var i = 0; i < RULES.length; i++) {
      if (s.indexOf(RULES[i][0]) !== -1) {
        s = s.split(RULES[i][0]).join(RULES[i][1]);
      }
    }
    // Üst sayfa menüsündeki taşma düğmesi: "10 more" -> "10 sayfa daha"
    if (trimmed.endsWith(' more')) {
      var num = trimmed.slice(0, -5).trim();
      if (num && !isNaN(Number(num))) {
        s = s.replace(trimmed, num + ' sayfa daha');
      }
    }
    return s;
  }

  function apply(root) {
    if (!root || !root.querySelectorAll) return;
    // Sürüm satırı React'te iki metin düğümüne bölünür ("Made with Streamlit v"
    // + "1.67.0"); bu yüzden öğe düzeyinde, tam metin üzerinden çevrilir.
    var leaves = root.querySelectorAll('*');
    for (var k = 0; k < leaves.length; k++) {
      var leaf = leaves[k];
      if (leaf.tagName === 'SCRIPT' || leaf.tagName === 'STYLE') continue;
      if (leaf.children && leaf.children.length !== 0) continue;
      var full = (leaf.textContent || '').trim();
      var vp = 'Made with Streamlit ';
      if (full.indexOf(vp) === 0) {
        var ver = full.substring(vp.length);
        var raw = ver.substring(1);
        if (ver.indexOf('v') === 0 && /^[0-9.]+$/.test(raw)) {
          leaf.textContent = 'Streamlit ' + ver + ' ile hazırlandı';
        }
      }
    }
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var n;
    while ((n = walker.nextNode())) {
      var p = n.parentElement;
      if (p && (p.tagName === 'SCRIPT' || p.tagName === 'STYLE')) continue;
      var v = n.nodeValue;
      if (!v || !v.trim()) continue;
      var nv = tr(v);
      if (nv !== v) n.nodeValue = nv;
    }
    var els = root.querySelectorAll('[title], [aria-label], [aria-description]');
    for (var j = 0; j < els.length; j++) {
      if (els[j].tagName === 'SCRIPT' || els[j].tagName === 'STYLE') continue;
      ['title', 'aria-label', 'aria-description'].forEach(function (attr) {
        var val = els[j].getAttribute(attr);
        if (val) {
          var nv2 = tr(val);
          if (nv2 !== val) els[j].setAttribute(attr, nv2);
        }
      });
    }
  }

  apply(document.body);

  var observer = new MutationObserver(function () {
    observer.disconnect();
    apply(document.body);
    observer.observe(document.body, {
      childList: true, subtree: true, characterData: true
    });
  });
  observer.observe(document.body, {
    childList: true, subtree: true, characterData: true
  });
})();
</script>
"""


def install() -> None:
    """Türkçe arayüz çeviricisini sayfaya kurar (her yeniden çalıştırmada güvenli)."""
    st.html(_JS, unsafe_allow_javascript=True)
