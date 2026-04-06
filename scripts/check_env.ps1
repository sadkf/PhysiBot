# 检查 PhysiBot 运行所需的基础环境（Windows PowerShell）
# 用法: powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1

$ErrorActionPreference = "Continue"
Write-Host "=== PhysiBot 环境检查 ===" -ForegroundColor Cyan

$ok = $true

try {
    $py = python --version 2>&1
    if ($py -match "Python 3\.(1[1-9]|[2-9][0-9])") {
        Write-Host "[OK] $py" -ForegroundColor Green
    } else {
        Write-Host "[--] Python 版本需 3.11+，当前: $py" -ForegroundColor Yellow
        $ok = $false
    }
} catch {
    Write-Host "[--] 未检测到 python 命令" -ForegroundColor Yellow
    Write-Host "    请安装 Python 3.11+： https://www.python.org/downloads/ （安装时勾选 Add to PATH）" -ForegroundColor Gray
    $ok = $false
}

try {
    $uvv = uv --version 2>&1
    Write-Host "[OK] uv $uvv" -ForegroundColor Green
} catch {
    Write-Host "[--] 未检测到 uv" -ForegroundColor Yellow
    Write-Host "    推荐: python -m pip install -U uv" -ForegroundColor Gray
}

if (-not (Test-Path "physi-data\config.yaml")) {
    Write-Host "[!!] 未找到 physi-data\config.yaml" -ForegroundColor Red
    Write-Host "    请执行: Copy-Item physi-data\config.yaml.example physi-data\config.yaml 并填写 API Key" -ForegroundColor Gray
    $ok = $false
} else {
    Write-Host "[OK] physi-data\config.yaml 已存在" -ForegroundColor Green
}

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    Write-Host "[..] 已安装 Node（仅 NapCat 等需要）: $(node --version)" -ForegroundColor DarkGray
} else {
    Write-Host "[..] 未安装 Node.js — 主程序为 Python，不接入 NapCat 时可忽略" -ForegroundColor DarkGray
}

Write-Host ""
if ($ok) {
    Write-Host "基础检查通过。运行: uv run python -m physi_core" -ForegroundColor Cyan
} else {
    Write-Host "请先解决上述标红项，再运行主程序。" -ForegroundColor Yellow
    exit 1
}
