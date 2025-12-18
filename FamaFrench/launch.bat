@echo off
:: 切換到這支 .bat 檔案所在的資料夾 (確保路徑正確)
cd /d "%~dp0"

echo ========================================================
echo   正在啟動股票因子分析儀 (Stock Factor DNA) ...
echo   檔案路徑: %CD%
echo ========================================================

:: 1. 自動開啟預設瀏覽器並前往 localhost:8000
echo 正在開啟瀏覽器...
timeout /t 1 >nul
start http://localhost:8000

:: 2. 啟動 Python 本地伺服器
echo 伺服器運行中... (請勿關閉此視窗)
python -m http.server 8000

pause