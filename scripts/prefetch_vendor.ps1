param(
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $ROOT "vendor" }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

Write-Host "[1/3] ActivityWatch zip"
Invoke-WebRequest `
  -Uri "https://ghfast.top/https://github.com/ActivityWatch/activitywatch/releases/latest/download/activitywatch-v0.13.2-windows-x86_64.zip" `
  -OutFile (Join-Path $OutDir "activitywatch.zip") `
  -UseBasicParsing

Write-Host "[2/3] FFmpeg zip"
Invoke-WebRequest `
  -Uri "https://ghfast.top/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" `
  -OutFile (Join-Path $OutDir "ffmpeg.zip") `
  -UseBasicParsing

Write-Host "[3/3] Screenpipe npm binary"
$env:npm_config_registry = "https://registry.npmmirror.com"
npx @screenpipe/cli-win32-x64 --version | Out-Null

Write-Host "done"
