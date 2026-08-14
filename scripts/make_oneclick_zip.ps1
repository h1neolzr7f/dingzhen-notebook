param([string]$Version = "1.3.4")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Name = "DingzhenNotebook-OneClick-v$Version"
$StageParent = Join-Path $env:TEMP "dingzhen-oneclick"
$Stage = Join-Path $StageParent "$Name-$(Get-Date -Format yyyyMMddHHmmss)"
$Desktop = [Environment]::GetFolderPath("Desktop")
$OutDir = Join-Path $Root "artifacts\windows"
New-Item -ItemType Directory -Force -Path $StageParent, $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$skipNames = @(
    ".venv", ".git", ".idea", ".pytest_cache", "__pycache__",
    "fenbi_study_pipeline.egg-info", "data", "exports", "artifacts"
)
Get-ChildItem -LiteralPath $Root -Force | Where-Object {
    $skipNames -notcontains $_.Name
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Stage $_.Name) -Recurse -Force
}

$drop = @(
    (Join-Path $Stage "apps\android-capture\.gradle"),
    (Join-Path $Stage "apps\android-capture\app\build"),
    (Join-Path $Stage "apps\android-capture\.cxx")
)
foreach ($path in $drop) {
    if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
Get-ChildItem -LiteralPath $Stage -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

$apk = Join-Path $Root "apps\android-capture\app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $apk)) {
    $apk = Join-Path $Desktop "丁真笔记本-$Version.apk"
}
if (Test-Path $apk) {
    Copy-Item $apk (Join-Path $Stage "dingzhen-notebook-$Version.apk") -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $Stage "data"), (Join-Path $Stage "exports") | Out-Null

$zip = Join-Path $OutDir "$Name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $zip -Force
Copy-Item $zip (Join-Path $Desktop "$Name.zip") -Force
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -Path "$zip.sha256" -Value "$hash  $Name.zip" -Encoding ascii
Write-Host "ZIP $zip"
Write-Host "SHA256 $hash"
Write-Host "SIZE $((Get-Item $zip).Length)"
