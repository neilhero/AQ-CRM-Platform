param(
    [Parameter(Mandatory = $true)]
    [string]$Snapshot,
    [string]$Server = "root@121.41.66.121",
    [string]$ServiceName = "aq-crm",
    [switch]$RestoreDatabase
)

$ErrorActionPreference = "Stop"

if ($Snapshot -notmatch '^/opt/aq-crm/backups/releases/pre-v[0-9A-Za-z._-]+$') {
    throw "Snapshot must be an absolute release snapshot path under /opt/aq-crm/backups/releases."
}

$restoreCommand = "set -e; test -f '$Snapshot/frontend/index.html'; cp '$Snapshot/frontend/index.html' /opt/aq-crm/frontend/index.html; test -f '$Snapshot/frontend/admin.html' && cp '$Snapshot/frontend/admin.html' /opt/aq-crm/frontend/admin.html || true; test -f '$Snapshot/frontend/version.js' && cp '$Snapshot/frontend/version.js' /opt/aq-crm/frontend/static/version.js || true; test -f '$Snapshot/backend/app.tar.gz' && tar -C /opt/aq-crm/backend -xzf '$Snapshot/backend/app.tar.gz' || true"
if ($RestoreDatabase) {
    $restoreCommand += '; db=$(find ' + $Snapshot + '/database -maxdepth 1 -name "*.db" -type f | head -n 1); test -n "$db"; cp "$db" /opt/aq-crm/backend/aq_crm.db'
}
$restoreCommand += "; systemctl restart $ServiceName; systemctl is-active --quiet $ServiceName"

ssh $Server $restoreCommand
if ($LASTEXITCODE -ne 0) { throw "Rollback failed." }

Write-Host "Rollback completed from $Snapshot"
if (-not $RestoreDatabase) {
    Write-Host "Database was intentionally not restored. Use -RestoreDatabase only when data rollback is required."
}
