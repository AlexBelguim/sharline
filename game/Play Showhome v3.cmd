@echo off
setlocal
cd /d "%~dp0"
if not exist "target\release\val_etf.exe" (
    echo Release build missing. Run cargo build --release -p val_etf from game.
    pause
    exit /b 1
)
"target\release\val_etf.exe" --host showhome_v3 --live --mode tdm
if errorlevel 1 pause
