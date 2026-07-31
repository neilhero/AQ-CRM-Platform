param(
    [string]$Server = "root@121.41.66.121",
    [string]$RemoteIndex = "/opt/aq-crm/frontend/index.html",
    [string]$RemoteAdmin = "/opt/aq-crm/frontend/admin.html",
    [string]$RemoteVersion = "/opt/aq-crm/frontend/static/version.js"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$indexPath = Join-Path $repoRoot "frontend\index.html"
$adminPath = Join-Path $repoRoot "frontend\admin.html"
$versionPath = Join-Path $repoRoot "frontend\static\version.js"

& (Join-Path $PSScriptRoot "sync-version.ps1") -Check

if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Frontend entry file not found: $indexPath"
}
if (-not (Test-Path -LiteralPath $adminPath) -or -not (Test-Path -LiteralPath $versionPath)) {
    throw "Frontend release files are incomplete."
}

$frontendSource = [System.IO.File]::ReadAllText($indexPath)
$requiredMarkers = [ordered]@{
    "industry donut dashboard" = "industry-donut-layout"
    "probability ring dashboard" = "probability-rings"
    "hidden trailing sales-ranking amount" = "style: { display: 'none' }"
    "opportunity presales spacing" = "opportunity-presales-card"
    "required expected close date" = "name: 'expected_close_date'"
    "contact department field" = "department:''"
    "unified opportunity detail layout" = "opportunity-detail-unified-layout"
    "opportunity detail created time" = "opp.created_at ? dayjs(opp.created_at).format('YYYY-MM-DD HH:mm')"
    "opportunity detail customer pain point" = "opp.pain_points || '-'"
    "direct opportunity required final customer" = "name: 'customer_id', label:"
    "channel opportunity required partner" = "name: 'channel_partner_id', label:"
    "channel opportunity required final customer" = "name: 'end_customer_name', label:"
}

foreach ($marker in $requiredMarkers.GetEnumerator()) {
    if (-not $frontendSource.Contains($marker.Value)) {
        throw "Frontend regression check failed: $($marker.Key)"
    }
}

$releaseFiles = @(
    @{ Local = $indexPath; Remote = $RemoteIndex },
    @{ Local = $adminPath; Remote = $RemoteAdmin },
    @{ Local = $versionPath; Remote = $RemoteVersion }
)

# The production fallback path is a symlink to index.html. Uploading both files
# would write the second file through that symlink and overwrite the main page.
foreach ($releaseFile in $releaseFiles) {
    $localHash = (Get-FileHash -LiteralPath $releaseFile.Local -Algorithm SHA256).Hash.ToLowerInvariant()
    scp $releaseFile.Local "${Server}:$($releaseFile.Remote)"
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend upload failed: $($releaseFile.Local)"
    }
    $remoteHash = (ssh $Server "sha256sum '$($releaseFile.Remote)' | cut -d' ' -f1").Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $remoteHash -ne $localHash) {
        throw "Frontend hash verification failed: $($releaseFile.Local)"
    }
}

$version = (Get-Content -LiteralPath (Join-Path $repoRoot "VERSION") -Raw).Trim()
Write-Host "Frontend deployed and verified: v$version"
