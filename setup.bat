@echo off
chcp 65001 >nul
title PhysiBot 初始配置向导

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║       PhysiBot 初始配置向导              ║
echo  ║  只需配置一次，以后直接双击「一键启动」  ║
echo  ╚══════════════════════════════════════════╝
echo.

set CONFIG_DIR=%~dp0physi-data
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

set CONFIG_FILE=%CONFIG_DIR%\config.yaml
set LOCAL_ENV=%CONFIG_DIR%\local.env

rem ─── 检查是否已配置 ──────────────────────────────────
if exist "%LOCAL_ENV%" (
    findstr /C:"PHYSIBOT_LLM_API_KEY" "%LOCAL_ENV%" >nul 2>&1
    if not errorlevel 1 (
        echo  [已配置] 检测到 physi-data\local.env 已存在。
        echo.
        set /p RECONFIG=是否重新配置？(y/N)
        if /i not "%RECONFIG%"=="y" goto :check_config_yaml
    )
)

rem ─── Step 1: API Key ─────────────────────────────────
echo.
echo  ══ 第 1 步：LLM API Key ═══════════════════════════
echo.
echo  支持的 LLM 供应商（推荐用国内可直连的）：
echo    1. MiniMax  (minimax.com，国内直连，免费额度)
echo    2. Anthropic Claude (需要梯子)
echo    3. OpenAI GPT (需要梯子)
echo    4. 其他 OpenAI 兼容 API
echo.
set /p PROVIDER=  请输入供应商 (minimax/anthropic/openai，默认 minimax):
if "%PROVIDER%"=="" set PROVIDER=minimax

set /p API_KEY=  请粘贴 API Key:
if "%API_KEY%"=="" (
    echo  [错误] API Key 不能为空！
    pause
    exit /b 1
)

set MODEL=
if /i "%PROVIDER%"=="minimax" set MODEL=MiniMax-M2.5
if /i "%PROVIDER%"=="anthropic" set MODEL=claude-sonnet-4-6
if /i "%PROVIDER%"=="openai" set MODEL=gpt-4o

set BASE_URL=
if /i "%PROVIDER%"=="minimax" set BASE_URL=https://api.minimax.chat/v1

set /p MODEL_INPUT=  模型型号（默认 %MODEL%，直接回车跳过）:
if not "%MODEL_INPUT%"=="" set MODEL=%MODEL_INPUT%

rem ─── Step 2: QQ 配置 ─────────────────────────────────
echo.
echo  ══ 第 2 步：QQ 配置 ════════════════════════════════
echo.
echo  PhysiBot 通过 NapCat 连接 QQ，需要知道你的 QQ 号。
echo.
set /p OWNER_QQ=  你的 QQ 号（机器人主人）:
if "%OWNER_QQ%"=="" (
    echo  [警告] 未填写 QQ 号，使用占位符 10000，后续可手动改 config.yaml
    set OWNER_QQ=10000
)

set /p TALK_QQ=  允许与机器人对话的 QQ 号（逗号分隔，留空则只有主人）:
if "%TALK_QQ%"=="" set TALK_QQ=%OWNER_QQ%

rem ─── Step 3: 感知层 ───────────────────────────────────
echo.
echo  ══ 第 3 步：感知层（可选功能）══════════════════════
echo.
echo  Screenpipe: 截屏 OCR，让 AI 知道你在看什么（首次启动自动下载约 500MB）
set /p ENABLE_SP=  启用 Screenpipe 截屏感知？(Y/n，默认 Y):
if /i "%ENABLE_SP%"=="n" (set SP_ENABLED=false) else (set SP_ENABLED=true)

echo  ActivityWatch: 追踪活跃应用，让 AI 知道你在用什么程序
set /p ENABLE_AW=  启用 ActivityWatch 应用追踪？(Y/n，默认 Y):
if /i "%ENABLE_AW%"=="n" (set AW_ENABLED=false) else (set AW_ENABLED=true)

rem ─── 写入 local.env（存 API Key，不写入 git）────────────
echo PHYSIBOT_LLM_API_KEY=%API_KEY%> "%LOCAL_ENV%"
echo  [OK] API Key 已保存到 physi-data\local.env

rem ─── 写入 config.yaml ────────────────────────────────
:check_config_yaml
if not exist "%CONFIG_FILE%" (
    if exist "%CONFIG_DIR%\config.yaml.example" (
        copy "%CONFIG_DIR%\config.yaml.example" "%CONFIG_FILE%" >nul
    )
)

rem 用 PowerShell 写 YAML（避免 bat 转义地狱）
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$cfg = '%CONFIG_FILE%'.Replace('\','\\');" ^
    "$env_file = '%LOCAL_ENV%'.Replace('\','\\');" ^
    "$provider = '%PROVIDER%';" ^
    "$model = '%MODEL%';" ^
    "$base_url = '%BASE_URL%';" ^
    "$owner_qq = '%OWNER_QQ%';" ^
    "$talk_qq_raw = '%TALK_QQ%';" ^
    "$sp_enabled = '%SP_ENABLED%';" ^
    "$aw_enabled = '%AW_ENABLED%';" ^
    "$talk_list = ($talk_qq_raw -split ',') | ForEach-Object { '    - \"' + $_.Trim() + '\"' };" ^
    "$talk_yaml = $talk_list -join \"`n\";" ^
    "$yaml = @\"`n# PhysiBot 配置（由 setup.bat 生成）`nllm:`n  provider: \`\"$provider\`\"`n  model: \`\"$model\`\"`n  api_key: \`\"\`\"`n  base_url: \`\"$base_url\`\"`n`nperception:`n  screenpipe:`n    enabled: $sp_enabled`n    api_url: \`\"http://localhost:3030\`\"`n  activitywatch:`n    enabled: $aw_enabled`n    api_url: \`\"http://localhost:5600\`\"`n  clipboard:`n    enabled: true`n    poll_interval: 5`n`niot:`n  enabled: false`n  url: \`\"http://homeassistant.local:8123\`\"`n  token: \`\"\`\"`n`nqq:`n  ws_url: \`\"ws://localhost:3001\`\"`n  owner_qq: \`\"$owner_qq\`\"`n  talk_qq:`n$talk_yaml`n`nagent:`n  segment_interval: 1800`n  user_trigger_cooldown: 600`n  confirm_dangerous: true`n`nprivacy:`n  redact_sensitive: false`n  ignore_apps:`n    - KeePass`n    - 1Password`n  sensitive_keywords: []`n`nmonitor:`n  enabled: true`n  host: \`\"127.0.0.1\`\"`n  port: 8765`n\"@;" ^
    "Set-Content -Path $cfg -Value $yaml -Encoding UTF8"

echo  [OK] config.yaml 已生成

rem ─── 完成 ─────────────────────────────────────────────
echo.
echo  ══════════════════════════════════════════════════
echo   配置完成！
echo.
echo   下一步：双击「一键启动.bat」即可启动 PhysiBot
echo   配置文件位置：physi-data\config.yaml
echo   API Key 位置：physi-data\local.env（请勿分享此文件）
echo  ══════════════════════════════════════════════════
echo.
pause
