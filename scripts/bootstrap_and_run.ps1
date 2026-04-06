# PhysiBot 一键启动：自动准备 Python / uv / 依赖后调用全流程构建脚本。
# 用法: 在项目根目录双击 PhysiBot.cmd 或 start.bat

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
$cfgWcd  = Join-Path $Root "physi-data\config.wcd.yaml"
if ((-not (Test-Path $cfgYaml)) -and (Test-Path $cfgWcd)) {
    Write-Host "[bootstrap] config.yaml -> config.wcd.yaml" -ForegroundColor Cyan
    Copy-Item $cfgWcd $cfgYaml
}

function Test-Python311Plus {
    try {
        $v = python --version 2>&1
        if ($v -match "Python 3\.(1[1-9]|[2-9][0-9])") { return $true }
    } catch { }
    return $false
}

# 国内网络：pip 与 uv 默认走清华 PyPI 镜像
if (-not $env:PIP_INDEX_URL) {
    $env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
}
if (-not $env:UV_DEFAULT_INDEX) {
    $env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
}

$python312_url = "https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-amd64.exe"
$pythonTmp = Join-Path $env:TEMP "python-3.12.8-amd64.exe"
$localPythonDir = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
$localPythonExe = Join-Path $localPythonDir "python.exe"
$localScriptsDir = Join-Path $localPythonDir "Scripts"

if (-not (Test-Python311Plus)) {
    if (Test-Path $localPythonExe) {
        Write-Host "[bootstrap] 发现已安装的自动 Python: $localPythonExe" -ForegroundColor Cyan
        $env:Path = "$localPythonDir;$localScriptsDir;" + $env:Path
    } else {
        Write-Host "[bootstrap] 未检测到 Python 3.11+，正在从国内高速镜像静默下载并安装 Python 3.12 (首次启动可能需要半分钟)..." -ForegroundColor Yellow
        try {
            Invoke-WebRequest -Uri $python312_url -OutFile $pythonTmp -UseBasicParsing
            Write-Host "[bootstrap] Python 下载完成，正在安装..." -ForegroundColor Yellow
            Start-Process -FilePath $pythonTmp -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1" -Wait -NoNewWindow
            Remove-Item $pythonTmp -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Host "[bootstrap] 自动 Python 下载或安装失败！" -ForegroundColor Red
            Write-Host "请手动下载并安装 Python 3.11+并勾选 Add to PATH:" -ForegroundColor Red
            Write-Host "  国内镜像: https://mirrors.huaweicloud.com/python/" -ForegroundColor Red
            Read-Host "按 Enter 退出"
            exit 1
        }
        
        # Reload Environment PATH context to detect the newly installed Python
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        if ($userPath) { $env:Path = "$userPath;$machinePath" }
        else { $env:Path = $machinePath }
        
        # explicitly prepend standard localappdata location to PATH for this process
        $env:Path = "$localPythonDir;$localScriptsDir;" + $env:Path
    }
}

if (-not (Test-Python311Plus)) {
    Write-Host "[bootstrap] 仍无法找到 python 命令，请重启当前命令提示符后再试。" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "[bootstrap] 载入 Python: $(python --version)" -ForegroundColor Green

$uvOk = $false
try {
    $null = uv --version 2>&1
    $uvOk = $true
} catch { }

if (-not $uvOk) {
    Write-Host "[bootstrap] 使用国内镜像安装 uv..." -ForegroundColor Cyan
    python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -U pip uv
}

Write-Host "[bootstrap] uv sync ..." -ForegroundColor Cyan
uv sync
if ($LASTEXITCODE -ne 0) {
    Write-Host "[bootstrap] uv sync 失败，可尝试手动执行: pip install -U uv 后重试" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "[bootstrap] Python / uv 环境准备就绪。进入感知生态启动引导..." -ForegroundColor Green
powershell -NoProfile -ExecutionPolicy Bypass -File "$Root\run.ps1"
exit $LASTEXITCODE
