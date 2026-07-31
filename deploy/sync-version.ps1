param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $repoRoot "VERSION"
$frontendVersionPath = Join-Path $repoRoot "frontend\static\version.js"

if (-not (Test-Path -LiteralPath $versionPath)) {
    throw "Version file not found: $versionPath"
}

$version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') {
    throw "VERSION must use semantic versioning, for example 3.7.0. Current value: $version"
}

$content = @"
// Generated from the repository-level VERSION file by deploy/sync-version.ps1.
window.AQ_CRM_VERSION = "$version";
"@.TrimEnd() + [Environment]::NewLine

if ($Check) {
    if (-not (Test-Path -LiteralPath $frontendVersionPath) -or (Get-Content -LiteralPath $frontendVersionPath -Raw) -ne $content) {
        throw "Frontend version file is out of sync. Run .\deploy\sync-version.ps1 before committing."
    }
    Write-Host "Version files are synchronized: v$version"
    return
}

Set-Content -LiteralPath $frontendVersionPath -Value $content -Encoding UTF8 -NoNewline
Write-Host "Synchronized release version: v$version"
