param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,

    [Parameter(Mandatory = $true)]
    [string]$MiniforgeInstaller,

    [Parameter(Mandatory = $true)]
    [string]$EnvFile,

    [Parameter(Mandatory = $true)]
    [string]$StateDir
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$installRoot = [System.IO.Path]::GetFullPath($InstallDir)
$miniforgeDir = Join-Path $installRoot 'miniforge'
$logsDir = Join-Path $installRoot 'logs'
$condaExe = Join-Path $miniforgeDir 'Scripts\conda.exe'
$envPython = Join-Path $miniforgeDir 'envs\almos\python.exe'
$envPythonw = Join-Path $miniforgeDir 'envs\almos\pythonw.exe'
$easyalmosExe = Join-Path $miniforgeDir 'envs\almos\Scripts\easyalmos.exe'
$sharedEnvFile = Join-Path $StateDir 'almos.yaml'

$pidFile = Join-Path $StateDir 'pid.txt'
$phaseFile = Join-Path $StateDir 'phase.txt'
$successFile = Join-Path $StateDir 'success.flag'
$failureFile = Join-Path $StateDir 'failure.txt'
$script:lastProcessExitCode = -1
$script:phaseDurations = [ordered]@{}
$script:installStartedAt = Get-Date
$script:utf8Encoding = New-Object System.Text.UTF8Encoding($false)

function Format-Duration {
    param(
        [Parameter(Mandatory = $true)]
        [TimeSpan]$Duration
    )

    return ('{0:hh\:mm\:ss}' -f $Duration)
}

function Write-LogSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,

        [string]$FailureMessage = ''
    )

    $summaryFile = Join-Path $logsDir 'installer-summary.log'
    $completedAt = Get-Date
    $totalDuration = $completedAt - $script:installStartedAt
    $lines = New-Object System.Collections.Generic.List[string]

    $lines.Add("Status: $Status")
    $lines.Add("Started: $($script:installStartedAt.ToString('yyyy-MM-dd HH:mm:ss'))")
    $lines.Add("Completed: $($completedAt.ToString('yyyy-MM-dd HH:mm:ss'))")
    $lines.Add("Total duration: $(Format-Duration -Duration $totalDuration)")

    if ($FailureMessage) {
        $lines.Add("Failure: $FailureMessage")
    }

    if ($script:phaseDurations.Count -gt 0) {
        $lines.Add('')
        $lines.Add('Phase durations:')
        foreach ($entry in $script:phaseDurations.GetEnumerator()) {
            $lines.Add("- $($entry.Key): $(Format-Duration -Duration $entry.Value)")
        }
    }

    [System.IO.File]::WriteAllLines($summaryFile, $lines)
}

function Append-PhaseFooter {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogBaseName,

        [Parameter(Mandatory = $true)]
        [TimeSpan]$Duration,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    $stdoutLog = Join-Path $logsDir "$LogBaseName.log"
    $footer = @(
        '',
        '--- EasyALMOS timing summary ---',
        "Phase duration: $(Format-Duration -Duration $Duration)",
        "Exit code: $ExitCode"
    )

    Add-Content -LiteralPath $stdoutLog -Value $footer -Encoding UTF8
}

function Normalize-LogText {
    param(
        [AllowEmptyString()]
        [string]$Text
    )

    if ($null -eq $Text) {
        return ''
    }

    $normalized = $Text -replace '\x1b\[[0-9;?]*[ -/]*[@-~]', ''
    $normalized = $normalized -replace '\x08', ''
    $normalized = $normalized -replace "`r(?!`n)", "`r`n"
    return $normalized
}

function Remove-PrivateRuntime {
    if (Test-Path -LiteralPath $miniforgeDir) {
        Remove-Item -LiteralPath $miniforgeDir -Recurse -Force
    }
}

function Invoke-LoggedProcess {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [string]$LogBaseName
    )

    $stdoutLog = Join-Path $logsDir "$LogBaseName.log"
    $stderrLog = Join-Path $logsDir "$LogBaseName-error.log"
    $startedAt = Get-Date

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $Arguments
    $startInfo.WorkingDirectory = $installRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $startInfo.Environment['PYTHONUTF8'] = '1'
    $startInfo.Environment['PYTHONIOENCODING'] = 'utf-8'
    $startInfo.Environment['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Could not start $FilePath."
    }

    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    # Refresh the native process state after asynchronous stream completion.
    $process.WaitForExit()
    $stdout = Normalize-LogText -Text $stdout
    $stderr = Normalize-LogText -Text $stderr
    [System.IO.File]::WriteAllText($stdoutLog, $stdout, $script:utf8Encoding)
    [System.IO.File]::WriteAllText($stderrLog, $stderr, $script:utf8Encoding)

    $script:lastProcessExitCode = [int]$process.ExitCode
    $duration = (Get-Date) - $startedAt
    $script:phaseDurations[$LogBaseName] = $duration
    Append-PhaseFooter -LogBaseName $LogBaseName -Duration $duration -ExitCode $script:lastProcessExitCode
    $process.Dispose()
}

function Copy-EnvironmentFile {
    Copy-Item -LiteralPath $EnvFile -Destination $sharedEnvFile -Force
}

try {
    $validationStartedAt = $null
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    Set-Content -LiteralPath $pidFile -Value $PID -Encoding ASCII

    Remove-PrivateRuntime
    if (Test-Path -LiteralPath $logsDir) {
        Remove-Item -LiteralPath $logsDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    Copy-EnvironmentFile

    Set-Content -LiteralPath $phaseFile -Value 'miniforge' -Encoding ASCII
    $miniforgeArgs = "/S /InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /D=$miniforgeDir"
    Invoke-LoggedProcess `
        -FilePath $MiniforgeInstaller `
        -Arguments $miniforgeArgs `
        -LogBaseName 'miniforge-install'
    $exitCode = $script:lastProcessExitCode
    if ($exitCode -ne 0) {
        throw "Miniforge installation failed with exit code $exitCode."
    }
    if (-not (Test-Path -LiteralPath $condaExe)) {
        throw 'Miniforge finished but conda.exe was not created.'
    }

    Set-Content -LiteralPath $phaseFile -Value 'environment' -Encoding ASCII
    $quotedEnvFile = "`"$sharedEnvFile`""
    $quotedEnvPrefix = "`"$($miniforgeDir)\envs\almos`""
    $condaArgs = "env create --prefix $quotedEnvPrefix --yes --file $quotedEnvFile"
    Invoke-LoggedProcess `
        -FilePath $condaExe `
        -Arguments $condaArgs `
        -LogBaseName 'conda-environment'
    $exitCode = $script:lastProcessExitCode
    if ($exitCode -ne 0) {
        throw "Conda environment creation failed with exit code $exitCode."
    }

    Set-Content -LiteralPath $phaseFile -Value 'validate' -Encoding ASCII
    $validationStartedAt = Get-Date
    if (-not (Test-Path -LiteralPath $envPython)) {
        throw 'Conda finished but python.exe is missing from the almos environment.'
    }
    if (-not (Test-Path -LiteralPath $envPythonw)) {
        throw 'Conda finished but pythonw.exe is missing from the almos environment.'
    }
    if (-not (Test-Path -LiteralPath $easyalmosExe)) {
        throw 'ALMOS did not create the expected easyalmos.exe entry point.'
    }

    $script:phaseDurations['validate'] = (Get-Date) - $validationStartedAt
    Write-LogSummary -Status 'success'
    Set-Content -LiteralPath $successFile -Value 'ok' -Encoding ASCII
    exit 0
}
catch {
    $message = $_.Exception.Message
    try {
        Write-LogSummary -Status 'failure' -FailureMessage $message
        Add-Content -LiteralPath (Join-Path $logsDir 'installer-error.log') `
            -Value $message -Encoding UTF8
    }
    catch {}

    try {
        Remove-PrivateRuntime
    }
    catch {
        $message += " Runtime cleanup failed: $($_.Exception.Message)"
    }

    [System.IO.File]::WriteAllText(
        $failureFile,
        $message,
        [System.Text.Encoding]::ASCII
    )
    exit 1
}
