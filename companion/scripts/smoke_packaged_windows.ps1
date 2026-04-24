param(
    [string]$ExePath = "",
    [string]$AppDir = "",
    [int]$HookPort = 49186,
    [int]$ApiPort = 49187,
    [int]$StartupDelaySeconds = 6,
    [switch]$SkipWindows
)

$ErrorActionPreference = "Stop"

function Stop-StartedProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }
    try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            $Process.Kill()
        }
    } catch {
        Write-Warning "Could not stop process $($Process.Id): $_"
    }
}

function Start-BuddyParallel {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$RuntimeAppDir
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["BUDDY_PARALLEL_APP_DIR"] = $RuntimeAppDir
    return [System.Diagnostics.Process]::Start($psi)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $ExePath) {
    $ExePath = Join-Path $repoRoot "dist\BuddyParallel\BuddyParallel.exe"
}
$ExePath = (Resolve-Path $ExePath).Path
$exeDir = Split-Path $ExePath

if (-not $AppDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $AppDir = Join-Path $repoRoot ".tmp-smoke\packaged-$stamp"
}
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

$config = @{
    transport_mode = "mock"
    notice_transport = "telegram"
    bot_token = ""
    allowed_chat_id = ""
    hook_server_port = $HookPort
    api_server_port = $ApiPort
    weather_enabled = $false
    device_name = "BuddyParallelSmoke"
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $AppDir "config.json") -Value $config -Encoding UTF8

Write-Host "Smoke app dir: $AppDir"
Write-Host "Smoke executable: $ExePath"

$first = $null
$second = $null
$settings = $null
$dashboard = $null
try {
    $first = Start-BuddyParallel -Exe $ExePath -Arguments "headless" -WorkingDirectory $exeDir -RuntimeAppDir $AppDir
    Start-Sleep -Seconds $StartupDelaySeconds
    $first.Refresh()
    if ($first.HasExited) {
        throw "First headless process exited early."
    }

    $second = Start-BuddyParallel -Exe $ExePath -Arguments "headless" -WorkingDirectory $exeDir -RuntimeAppDir $AppDir
    Start-Sleep -Seconds $StartupDelaySeconds
    $second.Refresh()
    if (-not $second.HasExited) {
        throw "Second headless process stayed alive; single-instance guard failed."
    }

    $logPath = Join-Path $AppDir "buddy-parallel.log"
    if (-not (Test-Path $logPath)) {
        throw "Expected log file was not created: $logPath"
    }
    $logText = Get-Content -LiteralPath $logPath -Raw
    if ($logText -notmatch "BuddyParallel is already running") {
        throw "Single-instance warning was not written to the log."
    }

    if (-not $SkipWindows) {
        $settings = Start-BuddyParallel -Exe $ExePath -Arguments "settings" -WorkingDirectory $exeDir -RuntimeAppDir $AppDir
        Start-Sleep -Seconds 3
        $settings.Refresh()
        if ($settings.HasExited) {
            throw "Settings window process exited early."
        }

        $dashboard = Start-BuddyParallel -Exe $ExePath -Arguments "dashboard" -WorkingDirectory $exeDir -RuntimeAppDir $AppDir
        Start-Sleep -Seconds 3
        $dashboard.Refresh()
        if ($dashboard.HasExited) {
            throw "Dashboard window process exited early."
        }
    }

    Write-Host "Packaged smoke test passed."
} finally {
    Stop-StartedProcess $dashboard
    Stop-StartedProcess $settings
    Stop-StartedProcess $second
    Stop-StartedProcess $first
}
