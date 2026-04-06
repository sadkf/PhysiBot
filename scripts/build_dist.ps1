# =============================================================================
# PhysiBot 离线发行包构建脚本
# 使用方法（在项目根目录执行）：
#   powershell -ExecutionPolicy Bypass -File scripts\build_dist.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build_dist.ps1 -Version 0.2.0
#   powershell -ExecutionPolicy Bypass -File scripts\build_dist.ps1 -IncludeScreenpipe
# 输出：dist\PhysiBot-<version>.zip
# =============================================================================
param(
    [string]$Version    = "0.1.0",
    [switch]$IncludeScreenpipe   # 加此开关才打入 screenpipe（+3.8 GB，默认不打）
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

$Root     = Split-Path -Parent $PSScriptRoot
$DistName = "PhysiBot-$Version"
$DistDir  = Join-Path $Root "dist\$DistName"
$DistZip  = Join-Path $Root "dist\$DistName.zip"
$Vendor   = Join-Path $Root "vendor"

# --- 下载源 ---
$PYEMBED_URL = "https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-embed-amd64.zip"
$GETPIP_URL  = "https://bootstrap.pypa.io/get-pip.py"
$UV_URL      = "https://ghfast.top/https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"

function Write-Step([string]$msg) { Write-Host "`n[BUILD] $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "  [OK] $msg"   -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)  { Write-Host "  [ERR] $msg"  -ForegroundColor Red; exit 1 }

function Download([string]$Url, [string]$Out) {
    Write-Host "  -> $Url" -ForegroundColor DarkGray
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Out -UseBasicParsing
    } catch {
        # GitHub 代理备用
        $mirrors = @("https://ghfast.top/", "https://ghproxy.net/")
        $ok = $false
        foreach ($m in $mirrors) {
            try {
                Invoke-WebRequest -Uri ($m + $Url) -OutFile $Out -UseBasicParsing
                $ok = $true; break
            } catch { }
        }
        if (-not $ok) { Write-Err "下载失败: $Url" }
    }
}

# ===========================================================================
# 1. 清理旧输出
# ===========================================================================
Write-Step "清理 dist\$DistName"
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Root "dist") -Force | Out-Null

# ===========================================================================
# 2. 复制源码与启动脚本
# ===========================================================================
Write-Step "复制项目源码"
$copyItems = @("src", "pyproject.toml", "uv.lock",
               "run.ps1", "一键启动.bat", "start.bat", "PhysiBot.cmd",
               "START_HERE.txt", "README.md")
foreach ($item in $copyItems) {
    $src = Join-Path $Root $item
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $DistDir -Recurse -Force
        Write-OK $item
    } else {
        Write-Warn "$item 不存在，跳过"
    }
}

# scripts/ 只复制运行时脚本（不复制 build_dist.ps1 自身）
$scriptsOut = Join-Path $DistDir "scripts"
New-Item -ItemType Directory -Path $scriptsOut -Force | Out-Null
foreach ($f in @("bootstrap_and_run.ps1")) {
    $s = Join-Path $Root "scripts\$f"
    if (Test-Path $s) { Copy-Item $s $scriptsOut -Force; Write-OK "scripts\$f" }
}

# setup.bat（首次配置向导）
$setupSrc = Join-Path $Root "setup.bat"
if (Test-Path $setupSrc) {
    Copy-Item $setupSrc $DistDir -Force; Write-OK "setup.bat"
}

# ===========================================================================
# 3. physi-data 模板（不含个人数据）
# ===========================================================================
Write-Step "生成 physi-data 模板"
$pdOut = Join-Path $DistDir "physi-data"
New-Item -ItemType Directory -Path $pdOut -Force | Out-Null

$configExample = Join-Path $Root "physi-data\config.yaml.example"
if (Test-Path $configExample) {
    Copy-Item $configExample (Join-Path $pdOut "config.yaml.example") -Force
    Write-OK "config.yaml.example"
}

$physi_md = Join-Path $Root "physi-data\PHYSI.md"
if (Test-Path $physi_md) {
    Copy-Item $physi_md $pdOut -Force; Write-OK "PHYSI.md"
}

# ===========================================================================
# 4. Python 嵌入包（免安装 Python）
# ===========================================================================
Write-Step "准备嵌入式 Python 3.12"
$pyEmbedDir = Join-Path $DistDir "vendor\python-embed"
$pyEmbedZip = Join-Path $env:TEMP "python-embed.zip"

if (-not (Test-Path (Join-Path $pyEmbedDir "python.exe"))) {
    New-Item -ItemType Directory -Path $pyEmbedDir -Force | Out-Null
    Download -Url $PYEMBED_URL -Out $pyEmbedZip
    Expand-Archive -Path $pyEmbedZip -DestinationPath $pyEmbedDir -Force
    Remove-Item $pyEmbedZip -Force -ErrorAction SilentlyContinue
    Write-OK "Python embed 解压完成"
}

# 启用 site-packages（解注释 import site）
$pthFiles = Get-ChildItem $pyEmbedDir -Filter "python*._pth"
foreach ($pf in $pthFiles) {
    $content = Get-Content $pf.FullName -Raw
    if ($content -match "#import site") {
        $content = $content -replace "#import site", "import site"
        Set-Content -Path $pf.FullName -Value $content -Encoding UTF8
    }
}

# 安装 pip
$getpipPath = Join-Path $env:TEMP "get-pip.py"
$pyExe      = Join-Path $pyEmbedDir "python.exe"
if (-not (Test-Path (Join-Path $pyEmbedDir "Lib\site-packages\pip"))) {
    Download -Url $GETPIP_URL -Out $getpipPath
    & $pyExe $getpipPath --no-warn-script-location -q `
        -i https://pypi.tuna.tsinghua.edu.cn/simple
    Write-OK "pip 安装完成"
}

# 安装项目依赖（到嵌入 Python 的 site-packages）
Write-Step "安装 Python 依赖到嵌入式 Python"
Push-Location $Root
try {
    & $pyExe -m pip install -e . --no-warn-script-location -q `
        -i https://pypi.tuna.tsinghua.edu.cn/simple
    Write-OK "physi-core 及依赖安装完成"
} finally { Pop-Location }

# 复制已安装的 site-packages 到 dist 中的 python-embed
$srcSitePackages = Join-Path $pyEmbedDir "Lib\site-packages"
Write-OK "依赖已安装到嵌入式 Python"

# ===========================================================================
# 5. ActivityWatch（直接从 vendor/ 复制）
# ===========================================================================
Write-Step "打包 ActivityWatch"
$awSrc = Join-Path $Vendor "activitywatch"
$awOut = Join-Path $DistDir "vendor\activitywatch"
if (Test-Path (Join-Path $awSrc "aw-server.exe")) {
    New-Item -ItemType Directory -Path $awOut -Force | Out-Null
    Copy-Item -Path "$awSrc\*" -Destination $awOut -Recurse -Force
    Write-OK "ActivityWatch 复制完成"
} elseif (Test-Path (Join-Path $Vendor "activitywatch.zip")) {
    # 直接复制 zip，运行时解压
    Copy-Item (Join-Path $Vendor "activitywatch.zip") `
              (Join-Path $DistDir "vendor\activitywatch.zip") -Force
    Write-OK "activitywatch.zip 已打包（运行时解压）"
} else {
    Write-Warn "ActivityWatch 未找到，跳过（运行时将自动下载）"
}

# ===========================================================================
# 6. NapCat（从官方 GitHub Release 下载，干净无用户数据）
# ===========================================================================
Write-Step "打包 NapCat（官方最新版）"
$napOut = Join-Path $DistDir "vendor\napcat"
New-Item -ItemType Directory -Path $napOut -Force | Out-Null
$napTmp = Join-Path $env:TEMP "napcat.zip"

try {
    $rel   = Invoke-RestMethod "https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest" -TimeoutSec 10
    $asset = $rel.assets | Where-Object { $_.name -like "NapCat.Shell.Windows.Node*" } | Select-Object -First 1
    if ($asset) {
        Write-Host ("  NapCat {0} — {1}" -f $rel.tag_name, $asset.name) -ForegroundColor DarkGray
        Download -Url $asset.browser_download_url -Out $napTmp
        Expand-Archive -Path $napTmp -DestinationPath $napOut -Force
        Remove-Item $napTmp -Force -ErrorAction SilentlyContinue
        $napSize = [math]::Round((Get-ChildItem $napOut -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 0)
        Write-OK ("NapCat {0} 下载完成 ({1} MB)" -f $rel.tag_name, $napSize)
    } else {
        Write-Warn "未找到 NapCat.Shell.Windows.Node 资产，跳过"
    }
} catch {
    Write-Warn ("NapCat 下载失败: {0}" -f $_.Exception.Message)
    Write-Warn "跳过 NapCat，用户需手动安装"
}

# ===========================================================================
# 7. Screenpipe（可选，默认不打入，太大）
# ===========================================================================
if ($IncludeScreenpipe) {
    Write-Step "打包 Screenpipe（-IncludeScreenpipe 模式）"
    $spSrc = Join-Path $Vendor "screenpipe"
    $spOut = Join-Path $DistDir "vendor\screenpipe"
    if (Test-Path (Join-Path $spSrc "screenpipe.exe")) {
        New-Item -ItemType Directory -Path $spOut -Force | Out-Null
        # 排除用户录制数据
        Get-ChildItem $spSrc -Recurse -File |
            Where-Object { $_.DirectoryName -notlike "*\data\*" } |
            ForEach-Object {
                $rel  = $_.FullName.Substring($spSrc.Length + 1)
                $dest = Join-Path $spOut $rel
                $destDir = Split-Path $dest -Parent
                if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
                Copy-Item $_.FullName $dest -Force
            }
        $spSize = [math]::Round((Get-ChildItem $spOut -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 0)
        Write-OK "Screenpipe 复制完成 (${spSize} MB)"
    } else {
        Write-Warn "screenpipe.exe 未找到，跳过"
    }
} else {
    Write-Warn "Screenpipe 未打包（过大，运行时从镜像下载）。如需离线打包加 -IncludeScreenpipe"
}

# ===========================================================================
# 8. 生成 ZIP
# ===========================================================================
Write-Step "生成 $DistName.zip"
if (Test-Path $DistZip) { Remove-Item $DistZip -Force }
Compress-Archive -Path "$DistDir\*" -DestinationPath $DistZip -CompressionLevel Optimal
$zipMB = [math]::Round((Get-Item $DistZip).Length / 1MB, 0)
Write-OK "输出: $DistZip ($zipMB MB)"

# ===========================================================================
# 9. 完成摘要
# ===========================================================================
Write-Host @"

===========================================================
  PhysiBot $Version 发行包构建完成！

  文件位置：dist\$DistName.zip  ($zipMB MB)
  解压后文件夹：dist\$DistName\

  ---- 用户使用步骤 ----
  1. 解压 ZIP
  2. 双击 setup.bat  ← 填写 API Key 和 QQ 号（仅需一次）
  3. 双击 一键启动.bat  ← 以后每次启动
===========================================================
"@ -ForegroundColor Green
