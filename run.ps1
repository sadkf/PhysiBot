param(
    [switch]$SkipCleanup,
    [switch]$SkipBot,
    [switch]$VerboseDownload,
    [switch]$OfflineBundle
)

# PhysiBot launcher: mirror-first, official fallback.
# Services:
# - ActivityWatch on localhost:5600
# - Screenpipe on localhost:3030

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"
$ProgressPreference = if ($VerboseDownload) { "Continue" } else { "SilentlyContinue" }
$VerbosePreference = "SilentlyContinue"

$ROOT = $PSScriptRoot
$VENDOR = Join-Path $ROOT "vendor"

# Mirrors
$GH_MIRRORS = @(
    "https://ghfast.top/",
    "https://ghproxy.net/"
)
$NPM_MIRROR = "https://registry.npmmirror.com"
$UV_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

function Write-Step([string]$msg) { Write-Host "`n$msg" -ForegroundColor Cyan }
function Write-OK([string]$msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg) { Write-Host "  [ERR] $msg" -ForegroundColor Red }
function Write-DebugLine([string]$msg) {
    if ($VerboseDownload) {
        Write-Host ("  [DBG] " + $msg) -ForegroundColor DarkGray
    }
}

function Find-Exe([string]$Root, [string]$ExeName) {
    if (-not (Test-Path $Root)) { return $null }
    $direct = Join-Path $Root $ExeName
    if (Test-Path $direct) { return $direct }
    $hit = Get-ChildItem -Path $Root -Recurse -File -Filter $ExeName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

function Is-Running([string]$Name) {
    return $null -ne (Get-Process -Name $Name -ErrorAction SilentlyContinue)
}

function Is-PortOpen([int]$Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $Port)
        $c.Close()
        return $true
    } catch {
        return $false
    }
}

function Wait-Port([int]$Port, [int]$TimeoutSec = 25) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Is-PortOpen $Port) { return $true }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Download-File([string]$Url, [string]$OutFile) {
    $candidates = @()
    if ($Url -match "^https://github\.com/") {
        foreach ($m in $GH_MIRRORS) {
            $candidates += ($m + $Url)
        }
    }
    $candidates += $Url

    Write-DebugLine ("download target: " + $Url)
    Write-DebugLine ("candidate count: " + $candidates.Count)

    $candidateIndex = 0
    foreach ($candidate in $candidates) {
        $candidateIndex += 1
        Write-DebugLine ("candidate " + $candidateIndex + "/" + $candidates.Count + ": " + $candidate)
        for ($i = 1; $i -le 2; $i++) {
            Write-DebugLine ("attempt " + $i + "/2 on candidate " + $candidateIndex)
            $sw = [Diagnostics.Stopwatch]::StartNew()
            try {
                if (Test-Path $OutFile) {
                    Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
                }
                Invoke-WebRequest -Uri $candidate -OutFile $OutFile -UseBasicParsing -Verbose:$VerboseDownload
                if (Test-Path $OutFile) { return $true }
            } catch {
                $sw.Stop()
                Write-DebugLine ("failed after " + [int]$sw.Elapsed.TotalSeconds + "s: " + $_.Exception.Message)
                if ($i -lt 2) { Start-Sleep -Seconds $i }
                continue
            }
            $sw.Stop()
            $size = 0
            try { $size = (Get-Item $OutFile).Length } catch {}
            Write-DebugLine ("success in " + [int]$sw.Elapsed.TotalSeconds + "s, bytes=" + $size)
            return $true
        }
    }
    Write-Err "download failed for all mirrors: $Url"
    return $false
}

function Download-AndUnzip([string]$Url, [string]$DestDir, [string]$Label) {
    $tmp = Join-Path $env:TEMP ("physi_" + $Label + ".zip")
    Write-Host "  Downloading $Label" -ForegroundColor Yellow
    Write-Host "  URL: $Url" -ForegroundColor DarkGray

    if (-not (Download-File -Url $Url -OutFile $tmp)) {
        return $false
    }

    try {
        New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
        Write-DebugLine ("extracting zip: " + $tmp)
        Expand-Archive -Path $tmp -DestinationPath $DestDir -Force

        # Flatten one wrapper folder.
        $subs = Get-ChildItem $DestDir -Directory
        if ($subs.Count -eq 1) {
            $sub = $subs[0].FullName
            Get-ChildItem $sub -Force | Move-Item -Destination $DestDir -Force
            Remove-Item $sub -Recurse -Force -ErrorAction SilentlyContinue
        }

        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        return $true
    } catch {
        Write-Err ("extract failed: {0}" -f $_.Exception.Message)
        return $false
    }
}

function Get-GithubAssetUrl([string]$Repo, [string[]]$Patterns) {
    # 彻底弃用 github api，直接硬编码中国区测试最优稳定版本，由上层 ghfast.top 代理加速
    if ($Repo -eq "BtbN/FFmpeg-Builds") {
        return "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    } elseif ($Repo -eq "ActivityWatch/activitywatch") {
        return "https://github.com/ActivityWatch/activitywatch/releases/download/v0.12.2/activitywatch-v0.12.2-windows-x86_64.zip"
    }
    return $null
}

function Ensure-FFmpeg([string]$TargetDir) {
    $ffmpegExe = Find-Exe -Root $TargetDir -ExeName "ffmpeg.exe"
    if ($ffmpegExe) { return (Split-Path $ffmpegExe -Parent) }

    if ($OfflineBundle) {
        Write-Warn "offline mode: ffmpeg.exe not found in vendor, skipping network download"
        return $null
    }

    Write-Host "  ffmpeg not found, downloading mirror-first build" -ForegroundColor Yellow
    $ffDir = Join-Path $TargetDir "ffmpeg"
    $url = Get-GithubAssetUrl -Repo "BtbN/FFmpeg-Builds" -Patterns @(
        "ffmpeg-master-latest-win64-gpl\.zip$",
        "ffmpeg-.*-win64-gpl\.zip$"
    )
    if ($url -and (Download-AndUnzip -Url $url -DestDir $ffDir -Label "ffmpeg")) {
        $ffmpegExe = Find-Exe -Root $ffDir -ExeName "ffmpeg.exe"
        if ($ffmpegExe) {
            Write-OK "ffmpeg prepared"
            return (Split-Path $ffmpegExe -Parent)
        }
    }
    Write-Warn "ffmpeg bundle failed, screenpipe may self-download ffmpeg"
    return $null
}

function Get-ScreenpipeAssetUrl() {
    return "https://github.com/mediar-ai/screenpipe/releases/download/v0.3.62/screenpipe-0.3.62-x86_64-pc-windows-msvc.zip"
}

function Start-ScreenpipeNpmFallback([string]$RootDir, [string]$DataDir, [bool]$OfflineMode) {
    $npmArgs = if ($OfflineMode) {
        "--offline @screenpipe/cli-win32-x64 record --disable-audio --disable-telemetry --port 3030 -l chinese --data-dir `"$DataDir`""
    } else {
        "@screenpipe/cli-win32-x64 record --disable-audio --disable-telemetry --port 3030 -l chinese --data-dir `"$DataDir`""
    }

    $fallbackCmd = "set NPM_CONFIG_LOGLEVEL=error&& set npm_config_registry=$NPM_MIRROR&& npx --yes $npmArgs"
    if ($OfflineMode) {
        Write-Warn "screenpipe.exe not found, trying npm offline fallback"
    } else {
        Write-Warn "screenpipe.exe not found, trying npm fallback"
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c $fallbackCmd" -WorkingDirectory $RootDir -WindowStyle Hidden
}

# ===========================================================================
# 嵌入式 Python 检测（离线包模式）
# 若 vendor/python-embed/python.exe 存在，则完全使用它，不依赖系统 Python/uv
# ===========================================================================
$EMBED_PYTHON = Join-Path $VENDOR "python-embed\python.exe"
$USE_EMBED    = Test-Path $EMBED_PYTHON

if ($USE_EMBED) {
    Write-Host "`n[离线包模式] 使用嵌入式 Python: $EMBED_PYTHON" -ForegroundColor Cyan
    # 确保嵌入式 Python 的 Scripts 目录在 PATH 中
    $embedScripts = Join-Path $VENDOR "python-embed\Scripts"
    $env:PATH = "$VENDOR\python-embed;$embedScripts;" + $env:PATH
    # 不需要 uv sync，包已预装
    $OfflineBundle = $true
} else {
    Write-Host "`n[标准模式] 使用系统 Python / uv" -ForegroundColor DarkGray
}

# 检查 ActivityWatch zip（离线包内可能携带 zip 而非已解压目录）
$AW_ZIP_BUNDLED = Join-Path $VENDOR "activitywatch.zip"
if ((Test-Path $AW_ZIP_BUNDLED) -and (-not (Test-Path (Join-Path $VENDOR "activitywatch\aw-server.exe")))) {
    Write-Host "  解压捆绑的 activitywatch.zip ..." -ForegroundColor Yellow
    Expand-Archive -Path $AW_ZIP_BUNDLED -DestinationPath (Join-Path $VENDOR "activitywatch") -Force
    Write-OK "ActivityWatch 解压完成"
}

Write-Step "[1/5] Pre-flight cleanup"
if ($SkipCleanup) {
    Write-Warn "cleanup disabled by -SkipCleanup"
} else {
    $p3001 = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue
    if ($p3001) {
        Write-Host "  stopping process on port 3001" -ForegroundColor Yellow
        $p3001 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }

    # Kill only physi bot python workers.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*physi_core*" -or $_.CommandLine -like "*physi-core*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    # Kill only napcat node workers.
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
        Where-Object { $_.CommandLine -like "*napcat*" -or $_.CommandLine -like "*NapCatQQ*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    # Kill screenpipe workers started by previous runs.
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -like "screenpipe*" -or
            $_.CommandLine -like "*@screenpipe/cli-win32-x64*" -or
            $_.CommandLine -like "*screenpipe record*"
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    Write-OK "cleanup done"
}

# ===========================================================================
# NapCat（QQ 消息中间件）
# 查找顺序: vendor/napcat → physi-data/napcat
# ===========================================================================
Write-Step "[2/5] NapCat"
$NAP_DIRS = @(
    (Join-Path $VENDOR "napcat"),
    (Join-Path $ROOT "physi-data\napcat")
)
$NAP_BAT = $null
foreach ($d in $NAP_DIRS) {
    $candidate = Join-Path $d "napcat.bat"
    if (Test-Path $candidate) { $NAP_BAT = $candidate; break }
}

if (Is-PortOpen 3001) {
    Write-OK "NapCat WebSocket already on :3001"
} elseif ($NAP_BAT) {
    Write-Host "  启动 NapCat: $NAP_BAT" -ForegroundColor Yellow
    $napDir = Split-Path $NAP_BAT -Parent
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$NAP_BAT`"" `
        -WorkingDirectory $napDir -WindowStyle Hidden
    if (Wait-Port -Port 3001 -TimeoutSec 30) {
        Write-OK "NapCat started on :3001"
    } else {
        Write-Warn "NapCat 已启动，但 :3001 尚未就绪（可能需要扫码登录 QQ）"
        Write-Host "  请在弹出的 QQ 窗口完成登录后，PhysiBot 将自动连接。" -ForegroundColor Yellow
    }
} else {
    Write-Warn "NapCat 未找到（vendor\napcat\napcat.bat 不存在）"
    Write-Host "  若要启用 QQ 消息功能，请将 NapCat 放到 vendor\napcat\ 目录。" -ForegroundColor DarkGray
}

Write-Step "[3/5] ActivityWatch"
$AW_DIR = Join-Path $VENDOR "activitywatch"
$AW_SERVER = Find-Exe -Root $AW_DIR -ExeName "aw-server.exe"
$AW_WATCHER = Find-Exe -Root $AW_DIR -ExeName "aw-watcher-window.exe"
$AW_AFK = Find-Exe -Root $AW_DIR -ExeName "aw-watcher-afk.exe"

if (-not $AW_SERVER) {
    Write-Host "  ActivityWatch not installed, downloading" -ForegroundColor Yellow
    $url = Get-GithubAssetUrl -Repo "ActivityWatch/activitywatch" -Patterns @("windows-x86_64\.zip$")
    if ($url -and (Download-AndUnzip -Url $url -DestDir $AW_DIR -Label "activitywatch")) {
        $AW_SERVER = Find-Exe -Root $AW_DIR -ExeName "aw-server.exe"
        $AW_WATCHER = Find-Exe -Root $AW_DIR -ExeName "aw-watcher-window.exe"
        $AW_AFK = Find-Exe -Root $AW_DIR -ExeName "aw-watcher-afk.exe"
    }
}

if (Is-Running "aw-server") {
    Write-OK "aw-server already running"
} elseif ($AW_SERVER) {
    Start-Process -FilePath $AW_SERVER -WorkingDirectory (Split-Path $AW_SERVER -Parent) -WindowStyle Hidden
    if ($AW_WATCHER) { Start-Process -FilePath $AW_WATCHER -WorkingDirectory (Split-Path $AW_WATCHER -Parent) -WindowStyle Hidden }
    if ($AW_AFK) { Start-Process -FilePath $AW_AFK -WorkingDirectory (Split-Path $AW_AFK -Parent) -WindowStyle Hidden }
    if (Wait-Port -Port 5600 -TimeoutSec 20) { Write-OK "ActivityWatch started on :5600" }
    else { Write-Warn "ActivityWatch started but :5600 not ready" }
} else {
    Write-Warn "aw-server.exe not found, ActivityWatch disabled"
}

Write-Step "[4/5] Screenpipe"
$SP_DIR = Join-Path $VENDOR "screenpipe"
$SP_EXE = Find-Exe -Root $SP_DIR -ExeName "screenpipe.exe"
$FFMPEG_BIN = Ensure-FFmpeg -TargetDir $SP_DIR
if ($FFMPEG_BIN) {
    $env:PATH = ($FFMPEG_BIN + ";" + $env:PATH)
}

if (-not $SP_EXE) {
    if ($OfflineBundle) {
        Write-Warn "offline mode: screenpipe.exe not found in vendor, skipping network download"
    } else {
        Write-Host "  Screenpipe not installed, downloading" -ForegroundColor Yellow
        $url = Get-ScreenpipeAssetUrl
        if ($url -and (Download-AndUnzip -Url $url -DestDir $SP_DIR -Label "screenpipe")) {
            $SP_EXE = Find-Exe -Root $SP_DIR -ExeName "screenpipe.exe"
            if (-not $SP_EXE) {
                Write-Warn "screenpipe.exe not found after extraction, checking subdirectories..."
                $SP_EXE = Find-Exe -Root $SP_DIR -ExeName "screenpipe.exe"
            }
        } else {
            Write-Warn "screenpipe download failed or zip not found"
        }
    }
}

if (Is-Running "screenpipe") {
    Write-OK "screenpipe already running"
    if (Wait-Port -Port 3030 -TimeoutSec 300) { Write-OK "screenpipe api ready on :3030" }
    else { Write-Warn "screenpipe process exists but :3030 still not ready" }
} elseif (Is-PortOpen 3030) {
    Write-OK "screenpipe api already reachable on :3030"
} elseif ($SP_EXE) {
    # Screenpipe may need 'record' explicitly in some versions.
    Start-Process -FilePath $SP_EXE -ArgumentList "record", "--no-audio", "--port", "3030", "-l", "chinese", "--data-dir", "`"$SP_DIR\data`"" -WorkingDirectory (Split-Path $SP_EXE -Parent) -WindowStyle Hidden
    if (Wait-Port -Port 3030 -TimeoutSec 300) { Write-OK "Screenpipe started on :3030" }
    else { Write-Warn "screenpipe started but :3030 not ready" }
} else {
    # Fallback: npm binary package for Windows (mirror registry).
    $spData = Join-Path $SP_DIR "data"
    New-Item -ItemType Directory -Path $spData -Force | Out-Null
    Start-ScreenpipeNpmFallback -RootDir $ROOT -DataDir $spData -OfflineMode:$OfflineBundle
    if (Wait-Port -Port 3030 -TimeoutSec 300) {
        if ($OfflineBundle) { Write-OK "Screenpipe (npm offline fallback) started on :3030" }
        else { Write-OK "Screenpipe (npm fallback) started on :3030" }
    } else { Write-Warn "screenpipe fallback failed, OCR disabled" }
}

Write-Step "[5/5] PhysiBot"
if ($SkipBot) {
    Write-Warn "bot launch disabled by -SkipBot"
    exit 0
}

Set-Location $ROOT
$env:PYTHONPATH = "src"
$env:npm_config_registry = $NPM_MIRROR

if ($USE_EMBED) {
    # 离线包模式：直接用嵌入式 Python 运行
    Write-Host "  使用嵌入式 Python 启动 PhysiBot..." -ForegroundColor Cyan
    & $EMBED_PYTHON -m physi_core
} else {
    # 标准模式：通过 uv 管理环境
    $env:UV_INDEX_URL = $UV_MIRROR
    $env:PIP_INDEX_URL = $UV_MIRROR
    uv run python -m physi_core
}
