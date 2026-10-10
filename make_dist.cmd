@echo off
rem Build the game and put a playable copy in dist\ next to this script:
rem   dist\SHARDLINE.exe, dist\assets\, dist\README.txt
rem Double-click it, or run "make_dist.cmd". "make_dist.cmd nobuild" only refreshes dist from the last build.
rem dist\ is not committed (.gitignore). Zip the dist folder to send the game to a friend.
setlocal
cd /d "%~dp0"

if /i not "%~1"=="nobuild" (
    echo Building the release exe ^(cargo build --release -p val_etf^)...
    pushd game
    cargo build --release -p val_etf
    if errorlevel 1 (
        popd
        echo.
        echo Build failed, see above. dist was not changed.
        pause
        exit /b 1
    )
    popd
)

if not exist "game\target\release\val_etf.exe" (
    echo No release build found. Run make_dist.cmd without "nobuild".
    pause
    exit /b 1
)

if not exist "dist" mkdir "dist"
copy /y "game\target\release\val_etf.exe" "dist\SHARDLINE.exe" >nul
if errorlevel 1 (
    echo Could not copy the exe. Is SHARDLINE.exe still running from dist?
    pause
    exit /b 1
)

rem Mirror the assets (removes files deleted from game\assets). Local-only test props stay out.
robocopy "game\assets" "dist\assets" /MIR /XD _tests /XF test_props.ron /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo Copying the assets failed.
    pause
    exit /b 1
)

> "dist\README.txt" (
    echo SHARD/LINE prototype
    echo.
    echo Run SHARDLINE.exe. Keep the assets folder next to it.
    echo Windows may warn that the app is unrecognised because it is not signed: More info, then Run anyway.
    echo To join a friend: PLAY, JOIN GAME, paste their invite code. To host: PLAY, HOST GAME.
    echo Settings are saved in %%APPDATA%%\shardline.
)

echo.
echo Done: %~dp0dist
echo   SHARDLINE.exe + assets\ + README.txt
if /i not "%~2"=="nopause" pause
