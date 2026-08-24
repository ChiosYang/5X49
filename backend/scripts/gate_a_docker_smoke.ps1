[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputDir,

    [Parameter(Mandatory = $true)]
    [string]$RunDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$reportSchemaVersion = 1
$scriptRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$backendRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot '..'))
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $backendRoot '..'))
$gateRoot = [System.IO.Path]::GetFullPath((Join-Path $backendRoot 'data\gate-a'))
$runsRoot = [System.IO.Path]::GetFullPath((Join-Path $gateRoot 'runs'))
$resolvedInput = [System.IO.Path]::GetFullPath($InputDir)
$resolvedRun = [System.IO.Path]::GetFullPath($RunDir)
$expectedInput = [System.IO.Path]::GetFullPath((Join-Path $gateRoot 'input'))

if ($resolvedInput -ne $expectedInput) {
    throw 'Docker Gate input must use the fixed input directory contract.'
}
if (-not ($resolvedRun.StartsWith($runsRoot + [System.IO.Path]::DirectorySeparatorChar))) {
    throw 'Docker Gate run directory is outside backend/data/gate-a/runs.'
}

$sourceDatabase = Join-Path $resolvedInput 'library.db'
$mediaRootFile = Join-Path $resolvedInput 'media-root.txt'
$localReport = Join-Path $resolvedRun 'local-report.json'
if (-not (Test-Path -LiteralPath $sourceDatabase -PathType Leaf) -or
    -not (Test-Path -LiteralPath $mediaRootFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath $localReport -PathType Leaf)) {
    throw 'Docker Gate requires the fixed input files and a completed local report.'
}

$mediaRoot = [System.IO.Path]::GetFullPath((Get-Content -LiteralPath $mediaRootFile -Raw -Encoding UTF8).Trim())
if (-not (Test-Path -LiteralPath $mediaRoot -PathType Container)) {
    throw 'Docker Gate media root does not exist.'
}

$runId = [System.IO.Path]::GetFileName($resolvedRun)
$safeRunId = ($runId -replace '[^A-Za-z0-9_.-]', '-').ToLowerInvariant()
$projectName = "gatea-$safeRunId"
$backendImage = "5x49-gatea-backend:$safeRunId"
$frontendImage = "5x49-gatea-frontend:$safeRunId"
$dockerRoot = Join-Path $resolvedRun 'docker'
$upgradeData = Join-Path $dockerRoot 'upgrade-data'
$freshData = Join-Path $dockerRoot 'fresh-data'
$restoreData = Join-Path $dockerRoot 'restore-data'
$composeFile = Join-Path $dockerRoot 'compose.gate-a.yml'
$dockerReport = Join-Path $resolvedRun 'docker-report.json'
$sourceHash = (Get-FileHash -LiteralPath $sourceDatabase -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceSize = (Get-Item -LiteralPath $sourceDatabase).Length
$localEvidence = Get-Content -LiteralPath $localReport -Raw -Encoding UTF8 | ConvertFrom-Json
if ($localEvidence.schema_version -ne $reportSchemaVersion -or
    $localEvidence.local_status -ne 'passed' -or
    $localEvidence.source_fingerprint -ne $sourceHash.Substring(0, 16)) {
    throw 'Docker Gate requires passed local evidence for the unchanged input.'
}
if ((Test-Path -LiteralPath "$sourceDatabase-wal") -or
    (Test-Path -LiteralPath "$sourceDatabase-shm")) {
    throw 'Docker Gate input must remain an offline SQLite copy without sidecars.'
}
if (Test-Path -LiteralPath $dockerRoot) {
    throw 'Docker Gate evidence directory already exists; use a new run ID.'
}
$composeStarted = $false
$backendImageBuilt = $false
$frontendImageBuilt = $false

$phases = [ordered]@{
    compose_config = 'blocked'
    image_build = 'blocked'
    upgrade = 'blocked'
    read_sources = 'blocked'
    fresh_install = 'blocked'
    restore = 'blocked'
    browser_smoke = 'blocked'
}
$checks = [System.Collections.Generic.List[object]]::new()
$checks.Add([ordered]@{
    id = 'docker-isolated-resources'
    status = 'passed'
    details = [ordered]@{ unique_project = $true; isolated_bind_mounts = $true }
})

function Get-RandomPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $captured = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed without publishing captured output."
    }
    return $captured
}

function Wait-BackendHealth {
    param([int]$Port)
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw 'Docker backend health check timed out.'
}

function Get-ApiHashes {
    param([int]$Port)
    $result = [ordered]@{}
    foreach ($endpoint in @('/library', '/library/user-states', '/watch-history')) {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port$endpoint" -TimeoutSec 30
        if ($response.StatusCode -ne 200) { throw 'Compatibility API smoke failed.' }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$response.Content)
        $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
        $result[$endpoint] = [Convert]::ToHexString($hash).ToLowerInvariant()
    }
    return $result
}

function Write-Report {
    param([string]$DockerStatus)
    $unchanged = ((Get-FileHash -LiteralPath $sourceDatabase -Algorithm SHA256).Hash.ToLowerInvariant() -eq $sourceHash) -and
        ((Get-Item -LiteralPath $sourceDatabase).Length -eq $sourceSize)
    $checks.Add([ordered]@{
        id = 'docker-input-unchanged'
        status = $(if ($unchanged) { 'passed' } else { 'failed' })
        details = [ordered]@{ hash_equal = $unchanged; size_equal = $unchanged }
    })
    $effectiveStatus = if (-not $unchanged) { 'failed' } else { $DockerStatus }
    $report = [ordered]@{
        schema_version = $reportSchemaVersion
        run_id = $runId
        source_fingerprint = $sourceHash.Substring(0, 16)
        checks = $checks
        phases = $phases
        local_status = 'blocked'
        docker_status = $effectiveStatus
        overall_status = $(if ($effectiveStatus -eq 'failed') { 'failed' } else { 'blocked' })
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $dockerReport -Encoding UTF8
    $report | ConvertTo-Json -Depth 8
}

New-Item -ItemType Directory -Path $dockerRoot -Force | Out-Null
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $checks.Add([ordered]@{
        id = 'docker-runtime-available'
        status = 'blocked'
        details = [ordered]@{ available = $false }
    })
    Write-Report -DockerStatus 'blocked'
    exit 3
}

$backendPort = Get-RandomPort
$frontendPort = Get-RandomPort
$mediaMount = $mediaRoot.Replace('\', '/')
$upgradeMount = $upgradeData.Replace('\', '/')
$composeYaml = @"
services:
  backend:
    image: $backendImage
    container_name: $projectName-backend
    ports:
      - "${backendPort}:8000"
    volumes:
      - "`${GATE_DATA_DIR}:/app/data"
      - "${mediaMount}:/media:ro"
    environment:
      MEDIA_DIR: /media
      LIBRARY_READ_SOURCE: "`${LIBRARY_READ_SOURCE:-canonical}"
      ALLOWED_ORIGINS: '*'
  frontend:
    image: $frontendImage
    container_name: $projectName-frontend
    ports:
      - "${frontendPort}:3000"
    environment:
      BACKEND_URL: http://backend:8000
    depends_on:
      - backend
"@
$composeYaml | Set-Content -LiteralPath $composeFile -Encoding UTF8

try {
    $env:MEDIA_DIR = $mediaRoot
    Invoke-Docker compose -f (Join-Path $repoRoot 'docker-compose.yml') config | Out-Null
    Invoke-Docker compose -f (Join-Path $repoRoot 'docker-compose.release.yml') config | Out-Null
    $env:GATE_DATA_DIR = $upgradeMount
    Invoke-Docker compose -p $projectName -f $composeFile config | Out-Null
    $phases.compose_config = 'passed'

    Invoke-Docker build -t $backendImage $backendRoot | Out-Null
    $backendImageBuilt = $true
    Invoke-Docker build -t $frontendImage (Join-Path $repoRoot 'frontend') | Out-Null
    $frontendImageBuilt = $true
    $phases.image_build = 'passed'

    New-Item -ItemType Directory -Path $upgradeData -Force | Out-Null
    Copy-Item -LiteralPath $sourceDatabase -Destination (Join-Path $upgradeData 'library.db')
    $env:LIBRARY_READ_SOURCE = 'canonical'
    Invoke-Docker compose -p $projectName -f $composeFile up -d | Out-Null
    $composeStarted = $true
    Wait-BackendHealth -Port $backendPort
    $canonicalHashes = Get-ApiHashes -Port $backendPort
    $phases.upgrade = 'passed'

    $readHashesEqual = $true
    foreach ($source in @('shadow', 'legacy')) {
        $env:LIBRARY_READ_SOURCE = $source
        Invoke-Docker compose -p $projectName -f $composeFile up -d --force-recreate backend | Out-Null
        Wait-BackendHealth -Port $backendPort
        $candidate = Get-ApiHashes -Port $backendPort
        foreach ($endpoint in $canonicalHashes.Keys) {
            if ($candidate[$endpoint] -ne $canonicalHashes[$endpoint]) { $readHashesEqual = $false }
        }
    }
    if (-not $readHashesEqual) { throw 'Canonical, shadow, and legacy API response hashes differ.' }
    $phases.read_sources = 'passed'

    $env:LIBRARY_READ_SOURCE = 'canonical'
    Invoke-Docker compose -p $projectName -f $composeFile up -d --force-recreate | Out-Null
    Wait-BackendHealth -Port $backendPort
    foreach ($locale in @('en', 'zh')) {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$frontendPort/$locale/library" -TimeoutSec 30
        if ($response.StatusCode -ne 200) { throw 'Localized frontend smoke failed.' }
    }
    $phases.browser_smoke = 'passed'

    Invoke-Docker compose -p $projectName -f $composeFile down --remove-orphans | Out-Null
    $composeStarted = $false
    New-Item -ItemType Directory -Path $freshData -Force | Out-Null
    $env:GATE_DATA_DIR = $freshData.Replace('\', '/')
    Invoke-Docker compose -p $projectName -f $composeFile up -d backend | Out-Null
    $composeStarted = $true
    Wait-BackendHealth -Port $backendPort
    $phases.fresh_install = 'passed'

    Invoke-Docker compose -p $projectName -f $composeFile down --remove-orphans | Out-Null
    $composeStarted = $false
    New-Item -ItemType Directory -Path $restoreData -Force | Out-Null
    Copy-Item -LiteralPath $sourceDatabase -Destination (Join-Path $restoreData 'library.db')
    $env:GATE_DATA_DIR = $restoreData.Replace('\', '/')
    Invoke-Docker compose -p $projectName -f $composeFile up -d backend | Out-Null
    $composeStarted = $true
    Wait-BackendHealth -Port $backendPort
    Get-ApiHashes -Port $backendPort | Out-Null
    $phases.restore = 'passed'

    $checks.Add([ordered]@{
        id = 'docker-runtime-available'
        status = 'passed'
        details = [ordered]@{ available = $true }
    })
    Write-Report -DockerStatus 'passed'
    exit 0
} catch {
    $checks.Add([ordered]@{
        id = 'docker-runtime-completed'
        status = 'failed'
        details = [ordered]@{ completed = $false; phase_names_only = $true }
    })
    Write-Report -DockerStatus 'failed'
    exit 2
} finally {
    if ($composeStarted) {
        try { Invoke-Docker compose -p $projectName -f $composeFile down --remove-orphans | Out-Null } catch { }
    }
    if ($backendImageBuilt) {
        try { Invoke-Docker image rm $backendImage | Out-Null } catch { }
    }
    if ($frontendImageBuilt) {
        try { Invoke-Docker image rm $frontendImage | Out-Null } catch { }
    }
    Remove-Item Env:LIBRARY_READ_SOURCE -ErrorAction SilentlyContinue
    Remove-Item Env:GATE_DATA_DIR -ErrorAction SilentlyContinue
}
