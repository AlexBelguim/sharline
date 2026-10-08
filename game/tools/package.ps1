# Package the game for a friend: the release exe plus game/assets, zipped (about 60-80 MB). The build folder
# (target/, several GB) is not needed to play.
#
#   powershell -ExecutionPolicy Bypass -File game/tools/package.ps1
#
# Build first: cargo build --release -p val_etf [--target x86_64-pc-windows-msvc]. The newest of the two
# release exes is used. Output: game/target/dist/SHARDLINE-<date>.zip (target/ is not committed).
$ErrorActionPreference = "Stop"
$game = Split-Path -Parent $PSScriptRoot
$candidates = @(
    "$game/target/x86_64-pc-windows-msvc/release/val_etf.exe",
    "$game/target/release/val_etf.exe"
) | Where-Object { Test-Path $_ } | ForEach-Object { Get-Item $_ } | Sort-Object LastWriteTime -Descending
if (-not $candidates) { throw "No release build found. Run: cargo build --release -p val_etf" }
$exe = $candidates[0]
Write-Host "exe: $($exe.FullName) ($([math]::Round($exe.Length / 1MB)) MB, built $($exe.LastWriteTime))"

$dist = "$game/target/dist"
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$folder = "$dist/SHARDLINE"
if (Test-Path $folder) { Remove-Item -Recurse -Force $folder }
New-Item -ItemType Directory -Force $folder | Out-Null
Copy-Item $exe.FullName "$folder/SHARDLINE.exe"
# The game finds an `assets` folder next to the exe (config::assets_root).
Copy-Item -Recurse "$game/assets" "$folder/assets"
@"
SHARD/LINE (prototype)

Run SHARDLINE.exe. Keep the 'assets' folder next to it.
Windows may warn that the app is unrecognised (it is not signed): More info > Run anyway.
To join a friend: PLAY > JOIN GAME, paste their invite (SL1-...). To host: PLAY > HOST GAME.
Settings (keys, mouse, video) are in SETTINGS; they are saved in %APPDATA%\shardline.
"@ | Set-Content -Encoding utf8 "$folder/README.txt"

$zip = "$dist/SHARDLINE-$stamp.zip"
Compress-Archive -Path $folder -DestinationPath $zip -CompressionLevel Optimal -Force
Write-Host "zip: $zip ($([math]::Round((Get-Item $zip).Length / 1MB)) MB)"
