@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   HSC BORSA ANALIZ - Akilli Sinyal Paneli
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [HATA] Sistemde Python bulunamadi.
    echo Lutfen https://www.python.org/downloads/ adresinden Python 3.10+ kurun.
    echo Kurulum sirasinda "Add Python to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo [HATA] Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\streamlit.exe" (
    echo [2/2] Paketler yukleniyor ^(ilk calismada biraz surebilir^)...
    .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [HATA] Paketler yuklenemedi. Internet baglantinizi kontrol edin.
        echo Elle denemek icin: .venv\Scripts\pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Hazir. Tarayici otomatik acilmazsa: http://localhost:8501
echo Kapatmak icin bu pencerede Ctrl+C tuslarina basin.
echo ============================================================
echo.

.venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501
pause
