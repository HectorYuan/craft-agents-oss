# Stage native binaries (uv / bun / ripgrep) into their electron-builder
# extraResources sources. Single source of truth shared by:
#   - .github/workflows/release.yml (windows-local / windows-hosted jobs)
#   - build-win.ps1 (local installer path)
# 2026-10-07: the workflow path never staged these three (gitignored /
# postinstall-gated files), so windows.3+ / v0.9.14/15 installers shipped
# without uv.exe (desktop chat spawn ENOENT), bun.exe (script runtime) and
# rg.exe (search); extraResources silently skips missing sources.
#
# ASCII-only on purpose: PowerShell 5.1 reads .ps1 without BOM as ANSI;
# CJK comments would mojibake on GBK (same rule as workflow run blocks).
#
# Usage: powershell -ExecutionPolicy Bypass -File stage-win-binaries.ps1
# cwd-independent (uses $PSScriptRoot). Non-zero exit on any failure.

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$ElectronDir = Join-Path $RepoRoot 'apps\electron'

# --- 1. uv: engine runtime (agent-engine spawn) -----------------------------
# Acquisition chain (Release 37738210452 proof 2026-10-08: NETWORK SERVICE
# has no PATH uv, cannot READ the interactive user's profile copy (ACL), and
# cannot pip-install into the machine python (no write to C:\Python314);
# release-assets.githubusercontent.com is unreachable from this host):
#   PATH uv -> $USERPROFILE/.local/bin -> pip --user (pypi)
#   -> pip --user (aliyun mirror) -> github zip download (last resort)
function Find-Uv {
    $c = Get-Command uv -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path $p) { return $p }
    return $null
}
function Install-UvViaPip {
    param([string]$Index)
    $pipArgs = @('-m', 'pip', 'install', '--user', '--quiet', 'uv')
    if ($Index) { $pipArgs += @('--index-url', $Index) }
    foreach ($a in 1..2) {
        try {
            & python @pipArgs
            if ($LASTEXITCODE -eq 0) {
                # locate via site.USER_BASE (user Scripts is NOT on PATH snapshot)
                $base = (& python -c "import site; print(site.USER_BASE)") 2>$null
                if ($base) {
                    $p = Join-Path $base.ToString().Trim() 'Scripts\uv.exe'
                    if (Test-Path $p) { return $p }
                }
            }
        } catch { }
        Write-Host "pip attempt $a failed (index=$Index)"
        Start-Sleep -Seconds 3
    }
    return $null
}
$uvBin = Find-Uv
if (-not $uvBin) { $uvBin = Install-UvViaPip -Index 'https://pypi.org/simple' }
if (-not $uvBin) { $uvBin = Install-UvViaPip -Index 'https://mirrors.aliyun.com/pypi/simple' }
if (-not $uvBin) { $uvBin = Install-UvViaPip -Index 'https://pypi.tuna.tsinghua.edu.cn/simple' }
if (-not $uvBin) {
    # github direct zip (works only if release assets are reachable)
    $UvVer = '0.12.5'
    $TmpUv = Join-Path $env:TEMP "uv-stage-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path $TmpUv | Out-Null
    try {
        foreach ($a in 1..3) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$UvVer/uv-x86_64-pc-windows-msvc.zip" -OutFile "$TmpUv\uv.zip"
                break
            } catch {
                if ($a -eq 3) { Write-Host "uv zip download failed: $($_.Exception.Message)" }
                Start-Sleep -Seconds 5
            }
        }
        if (Test-Path "$TmpUv\uv.zip") {
            Expand-Archive -Path "$TmpUv\uv.zip" -DestinationPath $TmpUv -Force
            $cand = Get-ChildItem -Path $TmpUv -Filter uv.exe -Recurse | Select-Object -First 1
            if ($cand) { $uvBin = $cand.FullName }
        }
    } finally {
        Remove-Item -Recurse -Force $TmpUv -ErrorAction SilentlyContinue
    }
}
if (-not ($uvBin -and (Test-Path $uvBin))) {
    Write-Host '::error::uv.exe not found (PATH / user .local / pip --user pypi+mirror / github zip all failed)'
    exit 1
}
$uvDest = Join-Path $ElectronDir 'resources\bin\win32-x64\uv.exe'
New-Item -ItemType Directory -Force -Path (Split-Path $uvDest) | Out-Null
Copy-Item $uvBin $uvDest -Force
Unblock-File $uvDest -ErrorAction SilentlyContinue
Write-Host "staged uv.exe from $uvBin"

# --- 2. ripgrep: bun blocks postinstall by default -> trust, then hoist ----
# Root node_modules must exist (bun install ran before this script in both
# build-win.ps1 section 2 and the workflow 'bun install' step).
Push-Location $RepoRoot
try {
    bun pm trust @vscode/ripgrep
} finally {
    Pop-Location
}
$rgSrc = Join-Path $RepoRoot 'node_modules\@vscode\ripgrep\bin\rg.exe'
if (-not (Test-Path $rgSrc)) {
    Write-Host "::error::rg.exe missing after bun pm trust ($rgSrc)"
    exit 1
}
$rgDestDir = Join-Path $ElectronDir 'node_modules\@vscode'
New-Item -ItemType Directory -Force -Path $rgDestDir | Out-Null
$rgDest = Join-Path $rgDestDir 'ripgrep'
if (Test-Path $rgDest) { Remove-Item -Recurse -Force $rgDest }
Copy-Item -Recurse -Force (Join-Path $RepoRoot 'node_modules\@vscode\ripgrep') $rgDest
Get-ChildItem -Recurse -File $rgDest -ErrorAction SilentlyContinue | ForEach-Object {
    Unblock-File $_.FullName -ErrorAction SilentlyContinue
}
Write-Host 'staged rg.exe'

# --- 3. bun: pinned baseline build (no AVX2 requirement), checksum verified -
# SHASUMS256 has BOTH bun-windows-x64-baseline.zip and
# bun-windows-x64-baseline-profile.zip rows; a plain Select-String $pkg
# double-matches and PS 5.1 member enumeration makes .ToString() implode
# (always mismatch) -- exact line match with -SimpleMatch + First 1.
$BunVersion = 'bun-v1.3.9'
$Pkg = 'bun-windows-x64-baseline'
$Tmp = Join-Path $env:TEMP "bun-stage-$(Get-Random)"
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
    # Mirror chain: github.com (canonical) -> npmmirror (CN reliability).
    # Zip + SHASUMS always fetched from the SAME mirror so the checksum
    # still proves the bytes. Real failures seen 2026-10-07:
    #   - workflow inline used Select-String $Pkg (no .zip) which matched
    #     baseline.zip AND baseline-profile.zip rows -> .ToString() on an
    #     array -> always mismatch (exact-line parse fixes);
    #   - flaky github connection returned a corrupted/short zip with no
    #     HTTP error -> hash mismatch (retry + mirror fallback fix).
    $mirrors = @(
        @{ Name = 'github'; Base = "https://github.com/oven-sh/bun/releases/download/$BunVersion" },
        @{ Name = 'npmmirror'; Base = "https://registry.npmmirror.com/-/binary/bun/$BunVersion" }
    )
    # PS 5.1: -UseBasicParsing skips the IE engine (hangs on fresh hosts).
    function Get-WithRetry($Url, $OutFile) {
        for ($a = 1; $a -le 3; $a++) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile
                return
            } catch {
                if ($a -eq 3) { throw }
                Write-Host "download retry $a/3 failed for $Url : $($_.Exception.Message)"
                Start-Sleep -Seconds 5
            }
        }
    }
    $downloaded = $false
    foreach ($m in $mirrors) {
        try {
            Write-Host "fetching bun via $($m.Name)..."
            Get-WithRetry "$($m.Base)/$Pkg.zip" "$Tmp\$Pkg.zip"
            Get-WithRetry "$($m.Base)/SHASUMS256.txt" "$Tmp\SHASUMS256.txt"
            $downloaded = $true
            break
        } catch {
            Write-Host "mirror $($m.Name) failed: $($_.Exception.Message)"
        }
    }
    if (-not $downloaded) {
        Write-Host "::error::bun download failed on all mirrors"
        exit 1
    }
    $line = Get-Content "$Tmp\SHASUMS256.txt" |
        Select-String -SimpleMatch "$Pkg.zip" | Select-Object -First 1
    if (-not $line) {
        Write-Host "::error::SHASUMS256.txt has no row for $Pkg.zip"
        exit 1
    }
    $Want = $line.Line.Split(' ')[0]
    $Got = (Get-FileHash "$Tmp\$Pkg.zip" -Algorithm SHA256).Hash.ToLower()
    if ($Got -ne $Want) {
        Write-Host "::error::bun checksum mismatch want=$Want got=$Got"
        exit 1
    }
    Expand-Archive -Path "$Tmp\$Pkg.zip" -DestinationPath $Tmp -Force
    $bunDest = Join-Path $ElectronDir 'vendor\bun\bun.exe'
    New-Item -ItemType Directory -Force -Path (Split-Path $bunDest) | Out-Null
    Copy-Item "$Tmp\$Pkg\bun.exe" $bunDest -Force
    # Expand-Archive propagates MOTW from the downloaded zip; SmartScreen risk
    Unblock-File "$Tmp\$Pkg\bun.exe" -ErrorAction SilentlyContinue
    Unblock-File $bunDest -ErrorAction SilentlyContinue
    Write-Host "staged bun.exe ($BunVersion baseline, checksum ok)"
} finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}

Write-Host 'staged: uv.exe + rg.exe + bun.exe'
exit 0
