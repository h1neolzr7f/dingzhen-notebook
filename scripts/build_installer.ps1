param([string]$Output = "dist", [switch]$ReusePortableZip)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$ResolvedOutput = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Output))
$Staging = Join-Path $ProjectRoot "build\installer-staging"
New-Item -ItemType Directory -Force -Path $Staging, $ResolvedOutput | Out-Null
$PortableZip = Join-Path $Staging "FenbiStudy.zip"
if (-not $ReusePortableZip -or -not (Test-Path $PortableZip)) {
  if (Test-Path $PortableZip) { Remove-Item -LiteralPath $PortableZip -Force }
  Compress-Archive -Path (Join-Path $ResolvedOutput "FenbiStudy\*") -DestinationPath $PortableZip -CompressionLevel Optimal
}
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PortableZip).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $Staging "FenbiStudy.sha256"), "$Hash  FenbiStudy.zip`n", [Text.UTF8Encoding]::new($false))
Copy-Item -LiteralPath "config\update.json" -Destination (Join-Path $Staging "update.json") -Force
Copy-Item -LiteralPath "config\stability.json" -Destination (Join-Path $Staging "stability.json") -Force
$Installer = Join-Path $Staging "FenbiStudy-Installer.exe"
$Csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $Csc /nologo /target:winexe /optimize+ /out:$Installer `
  /reference:System.Windows.Forms.dll `
  /reference:System.IO.Compression.dll `
  /reference:System.IO.Compression.FileSystem.dll `
  scripts\FenbiStudyInstaller.cs
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Installer)) { throw "Installer compilation failed" }
& $Installer /verify-only
if ($LASTEXITCODE -ne 0) { throw "Installer verification smoke test failed" }
$Distribution = Join-Path $ResolvedOutput "FenbiStudy-Windows-v1.0.0.zip"
if (Test-Path $Distribution) { Remove-Item -LiteralPath $Distribution -Force }
& tar.exe -a -c -f $Distribution -C $Staging `
  FenbiStudy-Installer.exe FenbiStudy.zip FenbiStudy.sha256 update.json stability.json
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Distribution)) { throw "Windows distribution archive failed" }
$Entries = & tar.exe -tf $Distribution
if ($LASTEXITCODE -ne 0 -or $Entries.Count -ne 5) { throw "Windows distribution archive validation failed" }
Write-Host "Windows distribution: $Distribution"
