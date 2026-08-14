param([string]$Output = "artifacts\android", [switch]$NoClean)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AndroidRoot = Join-Path $ProjectRoot "apps\android-capture"
$ResolvedOutput = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Output))
New-Item -ItemType Directory -Force -Path $ResolvedOutput | Out-Null
Push-Location $AndroidRoot
try {
  $Tasks = if ($NoClean) { @("testDebugUnitTest", "assembleRelease") } else { @("clean", "testDebugUnitTest", "assembleRelease") }
  .\gradlew.bat @Tasks --no-daemon --console=plain
} finally {
  Pop-Location
}
$Apk = Join-Path $AndroidRoot "app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path $Apk)) { throw "Release APK was not produced" }
$Destination = Join-Path $ResolvedOutput "fenbi-capture-personal-release.apk"
Copy-Item -LiteralPath $Apk -Destination $Destination -Force
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash
[IO.File]::WriteAllText((Join-Path $ResolvedOutput "fenbi-capture-personal-release.sha256"), "$Hash  fenbi-capture-personal-release.apk`n", [Text.UTF8Encoding]::new($false))
Write-Host "Android release artifact: $Destination"
