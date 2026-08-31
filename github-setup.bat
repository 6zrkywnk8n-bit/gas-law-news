@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  GitHub への初回登録
echo  ----------------------------------------
echo  先に GitHub で空のリポジトリを作ってください。
echo  そのページの URL を貼り付けて Enter を押します。
echo  例: https://github.com/yourname/gas-law-news
echo.
set /p REPO="URL: "
if "%REPO%"=="" echo URL が空です。 & pause & exit /b 1
git remote remove origin 2>nul
git remote add origin "%REPO%"
git branch -M main
echo.
echo  送信します。初回はブラウザで GitHub のログイン画面が出ます。
git push -u origin main
echo.
pause
