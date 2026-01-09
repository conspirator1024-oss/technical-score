@echo off
echo Starting Stock Trend Scorer App...
echo ------------------------------------------

cd /d "%~dp0"

:: Check if .venv exists, if so activate it
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo No virtual environment found, using system Python...
)

:: Install requirements if needed (optional, un-comment if you want auto-install)
:: echo Checking requirements...
:: pip install -r requirements.txt

echo Launching Streamlit...
streamlit run app.py

pause
