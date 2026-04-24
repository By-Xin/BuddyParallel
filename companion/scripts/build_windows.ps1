param(
    [switch]$Clean,
    [switch]$SkipFirmwareCheck,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedExternal {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$companionRoot = Join-Path $repoRoot "companion"
$specPath = Join-Path $companionRoot "packaging\buddy_parallel.spec"
$distDir = Join-Path $repoRoot "dist"
$buildDir = Join-Path $repoRoot "build\pyinstaller"
$venvPython = Join-Path $companionRoot ".venv-build\Scripts\python.exe"
$firmwareBuildDir = Join-Path $repoRoot "firmware\.pio\build\m5stickc-plus"
$firmwareFiles = @(
    (Join-Path $firmwareBuildDir "bootloader.bin"),
    (Join-Path $firmwareBuildDir "partitions.bin"),
    (Join-Path $firmwareBuildDir "firmware.bin"),
    (Join-Path $repoRoot "firmware\.platformio_local\packages\framework-arduinoespressif32\tools\partitions\boot_app0.bin")
)

if ($Clean) {
    Remove-Item -Recurse -Force $distDir -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue
}

if (-not $PythonExe) {
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    } elseif ($env:BUDDYPARALLEL_PYTHON) {
        $PythonExe = $env:BUDDYPARALLEL_PYTHON
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = (Get-Command python).Source
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = "py"
    } else {
        throw "Could not find a Python launcher. Pass -PythonExe explicitly."
    }
}

Write-Host "Building BuddyParallel from $specPath"
Write-Host "Using Python launcher: $PythonExe"

if (-not $SkipFirmwareCheck) {
    $missingFirmware = @($firmwareFiles | Where-Object { -not (Test-Path $_) })
    if ($missingFirmware.Count -gt 0) {
        throw "Firmware artifacts are missing. Build firmware first or pass -SkipFirmwareCheck for app-only builds: $($missingFirmware -join ', ')"
    }
}

$baseArgs = @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distDir, "--workpath", $buildDir, $specPath)

Invoke-CheckedExternal $PythonExe @baseArgs
