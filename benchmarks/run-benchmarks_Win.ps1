# Runs the accuracy benchmark, then the single-search speed benchmark.
# Edit the settings below, then run this script from PowerShell:
#   Set-Location benchmarks
#   .\run-benchmarks_Win.ps1
#
# Requires Docker Desktop. R and the tidyverse run inside the container.
# The container scripts must use Unix line endings.

$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$AccuracyPrefix = 'accuracy-test-all-terms'
$SpeedWorkloads = '500'
$Repeats = 5
$SpeedPrefix = "speed-test-$SpeedWorkloads-terms-$Repeats-repeats"

$BenchDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $BenchDir
$ImageName = if ($env:MAPTOLOGY_BENCHMARK_IMAGE) { $env:MAPTOLOGY_BENCHMARK_IMAGE } else { 'maptology-benchmark-single-search' }
$ContainerName = if ($env:MAPTOLOGY_BENCHMARK_CONTAINER) { $env:MAPTOLOGY_BENCHMARK_CONTAINER } else { 'maptology-benchmark-single-search' }

function Invoke-Docker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments[0]) failed with exit code $LASTEXITCODE"
    }
}

function Convert-ToDockerMount {
    param(
        [Parameter(Mandatory = $true)][string]$HostPath,
        [Parameter(Mandatory = $true)][string]$ContainerPath,
        [string]$Options
    )
    $normalized = (Resolve-Path -LiteralPath $HostPath).Path -replace '\\', '/'
    if ($Options) {
        return "${normalized}:${ContainerPath}:${Options}"
    }
    return "${normalized}:${ContainerPath}"
}

function Initialize-BenchmarkDirectories {
    foreach ($name in @('inputs', 'sources', 'assets', 'runs', 'results', 'raw')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $BenchDir $name) | Out-Null
    }
}

function Build-BenchmarkImage {
    if ($env:MAPTOLOGY_SKIP_IMAGE_BUILD -eq '1') {
        $runtime = docker image inspect --format '{{ index .Config.Labels "maptology.graph_runtime" }}' $ImageName 2>$null
        if ($LASTEXITCODE -eq 0 -and $runtime -eq 'r-tidyverse') {
            Write-Host "Reusing image '$ImageName' (already built in this run)."
            return
        }
        Write-Host "Rebuilding image '$ImageName' so the charts can be created inside the container."
    }

    Write-Host "Staging build context for '$ImageName'..."
    $stage = Join-Path ([System.IO.Path]::GetTempPath()) ("maptology-bench-" + [guid]::NewGuid().ToString('n'))
    try {
        $benchDest = Join-Path $stage 'benchmarks'
        New-Item -ItemType Directory -Force -Path $benchDest | Out-Null
        $exclude = @('runs', 'sources', 'assets', 'inputs', '__pycache__', '.DS_Store')
        Get-ChildItem -Force -LiteralPath $BenchDir | ForEach-Object {
            if ($exclude -contains $_.Name) { return }
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $benchDest $_.Name) -Recurse -Force
        }
        @(Get-ChildItem -LiteralPath $benchDest -Recurse -Force -Directory -Filter '__pycache__') |
            Remove-Item -Recurse -Force
        Get-ChildItem -LiteralPath $benchDest -Recurse -Force -File |
            Where-Object { $_.Name -eq '.DS_Store' -or $_.Extension -eq '.pyc' } |
            Remove-Item -Force
        $rawDir = Join-Path $benchDest 'raw'
        if (Test-Path -LiteralPath $rawDir) {
            Get-ChildItem -LiteralPath $rawDir -Filter '*.tsv.gz' -File | Remove-Item -Force
        }
        $buildDest = Join-Path $stage 'build'
        New-Item -ItemType Directory -Force -Path $buildDest | Out-Null
        Copy-Item -LiteralPath (Join-Path $RepoRoot 'build\build_all_caches.py') -Destination (Join-Path $buildDest 'build_all_caches.py')

        Write-Host "Building image '$ImageName'..."
        Invoke-Docker -Arguments @('build', '-f', (Join-Path $benchDest 'Dockerfile'), '-t', $ImageName, $stage)
    }
    finally {
        if (Test-Path -LiteralPath $stage) {
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
    }
}

function Get-ContainerUserSpec {
    $idCommand = Get-Command id -ErrorAction SilentlyContinue
    if (-not $idCommand) {
        $gitId = Join-Path $env:ProgramFiles 'Git\usr\bin\id.exe'
        if (Test-Path -LiteralPath $gitId) {
            $idCommand = $gitId
        }
    }
    $uid = $null
    $gid = $null
    $userName = $null
    if ($idCommand) {
        $uid = "$((& $idCommand -u).Trim())"
        $gid = "$((& $idCommand -g).Trim())"
        $userName = "$((& $idCommand -un).Trim())"
    } elseif ($env:UID -match '^\d+$' -and $env:GID -match '^\d+$') {
        $uid = $env:UID
        $gid = $env:GID
        $userName = $env:USERNAME
    }
    if ($uid -notmatch '^\d+$' -or $gid -notmatch '^\d+$') {
        throw "Could not determine the current numeric user and group ids. Install Git for Windows, or set the UID and GID environment variables."
    }
    if (-not $userName) {
        $userName = $env:USERNAME
    }
    return @{
        Spec = "${uid}:${gid}"
        Name = $userName
    }
}

function Invoke-BenchmarkContainer {
    param(
        [Parameter(Mandatory = $true)][string]$Entrypoint,
        [string[]]$Arguments
    )
    Initialize-BenchmarkDirectories
    $names = docker ps -a --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) {
        throw "docker ps failed with exit code $LASTEXITCODE"
    }
    if ($names -split "`n" | Where-Object { $_.Trim() -eq $ContainerName }) {
        Write-Host "Removing existing container '$ContainerName'..."
        Invoke-Docker -Arguments @('rm', '-f', $ContainerName) | Out-Null
    }

    Write-Host "Starting container '$ContainerName'..."
    Write-Host 'Persistent host dirs: inputs sources assets runs results raw'
    $containerUser = Get-ContainerUserSpec
    $dockerArgs = @(
        'run', '--name', $ContainerName, '--rm',
        '--user', $containerUser.Spec,
        '--entrypoint', $Entrypoint,
        '-e', 'PYTHONDONTWRITEBYTECODE=1',
        '-e', 'PYTHONHASHSEED=0',
        '-e', 'PYTHONUTF8=1',
        '-e', 'HOME=/tmp',
        '-e', 'USER', $containerUser.Name,
        '-e', 'LOGNAME', $containerUser.Name,
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'code') '/app/benchmarks/code' 'ro'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'scripts') '/app/benchmarks/scripts' 'ro'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'inputs') '/app/benchmarks/inputs'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'sources') '/app/benchmarks/sources'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'assets') '/app/benchmarks/assets'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'runs') '/app/benchmarks/runs'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'results') '/app/benchmarks/results'),
        '-v', (Convert-ToDockerMount (Join-Path $BenchDir 'raw') '/app/benchmarks/raw'),
        $ImageName
    ) + $Arguments
    Invoke-Docker -Arguments $dockerArgs
}

if ($SpeedWorkloads -ne 'full' -and $SpeedWorkloads -notmatch '^[1-9][0-9]*$') {
    throw "SPEED_WORKLOADS must be a positive integer or full (got: $SpeedWorkloads)"
}
if ("$Repeats" -notmatch '^[1-9][0-9]*$') {
    throw "REPEATS must be a positive integer (got: $Repeats)"
}

$accuracyTsv = Join-Path $BenchDir "results\$AccuracyPrefix.tsv"
$accuracyPdf = Join-Path $BenchDir "results\$AccuracyPrefix.pdf"
if ((Test-Path -LiteralPath $accuracyTsv) -and (Test-Path -LiteralPath $accuracyPdf)) {
    Write-Host 'Accuracy benchmark will not be executed because the output files already exist:'
    Write-Host "  $accuracyTsv"
    Write-Host "  $accuracyPdf"
}
elseif (Test-Path -LiteralPath $accuracyTsv) {
    Write-Host 'Accuracy benchmark will not be executed because the results already exist:'
    Write-Host "  $accuracyTsv"
    Write-Host 'Creating accuracy graph...'
    Build-BenchmarkImage
    Invoke-BenchmarkContainer 'Rscript' @(
        'code/create_figures.R',
        "results/$AccuracyPrefix.tsv",
        "results/$AccuracyPrefix.pdf"
    )
}
else {
    Build-BenchmarkImage
    Write-Host 'Accuracy scores every evaluation row for six methods (text2term is the slow part).'
    Invoke-BenchmarkContainer './scripts/container-run-accuracy.sh' @('--output-prefix', $AccuracyPrefix)
}

$speedTsv = Join-Path $BenchDir "results\$SpeedPrefix.tsv"
$speedPdf = Join-Path $BenchDir "results\$SpeedPrefix.pdf"
if ((Test-Path -LiteralPath $speedTsv) -and (Test-Path -LiteralPath $speedPdf)) {
    Write-Host 'Speed benchmark will not be executed because the output files already exist:'
    Write-Host "  $speedTsv"
    Write-Host "  $speedPdf"
    return
}
if (Test-Path -LiteralPath $speedTsv) {
    Write-Host 'Speed benchmark will not be executed because the results already exist:'
    Write-Host "  $speedTsv"
    Write-Host 'Creating speed graph...'
    Build-BenchmarkImage
    Invoke-BenchmarkContainer 'Rscript' @(
        'code/create_figures.R', '--speed',
        "results/$SpeedPrefix.tsv",
        "results/$SpeedPrefix.pdf"
    )
    return
}

$env:MAPTOLOGY_SKIP_IMAGE_BUILD = '1'
Build-BenchmarkImage
if ($SpeedWorkloads -eq 'full') {
    Write-Host 'A full speed run can take many hours because text2term searches one string at a time.'
}
Invoke-BenchmarkContainer './scripts/container-run-speed.sh' @(
    '--workloads', "$SpeedWorkloads",
    '--repeats', "$Repeats",
    '--output-prefix', $SpeedPrefix
)
