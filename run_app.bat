@echo off
cd /d "%~dp0"

echo ========================================================
echo      Setting up Paris Trader Pro Environment...
echo ========================================================

:: 1. 設定您提供的 Python 絕對路徑 (注意：路徑中不要有空格，若有需加引號)
set PY_PATH=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe

:: 2. 檢查 Python 是否存在
if not exist "%PY_PATH%" (
    echo [ERROR] Python not found at: %PY_PATH%
    echo Please check the path again.
    pause
    exit
)

echo Using Python at: %PY_PATH%

:: 3. 自動安裝/檢查必要庫 (Streamlit, Pandas, yfinance, option_menu)
echo Checking dependencies...
"%PY_PATH%" -m pip install streamlit pandas yfinance streamlit-option-menu

:: 4. 啟動 Streamlit
echo.
echo ========================================================
echo      Launching App...
echo ========================================================
"%PY_PATH%" -m streamlit run app.py

:: 如果執行結束或報錯，暫停畫面
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application crashed or failed to start.
    pause
)