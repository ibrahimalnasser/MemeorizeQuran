@echo off
REM Quran Hifz Platform - Startup Script for Windows
REM For local development

echo Starting Quran Memorization Platform...

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/update requirements
echo Installing requirements...
pip install -r requirements.txt

REM Start Streamlit
echo Starting Streamlit on port 8501...
streamlit run app.py

pause
