param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,

    [Parameter(Mandatory = $true)]
    [string]$StateDir
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$installRoot = [System.IO.Path]::GetFullPath($InstallDir)
$successFile = Join-Path $StateDir 'success.flag'
$failureFile = Join-Path $StateDir 'failure.txt'
$targets = @(
    (Join-Path $installRoot 'miniforge'),
    (Join-Path $installRoot 'logs')
)

try {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

    foreach ($target in $targets) {
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }

    Set-Content -LiteralPath $successFile -Value 'ok' -Encoding ASCII
    exit 0
}
catch {
    [System.IO.File]::WriteAllText(
        $failureFile,
        $_.Exception.Message,
        [System.Text.Encoding]::ASCII
    )
    exit 1
}
