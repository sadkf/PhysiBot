# PhysiBot 初始配置向导
# 通过 setup.bat 调用，或直接执行：
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$Root      = Split-Path -Parent $PSScriptRoot
$DataDir   = Join-Path $Root "physi-data"
$ConfigFile = Join-Path $DataDir "config.yaml"
$LocalEnv  = Join-Path $DataDir "local.env"

if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║       PhysiBot 初始配置向导              ║" -ForegroundColor Cyan
Write-Host "  ║  只需配置一次，以后直接双击「一键启动」  ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── 检查是否已配置 ────────────────────────────────────────────
if ((Test-Path $LocalEnv) -and (Select-String -Path $LocalEnv -Pattern "PHYSIBOT_LLM_API_KEY" -Quiet)) {
    Write-Host "  [已配置] 检测到 physi-data\local.env 已存在。" -ForegroundColor Yellow
    $reconfig = Read-Host "  是否重新配置? (y/N)"
    if ($reconfig -ne "y" -and $reconfig -ne "Y") {
        Write-Host "  跳过配置，直接启动请双击「一键启动.bat」" -ForegroundColor Green
        exit 0
    }
}

# ── Step 1: LLM 供应商 ────────────────────────────────────────
Write-Host ""
Write-Host "  ══ 第 1 步：LLM API Key ════════════════════════" -ForegroundColor White
Write-Host ""
Write-Host "  推荐供应商（国内可直连）："
Write-Host "    minimax   — minimax.com，有免费额度"
Write-Host "    其他      — anthropic / openai（需要梯子）"
Write-Host ""

$provider = Read-Host "  供应商 (默认 minimax)"
if (-not $provider) { $provider = "minimax" }

$apiKey = Read-Host "  API Key（粘贴后回车）"
if (-not $apiKey) {
    Write-Host "  [错误] API Key 不能为空！" -ForegroundColor Red
    exit 1
}

$defaultModel = switch ($provider.ToLower()) {
    "minimax"   { "MiniMax-M2.5" }
    "anthropic" { "claude-sonnet-4-6" }
    "openai"    { "gpt-4o" }
    default     { "" }
}
$defaultBaseUrl = if ($provider.ToLower() -eq "minimax") { "https://api.minimax.chat/v1" } else { "" }

$model = Read-Host "  模型型号（默认 $defaultModel，回车跳过）"
if (-not $model) { $model = $defaultModel }

# ── Step 2: QQ 配置 ───────────────────────────────────────────
Write-Host ""
Write-Host "  ══ 第 2 步：QQ 配置 ════════════════════════════" -ForegroundColor White
Write-Host ""
$ownerQQ = Read-Host "  你的 QQ 号（机器人主人）"
if (-not $ownerQQ) { $ownerQQ = "10000" }

$talkInput = Read-Host "  允许对话的 QQ 号（多个用逗号分隔，留空则只有主人）"
$talkList = if ($talkInput) {
    ($talkInput -split ",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
} else {
    @($ownerQQ)
}

# ── Step 3: 感知层 ────────────────────────────────────────────
Write-Host ""
Write-Host "  ══ 第 3 步：感知层（可选）══════════════════════" -ForegroundColor White
Write-Host ""
$spInput = Read-Host "  启用 Screenpipe 屏幕感知？(Y/n，首次启动自动下载约 500MB)"
$spEnabled = ($spInput -ne "n" -and $spInput -ne "N")

$awInput = Read-Host "  启用 ActivityWatch 应用追踪？(Y/n)"
$awEnabled = ($awInput -ne "n" -and $awInput -ne "N")

# ── 写入 local.env ───────────────────────────────────────────
"PHYSIBOT_LLM_API_KEY=$apiKey" | Set-Content -Path $LocalEnv -Encoding UTF8
Write-Host ""
Write-Host "  [OK] API Key 已保存到 physi-data\local.env" -ForegroundColor Green

# ── 生成 config.yaml ─────────────────────────────────────────
$talkYaml = ($talkList | ForEach-Object { "    - `"$_`"" }) -join "`n"

$yaml = @"
# PhysiBot 配置（由 setup.ps1 生成）
llm:
  provider: "$provider"
  model: "$model"
  api_key: ""
  base_url: "$defaultBaseUrl"

perception:
  screenpipe:
    enabled: $($spEnabled.ToString().ToLower())
    api_url: "http://localhost:3030"
  activitywatch:
    enabled: $($awEnabled.ToString().ToLower())
    api_url: "http://localhost:5600"
  clipboard:
    enabled: true
    poll_interval: 5

iot:
  enabled: false
  url: "http://homeassistant.local:8123"
  token: ""

qq:
  ws_url: "ws://localhost:3001"
  owner_qq: "$ownerQQ"
  talk_qq:
$talkYaml

agent:
  segment_interval: 1800
  user_trigger_cooldown: 600
  confirm_dangerous: true

privacy:
  redact_sensitive: false
  ignore_apps:
    - KeePass
    - 1Password
  sensitive_keywords: []

monitor:
  enabled: true
  host: "127.0.0.1"
  port: 8765
"@

Set-Content -Path $ConfigFile -Value $yaml -Encoding UTF8
Write-Host "  [OK] config.yaml 已生成" -ForegroundColor Green

# ── 完成 ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ══════════════════════════════════════════════" -ForegroundColor Green
Write-Host "   配置完成！" -ForegroundColor Green
Write-Host ""
Write-Host "   下一步：双击「一键启动.bat」启动 PhysiBot" -ForegroundColor White
Write-Host "   配置文件：physi-data\config.yaml" -ForegroundColor DarkGray
Write-Host "   API Key：physi-data\local.env（不要分享）" -ForegroundColor DarkGray
Write-Host "  ══════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Read-Host "  按 Enter 退出"
