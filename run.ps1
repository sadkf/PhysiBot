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
    try {
        $headers = @{ "User-Agent" = "PhysiBot-Launcher"; "Accept" = "application/vnd.github+json" }
        $rels = Invoke-RestMethod -Uri ("https://api.github.com/repos/" + $Repo + "/releases?per_page=30") -Headers $headers
        foreach ($rel in $rels) {
            foreach ($asset in ($rel.assets | ForEach-Object { $_ })) {
                foreach ($pattern in $Patterns) {
                    if ($asset.name -match $pattern) {
                        Write-Host ("  Found: {0} ({1} @ {2})" -f $asset.name, $rel.tag_name, $Repo) -ForegroundColor DarkGray
                        return $asset.browser_download_url
                    }
                }
            }
        }
        Write-Warn ("no matching asset in " + $Repo)
    } catch {
        Write-Warn ("github api failed for {0}: {1}" -f $Repo, $_.Exception.Message)
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
    $patterns = @(
        "x86_64.*windows.*\.zip$",
        "screenpipe.*windows.*\.zip$",
        "windows.*\.zip$"
    )
    $url = Get-GithubAssetUrl -Repo "screenpipe/screenpipe" -Patterns $patterns
    if ($url) { return $url }
    $url = Get-GithubAssetUrl -Repo "mediar-ai/screenpipe" -Patterns $patterns
    if ($url) { return $url }
    return $null
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

Write-Step "[1/4] Pre-flight cleanup"
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

Write-Step "[2/4] ActivityWatch"
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

Write-Step "[3/4] Screenpipe"
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

Write-Step "[4/4] PhysiBot"
if ($SkipBot) {
    Write-Warn "bot launch disabled by -SkipBot"
    exit 0
}

Set-Location $ROOT
$env:PYTHONPATH = "src"
$env:UV_INDEX_URL = $UV_MIRROR
$env:PIP_INDEX_URL = $UV_MIRROR
$env:npm_config_registry = $NPM_MIRROR
uv run python -m physi_core
