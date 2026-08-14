param(
  [string]$Output = "dist",
  [switch]$SkipOcr,
  [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$BuildVenv = Join-Path $ProjectRoot ".build-venv"
$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not (Test-Path (Join-Path $BuildVenv "Scripts\python.exe"))) {
  if ($Uv) {
    uv venv --python 3.12 $BuildVenv
  } else {
    py -3.12 -m venv $BuildVenv
  }
}
$Python = Join-Path $BuildVenv "Scripts\python.exe"
if ($Uv) {
  $Requirements = if ($SkipOcr) { "requirements-dev.lock" } else { "requirements-build.lock" }
  uv pip install --python $Python -r $Requirements
  if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
  uv pip install --python $Python --no-deps -e .
  if ($LASTEXITCODE -ne 0) { throw "Project installation failed" }
} else {
  $Requirements = if ($SkipOcr) { "requirements-dev.lock" } else { "requirements-build.lock" }
  & $Python -m pip install -r $Requirements
  if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
  & $Python -m pip install --no-deps -e .
  if ($LASTEXITCODE -ne 0) { throw "Project installation failed" }
}
& $Python -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
& $Python -m compileall -q apps packages
if ($LASTEXITCODE -ne 0) { throw "Compileall failed" }

$ResolvedOutput = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Output))
New-Item -ItemType Directory -Force -Path $ResolvedOutput | Out-Null
$Work = Join-Path $ProjectRoot "build\pyinstaller"
$PromptData = "$(Join-Path $ProjectRoot 'prompts');prompts"
$ConfigData = "$(Join-Path $ProjectRoot 'config');config"
$SchemaData = "$(Join-Path $ProjectRoot 'schemas');schemas"
$PaddleLibraries = "$(Join-Path $BuildVenv 'Lib\site-packages\paddle\libs');paddle\libs"
& $Python -m PyInstaller `
  --noconfirm --clean --windowed --onedir `
  --name FenbiStudy `
  --distpath $ResolvedOutput `
  --workpath $Work `
  --specpath (Join-Path $ProjectRoot "build") `
  --paths $ProjectRoot `
  --hidden-import apps.desktop.gui `
  --collect-submodules apps `
  --collect-submodules packages `
  --collect-all paddleocr `
  --collect-all paddlex `
  --copy-metadata imagesize `
  --copy-metadata opencv-contrib-python `
  --copy-metadata pyclipper `
  --copy-metadata pypdfium2 `
  --copy-metadata python-bidi `
  --copy-metadata shapely `
  --add-binary $PaddleLibraries `
  --add-data $PromptData `
  --add-data $ConfigData `
  --add-data $SchemaData `
  scripts\fenbi_study_entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if (-not $SkipInstaller) {
  & (Join-Path $PSScriptRoot "build_installer.ps1") -Output $Output
  if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
}
Write-Host "Windows artifacts written to $ResolvedOutput"
