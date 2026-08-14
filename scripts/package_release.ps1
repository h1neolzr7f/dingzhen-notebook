param([string]$Version = "1.0.0")
$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$OutputsRoot = [IO.Path]::GetFullPath((Split-Path -Parent $ProjectRoot))
$ReleaseName = "fenbi-study-pipeline-v$Version"
$Stage = [IO.Path]::GetFullPath((Join-Path $OutputsRoot $ReleaseName))
$Archive = [IO.Path]::GetFullPath((Join-Path $OutputsRoot "$ReleaseName.zip"))

if ((Split-Path -Parent $Stage) -ne $OutputsRoot -or (Split-Path -Leaf $Stage) -ne $ReleaseName) {
    throw "Unsafe release staging path: $Stage"
}
if (Test-Path $Stage) {
    Remove-Item -LiteralPath $Stage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$ExcludedDirectories = @(
    ".build-venv", "build", "dist", "tmp", "output", "data",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    (Join-Path $ProjectRoot "apps\android-capture\.gradle"),
    (Join-Path $ProjectRoot "apps\android-capture\app\build")
)
& robocopy.exe $ProjectRoot $Stage /E /NFL /NDL /NJH /NJS /NP `
    /XD $ExcludedDirectories /XF "*.pyc" "fenbi-capture-debug.apk"
if ($LASTEXITCODE -gt 7) { throw "Source staging failed with robocopy exit $LASTEXITCODE" }

$WindowsArtifacts = Join-Path $Stage "artifacts\windows"
New-Item -ItemType Directory -Force -Path $WindowsArtifacts | Out-Null
$WindowsDistribution = Join-Path $ProjectRoot "dist\FenbiStudy-Windows-v$Version.zip"
if (-not (Test-Path $WindowsDistribution)) { throw "Windows distribution is missing" }
$WindowsDestination = Join-Path $WindowsArtifacts "FenbiStudy-Windows-v$Version.zip"
Copy-Item -LiteralPath $WindowsDistribution -Destination $WindowsDestination -Force
$WindowsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $WindowsDestination).Hash.ToLowerInvariant()
[IO.File]::WriteAllText(
    (Join-Path $WindowsArtifacts "FenbiStudy-Windows-v$Version.sha256"),
    "$WindowsHash  FenbiStudy-Windows-v$Version.zip`n",
    [Text.UTF8Encoding]::new($false)
)

if (Test-Path $Archive) { Remove-Item -LiteralPath $Archive -Force }
& tar.exe -a -c -f $Archive -C $OutputsRoot $ReleaseName
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Archive)) { throw "Release archive creation failed" }

$Forbidden = & tar.exe -tf $Archive | Select-String -Pattern "(^|/)(\.build-venv|build|dist|tmp|output|data|__pycache__|\.gradle)(/|$)|\.pyc$|fenbi-capture-debug\.apk$"
if ($Forbidden) { throw "Release archive contains forbidden build/cache files: $Forbidden" }

$ArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$Archive.sha256", "$ArchiveHash  $ReleaseName.zip`n", [Text.UTF8Encoding]::new($false))
Write-Host "Release directory: $Stage"
Write-Host "Release archive: $Archive"
