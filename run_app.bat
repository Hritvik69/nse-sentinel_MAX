@echo off
cd /d C:\Users\HP\Downloads\NSE SENTINAL

call .venv\Scripts\activate
start "" streamlit run app.py
timeout /t 3 >nul
start "" http://localhost:8501