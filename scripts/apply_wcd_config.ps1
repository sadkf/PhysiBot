# 用 feat_wcd 的模板覆盖本地 physi-data/config.yaml（便于重置为仓库内开发默认）
# 用法: powershell -ExecutionPolicy Bypass -File scripts\apply_wcd_config.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $Root "physi-data\config.wcd.yaml"
$dst = Join-Path $Root "physi-data\config.yaml"
if (-not (Test-Path $src)) {
    Write-Host "未找到 physi-data\config.wcd.yaml（仅在 feat_wcd 分支存在）" -ForegroundColor Red
    exit 1
}
Copy-Item $src $dst -Force
Write-Host "已写入 $dst（API Key 仍来自 local.env 或 YAML 中的 llm.api_key）" -ForegroundColor Green
