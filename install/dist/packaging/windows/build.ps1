$ErrorActionPreference = 'Stop'

$platformRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $platformRoot)
$scriptFile = Join-Path $platformRoot 'EasyALMOS.iss'
$sharedVersionFile = Join-Path $root 'packaging\shared\version.txt'
if (-not (Test-Path -LiteralPath $sharedVersionFile)) {
    throw "Required shared version file is missing: $sharedVersionFile"
}

$version = (Get-Content -LiteralPath $sharedVersionFile | Select-Object -First 1).Trim()
if ([string]::IsNullOrWhiteSpace($version)) {
    throw "Could not read the EasyALMOS version from $sharedVersionFile"
}

$scriptContent = Get-Content -LiteralPath $scriptFile -Raw
if ($scriptContent -notmatch '__EASYALMOS_VERSION__') {
    throw "The Windows installer template does not contain the __EASYALMOS_VERSION__ placeholder: $scriptFile"
}

$outputDir = Join-Path $root "dist\windows"
$outputFile = Join-Path $outputDir "easyalmos-$version.exe"
$generatedScriptFile = Join-Path $platformRoot 'EasyALMOS.generated.iss'

if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

$requiredFiles = @(
    'EasyALMOS.iss',
    'scripts\install_easyalmos.ps1',
    'scripts\launch_easyalmos.pyw',
    'scripts\uninstall_easyalmos.ps1',
    'assets\micromamba-win-64.exe',
    'assets\almos_icon.ico'
)

foreach ($file in $requiredFiles) {
    $path = Join-Path $platformRoot $file
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required installer file is missing: $path"
    }
}

$sharedEnvFile = Join-Path $root 'packaging\shared\almos.yaml'
if (-not (Test-Path -LiteralPath $sharedEnvFile)) {
    throw "Required shared environment file is missing: $sharedEnvFile"
}

$isccCandidates = @(
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$iscc = $isccCandidates |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1

if (-not $iscc) {
    throw 'Inno Setup 6 or 7 was not found. Install it before building EasyALMOS.'
}

Write-Host "Compiling EasyALMOS with: $iscc"
$generatedScriptContent = $scriptContent.Replace('__EASYALMOS_VERSION__', $version)
[System.IO.File]::WriteAllText($generatedScriptFile, $generatedScriptContent, [System.Text.UTF8Encoding]::new($false))
Push-Location $platformRoot
try {
    & $iscc $generatedScriptFile
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $generatedScriptFile) {
        Remove-Item -LiteralPath $generatedScriptFile -Force
    }
}

if (-not (Test-Path -LiteralPath $outputFile)) {
    throw "Compilation finished but the installer was not found: $outputFile"
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $outputFile).Length / 1MB, 2)
Write-Host "Installer created successfully:"
Write-Host "  $outputFile"
Write-Host "  Size: $sizeMb MB"
