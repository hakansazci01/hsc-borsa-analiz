"""
Arayüzdeki fare-üzerine açıklamaların (tooltip) tek kaynağı.

Amaç: Kullanıcı bir değeri veya ayarı gördüğünde "bu neyi ifade ediyor,
neden işaretledim / neden bu değeri seçtim" sorusunu anında yanıtlamak.
"""

TOOLTIPS: dict[str, str] = {
    # ---- Genel sinyal kavramları ----
    "score": (
        "Sinyal puanı -5 (güçlü SAT) ile +5 (güçlü AL) arasında değişir. "
        "RSI, MACD, trend, Bollinger, Stokastik, OBV ve VWAP göstergelerinin "
        "ağırlıklı toplamıdır. Kuramsal aralık -5..+5 olsa da göstergelerin bir kısmı kesirli puan "
        "verdiği için pratik aralık yaklaşık -4,8..+4,8'dir. Eşikleri Ayarlar sayfasından değiştirebilirsiniz."
    ),
    "confidence": (
        "Güven skoru (0-100) sinyalin ne kadar tutarlı olduğunu gösterir. "
        "Sinyal gücü, göstergelerin birbirini onaylaması ve geçmiş test "
        "performansı birleştirilerek hesaplanır. Yüksek değer daha fazla onay demektir; "
        "kazanç garantisi değildir."
    ),
    "signal": (
        "Karar motorunun hissenin yönü için ürettiği etikettir: "
        "Güçlü AL, AL, NÖTR, SAT veya Güçlü SAT. Puan eşiklerini Ayarlar'dan belirlersiniz."
    ),
    "rsi": (
        "Göreli Güç Endeksi (14 gün). 30 altı aşırı satım (AL yönü), 70 üstü "
        "aşırı alım (SAT yönü) kabul edilir. Bu eşikleri Ayarlar'dan değiştirebilirsiniz."
    ),
    "macd": (
        "Hareketli Ortalama Yakınsama/Iraksama göstergesi. Sinyal çizgisini yukarı "
        "kesmesi AL, aşağı kesmesi SAT yönü olarak yorumlanır. Histogram pozitifse "
        "yükseliş eğilimi vardır."
    ),
    "last_close": "Son kapanış fiyatı. Günlük veride bir önceki tamamlanmış seansın kapanışıdır.",
    "volume": (
        "İşlem hacmi: o gün el değiştiren hisse adedi. Artan hacimle gelen fiyat "
        "hareketi, sinyalin daha güvenilir olmasına yardımcı olur (OBV onayı)."
    ),
    "change_pct": "Son fiyatın günlük açılışa göre yüzde değişimi. Seans kapalıysa son tamamlanmış günü gösterir.",
    "session": (
        "Piyasa seansı durumu. 'out_of_session' piyasanın kapalı olduğu, "
        "'regular' seansın açık olduğu anlamına gelir. Kapalıyken görülen fiyat son kotasyondur."
    ),
    "quote_source": (
        "Fiyatın geldiği kaynak. TradingView WebSocket hızlı canlı akıştır; "
        "yedek mod yavaş ama güvenilir bir sorgulamayı gösterir."
    ),
    "regime": (
        "Piyasa rejimi: Yükseliş, Düşüş, Yatay veya Yüksek oynaklık. "
        "Rejim belirlenirken trend eğimi, momentum ve oynaklık kümeleri kullanılır. "
        "Rejim, kararın güvenini ve önerilen pozisyon büyüklüğünü otomatik ayarlar."
    ),
    "regime_confidence": "Rejim tespitinin ne kadar net olduğunu gösterir (0-100). Düşükse piyasa karmaşık bir dönemdedir.",
    "trend_score": "Trend skoru -2 ile +2 arasında. Pozitif değer yükseliş düzeni, negatif değer düşüş düzeni anlamına gelir.",
    "volatility": (
        "Yıllıklandırılmış oynaklık yüzdesi. Yüksek oynaklıkta fiyat daha sert "
        "hareket eder; risk yönetimi pozisyonu otomatik küçültür."
    ),
    "timeframe": (
        "Zaman dilimi. Kısa dilimler (1m-15m) anlık hareketi, uzun dilimler (1d-1M) "
        "ana eğilimi gösterir. Strateji seçimi hangi dilimlerin daha ağırlıklı olacağını belirler."
    ),
    "news_impact": (
        "KAP başlığındaki ifadelerin olumlu/olumsuz sözlük analizi sonucu. "
        "Yeni haberler daha ağırlıklıdır. Bu bir duyarım tahminidir, yorum değildir."
    ),
    # ---- Ayarlar ----
    "symbols": (
        "İzleme listeniz. Piyasa analizi ve portföy testi bu hisseleri tarar. "
        "BIST hisseleri için '.IS' eki kullanılır (örn. THYAO.IS)."
    ),
    "period": "Analiz için indirilen geçmiş verinin uzunluğu. Uzun dönüm daha fazla örnek, kısa dönüm daha güncel veri verir.",
    "interval": "Veri çözünürlüğü. 1d günlük, 1wk haftalık bardır. Günlük, sinyal gürültüsünü azalttığı için önerilir.",
    "profile": (
        "Risk profili. Temkinli yüksek onay ister ve küçük pozisyon alır; Dengeli "
        "standart ayardır; Atak daha erken giriş yapar ve pozisyonu büyütür."
    ),
    "strong_buy": "Puan bu değerin üzerine çıkarsa sinyal 'Güçlü AL' olarak sınıflandırılır. Yükseltmek sinyali daha seçici yapar.",
    "buy": "Puan bu eşiğin üzerindeyse 'AL' sinyali üretilir. Düşürmek daha çok AL sinyali oluşturur.",
    "sell": "Puan bu eşiğin altındaysa 'SAT' sinyali üretilir.",
    "strong_sell": "Puan bu değerin altına düşerse 'Güçlü SAT' sinyali üretilir.",
    "rsi_oversold": "RSI'in bu değerin altına düşmesi aşırı satım kabul edilir ve AL puanı eklenir.",
    "rsi_overbought": "RSI'in bu değerin üstüne çıkması aşırı alım kabul edilir ve SAT puanı eklenir.",
    "weight": (
        "Göstergenin sinyal puanındaki etkisini ayarlar. Ağırlığı artırmak o göstergeyi "
        "karar üzerinde daha belirleyici yapar; 0'a çekmek devre dışı bırakır."
    ),
    "capital": "Backtest ve önerilerde kullanılan kurgusal başlangıç sermayesi. Gerçek hesabınızı etkilemez.",
    "position_size": "Her işlemde sermayenin yüzde kaçının kullanılacağı. Yüksek değer getiriyi de riski de artırır.",
    "stop_loss": "Zarar kesme (stop-loss) yüzdesi. Pozisyon bu kadar zarar ederse kurgusal olarak kapatılır.",
    "take_profit": "Kar alma hedefi yüzdesi. Fiyat bu kadar yükselirse pozisyon kapatılır.",
    "max_positions": "Aynı anda açık tutulabilecek en fazla pozisyon sayısı. Riski dağıtır.",
    "commission": "Her alım/satımda kesilen kurgusal işlem komisyonu oranı.",
    "save_settings": "Değişiklikleri bu tarayıcıda kalıcı kaydeder ve analizleri yeni ayarlarla yeniden hesaplar.",
    "reset_settings": "Tüm ayarları fabrika varsayılanlarına döndürür ve kayıtlı ayar dosyasını siler.",
    # ---- Canlı işlem / bot ----
    "strategy": (
        "Hangi zaman dilimlerinin kararda daha etkili olacağını belirler. "
        "Kısa vadeli gün içi hareketi, Uzun vadeli ana trendi öne çıkarır."
    ),
    "news_weight": "KAP haberlerinin karar skorundaki ağırlığı. Artırmak haberlere daha fazla önem verir.",
    "auto_refresh": "Açıkken veriler 60 saniyede bir otomatik yenilenir. Kapatırsanız yalnızca siz yenilersiniz.",
    "instant_analysis": "Önbelleği temizleyip hisseyi sıfırdan analiz eder. Fiyat güncel değilse bunu kullanın.",
    "bist_search": (
        "BIST'te kayıtlı 804 şirket arasından sembol veya şirket adıyla arama yapın. "
        "Örn. 'THYAO' veya 'banka'."
    ),
    "bot_chat": "Hisse sembolü veya şirket adı yazın. Bot gerçek verilerle AL/BEKLE/SAT kararını gerekçesiyle döndürür.",
    "kelly": (
        "Kelly kriteri, kazanma oranı ve ortalama kazanç/kayıp oranına göre "
        "uzun vadede büyümeyi optimize eden risk payını verir. Aşırı riski önlemek "
        "için yarım Kelly ve yüzde 2 sert tavan uygulanır."
    ),
    "monte_carlo": (
        "Geçmiş işlem getirileri rastgele yeniden örneklenerek binlerce olası gelecek "
        "senaryosu üretir. Tek bir tahmin değil, olasılık dağılımı gösterir."
    ),
    "var95": "Riske maruz değer (%95): 100 senaryodan 5'inde kaybın bu değerden kötü olması beklenir.",
    "cvar95": "Beklenen kayıp (%95): en kötü yüzde 5'lik senaryonun ortalama kaybı. VaR'dan daha temkinli bir ölçüdür.",
    "diversification": "Çeşitlendirme skoru yüksekse hisseler birlikte hareket etmiyor demektir. Düşükse portföy tek bir risk yaşıyor.",
    "correlation": "İki hissenin birlikte hareket etme derecesi. 1 aynı yönde, -1 ters yönde, 0 ilişkisiz anlamına gelir.",
    "risk_contribution": "Her hissenin toplam portföy riskine katkısı. Yüksek katkı, o hissenin portföyü daha fazla etkilediğini gösterir.",
    "distribution": "Monte Carlo senaryolarının getiri dağılımı. Eğrinin sol kuyruğu büyük kayıp olasılığını gösterir.",
    "simulations": "Kaç olası senaryo üretileceği. Daha yüksek değer daha kararlı dağılım verir, biraz daha uzun sürer.",
    "equity_curve": "Backtest boyunca kurgusal sermayenin değişimi. Düşüşler işlem stratejisinin riskini gösterir.",
    "win_rate": "Kazanan işlemlerin tüm kapanmış işlemlere oranı. Tek başına yeterli değildir; kazanç/kayıp oranıyla birlikte okunmalıdır.",
    "max_drawdown": "Zirveden dibe görülen en büyük yüzde düşüş. Stratejinin dayanıklılığını gösterir.",
    "recommendation": "O zaman dilimindeki teknik göstergelerin AL/SAT oyları. Çoklu dilimler birbirini onaylarsa sinyal güçlenir.",
    "news": "KAP ve şirket duyuruları. Olumlu/olumsuz etiketi başlıktaki ifadelerin sözlük analizinden gelir.",
    "trades": "Backtest sırasında giriş ve çıkışların listesi. Gerçek emir değildir, simülasyondur.",
    "ntfy": (
        "ntfy.sh ücretsiz ve hesapsız bir push bildirim servisidir. Sistem bir konu adı üretir; "
        "siz https://ntfy.sh/<konu> adresini tarayıcıda açıp abone olursunuz. Telegram erişimi "
        "yoksa en kolay alternatiftir. Konu adı tahmin edilemez olduğu için güvenlidir."
    ),
    "email": (
        "E-posta bildirimi için Gmail 'Uygulama Şifresi' gerekir; normal Gmail şifreniz çalışmaz. "
        "Google hesabınızda 2 adımlı doğrulamayı açıp 'App passwords' bölümünden 16 haneli bir "
        "şifre oluşturun. Bu şifre secrets.toml içinde saklanır."
    ),
    "telegram": (
        "Otomatik tarama sonucunda AL veya SAT sinyali olduğunda Telegram botunuz üzerinden "
        "bildirim gönderir. Bot token'ı @BotFather'dan, chat id'niz @userinfobot'tan alınır. "
        "Anahtarlar secrets.toml içinde saklanır ve arayüzde gösterilmez."
    ),
    "sharpe": "Sharpe oranı: birim toplam risk (volatilite) başına elde edilen getiri. 1 üzeri iyi, 2 üzeri güçlü kabul edilir.",
    "sortino": "Sortino oranı: yalnızca aşağı yönlü volatiliteyi cezalandırır. Asimetrik stratejilerde Sharpe'tan daha anlamlıdır.",
    "calmar": "Calmar oranı: yıllık getirinin maksimum düşüşe oranı. Kurumsal yatırımcıların en çok baktığı risk/getiri ölçülerinden biridir.",
    "profit_factor": "Toplam kazançların toplam kayıplara oranı. 1'in altında strateji komisyonlar hariç zarar ediyor demektir.",
    "benchmark": "BIST 100 endeksinin aynı dönemdeki al-sat tutuş getirisi. Stratejinin endeksi yenip yenemediğini gösterir.",
    "schedule": (
        "Uygulama açıkken izleme listenizin otomatik taranma aralığı. Seans başı/sonu seçenekleri "
        "hafta içi günler için geçerlidir. Gerçek zamanlayıcı için sunucu arka plan servisi gerekir."
    ),
    "api_key_editor": (
        "Yeni anahtarı buraya yazın. Mevcut değer güvenlik için gösterilmez; alanı boş bırakırsanız "
        "eski değer korunur. Kaydedilen değer yalnızca bu makinedeki secrets.toml dosyasına yazılır."
    ),
    "guards": (
        "Art arda zarar veya aşırı drawdown durumunda işlem açılmasını geçici olarak durduran "
        "kurallardır. Cooldown zarar sonrası bekleme, StoplossGuard sık stop sonrası duraklama, "
        "günlük limit o günün zarar sınırı, drawdown kademeleri ise sermaye zirvesinden düşüşe göre pozisyon küçültür."
    ),
    "order_ticket": (
        "Sinyalin broker ekranına elle girilmesi için hazırlanmış taslaktır. "
        "Adet ve tutar kurgusal sermayeye göre hesaplanır; gerçek emir gönderilmez, "
        "gönderim tamamen sizin kontrolünüzdedir."
    ),
    "disclaimer": "Bu panel teknik analiz ve karar desteği içindir; yatırım tavsiyesi değildir ve aracı kuruma emir göndermez.",
}


def h(key: str) -> str:
    """Tooltip metnini döndürür; bilinmeyen anahtar boş string üretmez."""
    return TOOLTIPS.get(key, "")
