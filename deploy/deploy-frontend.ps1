param(
    [string]$Server = "root@121.41.66.121",
    [string]$RemoteIndex = "/opt/aq-crm/frontend/index.html"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$indexPath = Join-Path $repoRoot "frontend\index.html"

if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "Frontend entry file not found: $indexPath"
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
}

foreach ($marker in $requiredMarkers.GetEnumerator()) {
    if (-not $frontendSource.Contains($marker.Value)) {
        throw "Frontend regression check failed: $($marker.Key)"
    }
}

$indexHash = (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash.ToLowerInvariant()

# The production fallback path is a symlink to index.html. Uploading both files
# would write the second file through that symlink and overwrite the main page.
scp $indexPath "${Server}:$RemoteIndex"
if ($LASTEXITCODE -ne 0) {
    throw "Frontend upload failed."
}

$remoteHash = (ssh $Server "sha256sum '$RemoteIndex' | cut -d' ' -f1").Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $remoteHash -ne $indexHash) {
    throw "Frontend hash verification failed. Local: $indexHash; remote: $remoteHash"
}

Write-Host "Frontend deployed and verified: $indexHash"
