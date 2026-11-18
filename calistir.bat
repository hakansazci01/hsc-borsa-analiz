@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo [HATA] Sanal ortam veya Streamlit bulunamadi.
    echo Once su komutlari calistirin:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo   HKC BORSA ANALIZ - Akilli Sinyal Paneli
echo ============================================================
echo   Tarayici otomatik acilmazsa: http://localhost:8501
echo   Kapatmak icin bu pencerede Ctrl+C tuslarina basin.
echo ============================================================
echo.

".venv\Scripts\streamlit.exe" run streamlit_app.py --server.port 8501
pause
