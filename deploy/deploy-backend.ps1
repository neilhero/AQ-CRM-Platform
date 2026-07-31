param(
    [string]$Server = "root@121.41.66.121",
    [string]$RemoteBackend = "/opt/aq-crm/backend",
    [string]$ServiceName = "aq-crm"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repoRoot "backend"
$versionPath = Join-Path $repoRoot "VERSION"

if (-not (Test-Path -LiteralPath $versionPath)) {
    throw "Version file not found: $versionPath"
}

& (Join-Path $PSScriptRoot "sync-version.ps1") -Check

# Keep the backend package and operational scripts together so server code cannot
# be newer than its backup/restore utilities.
scp -r (Join-Path $backendPath "app") (Join-Path $backendPath "scripts") (Join-Path $backendPath "requirements.txt") "${Server}:$RemoteBackend/"
if ($LASTEXITCODE -ne 0) {
    throw "Backend upload failed."
}

scp $versionPath "${Server}:/opt/aq-crm/VERSION"
if ($LASTEXITCODE -ne 0) {
    throw "Version file upload failed."
}

ssh $Server "systemctl restart $ServiceName && systemctl is-active --quiet $ServiceName"
if ($LASTEXITCODE -ne 0) {
    throw "Backend service restart failed."
}

$version = (Get-Content -LiteralPath $versionPath -Raw).Trim()
$remoteVersion = ""
$expectedVersionPattern = ('\"version\"\s*:\s*\"' + [regex]::Escape($version) + '\"')
for ($attempt = 1; $attempt -le 15; $attempt++) {
    $remoteVersion = (ssh $Server "curl -fsS http://127.0.0.1:8097/api/system/version" 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $remoteVersion -match $expectedVersionPattern) {
        break
    }
    Start-Sleep -Seconds 1
}
if ($remoteVersion -notmatch $expectedVersionPattern) {
    throw "Backend version verification failed. Expected v$version; response: $remoteVersion"
}

Write-Host "Backend deployed and verified: v$version"
