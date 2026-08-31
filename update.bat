@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  保安法令ニュース を更新しています...
echo.
python main.py %*
if errorlevel 1 (
  echo.
  echo  エラーが発生しました。上のメッセージをご確認ください。
  pause
)
