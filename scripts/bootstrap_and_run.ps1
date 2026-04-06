# PhysiBot 一键启动：尽量自动准备 Python / uv / 依赖后运行主程序。
# 用法: 在项目根目录双击 PhysiBot.cmd，或: powershell -ExecutionPolicy Bypass -File scripts\bootstrap_and_run.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# 开发分支：加载 physi-data/local.env（含 PHYSIBOT_LLM_API_KEY，不提交 git）
$localEnv = Join-Path $Root "physi-data\local.env"
if (Test-Path $localEnv) {
    Write-Host "[bootstrap] 加载 physi-data\local.env" -ForegroundColor DarkGray
    Get-Content $localEnv -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -match '^\s*#' -or $line -eq '') { return }
        $i = $line.IndexOf('=')
        if ($i -gt 0) {
            $k = $line.Substring(0, $i).Trim()
            $v = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($k, $v, 'Process')
        }
    }
}
$cfgYaml = Join-Path $Root "physi-data\config.yaml"
$cfgWcd = Join-Path $Root "physi-data\config.wcd.yaml"
if (-not (Test-Path $cfgYaml) -and (Test-Path $cfgWcd)) {
    Write-Host "[bootstrap] 生成 config.yaml ← config.wcd.yaml" -ForegroundColor Cyan
    Copy-Item $cfgWcd $cfgYaml
}

function Test-Python311Plus {
    try {
        $v = python --version 2>&1
        if ($v -match "Python 3\.(1[1-9]|[2-9][0-9])") { return $true }
    } catch { }
    return $false
}

function Install-PythonViaWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { return $false }
    Write-Host "[bootstrap] 尝试通过 winget 安装 Python 3.12（可能需要确认）..." -ForegroundColor Cyan
    try {
        & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
        return $true
    } catch {
        return $false
    }
}

# 国内网络：pip 与 uv 默认走清华 PyPI 镜像（可用环境变量覆盖；见 README「国内用户与网络」）
if (-not $env:PIP_INDEX_URL) {
    $env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
}
if (-not $env:UV_DEFAULT_INDEX) {
    $env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
}

if (-not (Test-Python311Plus)) {
    Write-Host "[bootstrap] 未检测到 Python 3.11+，尝试 winget 安装..." -ForegroundColor Yellow
    if (-not (Install-PythonViaWinget)) {
        Write-Host @"

[bootstrap] 请手动安装 Python 3.11+ 并勾选 Add to PATH：
  - 官方: https://www.python.org/downloads/windows/
  - 国内镜像目录: https://mirrors.huaweicloud.com/python/
安装完成后重新运行本脚本。
"@ -ForegroundColor Red
        Read-Host "按 Enter 退出"
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Test-Python311Plus)) {
    Write-Host "[bootstrap] 仍无法找到 python，请重启终端后再试。" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "[bootstrap] $(python --version)" -ForegroundColor Green

$uvOk = $false
try {
    $null = uv --version 2>&1
    $uvOk = $true
} catch { }

if (-not $uvOk) {
    Write-Host "[bootstrap] 安装 uv（包管理器）..." -ForegroundColor Cyan
    python -m pip install -U pip uv
}

Write-Host "[bootstrap] 同步依赖 uv sync ..." -ForegroundColor Cyan
uv sync
if ($LASTEXITCODE -ne 0) {
    Write-Host "[bootstrap] uv sync 失败，可尝试: pip install -U uv 后重试" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "[bootstrap] 启动 PhysiBot ..." -ForegroundColor Green
uv run python -m physi_core
exit $LASTEXITCODE
