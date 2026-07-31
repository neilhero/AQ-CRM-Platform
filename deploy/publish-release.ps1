param(
    [string]$Server = "root@121.41.66.121",
    [string]$ServiceName = "aq-crm",
    [switch]$SkipNginxReload,
    [switch]$SkipDatabaseBackup
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $repoRoot "VERSION") -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') {
    throw "VERSION must use semantic versioning."
}

& (Join-Path $PSScriptRoot "sync-version.ps1") -Check

$pendingChanges = git -C $repoRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect Git status." }
if ($pendingChanges) {
    throw "Release stopped: commit or stash all local changes first. This prevents an untracked local file from reaching production."
}

$commit = (git -C $repoRoot rev-parse HEAD).Trim()
$tag = "v$version"
$tagCommit = (git -C $repoRoot rev-list -n 1 $tag 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $tagCommit) {
    throw "Release stopped: Git tag $tag is missing. Create it with: git tag -a $tag -m '安泉CRM $tag'"
}
if ($tagCommit -ne $commit) {
    throw "Release stopped: tag $tag must point to the current commit."
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapshot = "/opt/aq-crm/backups/releases/pre-v$version-$stamp"

# Snapshot production before any file is overwritten. Database restore remains an
# explicit rollback choice, while files can always be restored from this folder.
$backupCommand = "set -e; mkdir -p '$snapshot/frontend' '$snapshot/backend'; cp -a /opt/aq-crm/frontend/index.html '$snapshot/frontend/' 2>/dev/null || true; cp -a /opt/aq-crm/frontend/admin.html '$snapshot/frontend/' 2>/dev/null || true; cp -a /opt/aq-crm/frontend/static/version.js '$snapshot/frontend/' 2>/dev/null || true; tar -C /opt/aq-crm/backend -czf '$snapshot/backend/app.tar.gz' app scripts requirements.txt 2>/dev/null || true"
if (-not $SkipDatabaseBackup) {
    $backupCommand += "; cd /opt/aq-crm/backend; python3 scripts/backup_db.py --out-dir '$snapshot/database'"
}
ssh $Server $backupCommand
if ($LASTEXITCODE -ne 0) { throw "Production snapshot failed. Release was not deployed." }

& (Join-Path $PSScriptRoot "deploy-backend.ps1") -Server $Server -ServiceName $ServiceName
& (Join-Path $PSScriptRoot "deploy-frontend.ps1") -Server $Server

if (-not $SkipNginxReload) {
    $nginxConfig = Join-Path $PSScriptRoot "nginx\aq-crm.conf"
    scp $nginxConfig "${Server}:/etc/nginx/sites-available/aq-crm.conf"
    if ($LASTEXITCODE -ne 0) { throw "Nginx configuration upload failed." }
    ssh $Server "nginx -t && systemctl reload nginx"
    if ($LASTEXITCODE -ne 0) { throw "Nginx reload failed." }
}

$manifest = [ordered]@{
    version = $version
    git_commit = $commit
    deployed_at = (Get-Date).ToUniversalTime().ToString("o")
    snapshot = $snapshot
} | ConvertTo-Json
$manifestPath = Join-Path $env:TEMP "aq-crm-release-$version.json"
Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding UTF8
scp $manifestPath "${Server}:/opt/aq-crm/release.json"
Remove-Item -LiteralPath $manifestPath -Force

Write-Host "Release v$version deployed. Snapshot: $snapshot"
Write-Host "Next: git push origin main --follow-tags"
