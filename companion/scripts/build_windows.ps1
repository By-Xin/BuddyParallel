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

function Assert-PythonModules {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Modules
    )

    $checkScript = @'
import importlib.util
import sys

missing = [name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]
if missing:
    print('Missing Python modules required for BuddyParallel packaging: ' + ', '.join(missing))
    print('Run: powershell -ExecutionPolicy Bypass -File companion\\scripts\\prepare_build_env.ps1')
    raise SystemExit(1)
'@

    & $Executable -c $checkScript @Modules
    if ($LASTEXITCODE -ne 0) {
        throw "Build Python is missing required packaging modules. Use companion\scripts\prepare_build_env.ps1, then rerun this build."
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

Assert-PythonModules $PythonExe @(
    "PyInstaller",
    "PIL",
    "bleak",
    "esptool",
    "lark_oapi",
    "pystray",
    "serial"
)

$baseArgs = @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distDir, "--workpath", $buildDir, $specPath)

Invoke-CheckedExternal $PythonExe @baseArgs

$appDir = Join-Path $distDir "BuddyParallel"
$setupShortcut = Join-Path $appDir "Setup Board.cmd"
Set-Content -LiteralPath $setupShortcut -Encoding ASCII -Value @(
    "@echo off",
    "cd /d ""%~dp0""",
    """%~dp0BuddyParallel.exe"" setup"
)

$advancedDir = Join-Path $appDir "Advanced"
New-Item -ItemType Directory -Force -Path $advancedDir | Out-Null

Set-Content -LiteralPath (Join-Path $advancedDir "README.txt") -Encoding ASCII -Value @(
    "BuddyParallel advanced config helpers",
    "",
    "Public releases do not include your personal config.",
    "BuddyParallel reads config from %APPDATA%\BuddyParallel\config.json on each Windows account.",
    "",
    "Export Current Config.cmd",
    "  Copies this Windows account's current config to shared-config.json next to these scripts.",
    "  That file can contain API keys, tokens, chat IDs, and personal names.",
    "  Share it only with people you trust.",
    "",
    "Import Shared Config.cmd",
    "  Copies shared-config.json next to these scripts into %APPDATA%\BuddyParallel\config.json.",
    "  This overwrites the local BuddyParallel config on that Windows account."
)

Set-Content -LiteralPath (Join-Path $advancedDir "Export Current Config.cmd") -Encoding ASCII -Value @(
    "@echo off",
    "setlocal",
    "set ""SOURCE=%APPDATA%\BuddyParallel\config.json""",
    "set ""DEST=%~dp0shared-config.json""",
    "if not exist ""%SOURCE%"" (",
    "  echo No BuddyParallel config found at:",
    "  echo   %SOURCE%",
    "  echo Open BuddyParallel once and save settings before exporting.",
    "  pause",
    "  exit /b 1",
    ")",
    "echo WARNING: this export may include API keys, tokens, chat IDs, and personal names.",
    "echo It is meant only for trusted private beta sharing.",
    "set /p CONFIRM=Type EXPORT to write shared-config.json: ",
    "if /I not ""%CONFIRM%""==""EXPORT"" (",
    "  echo Export canceled.",
    "  pause",
    "  exit /b 1",
    ")",
    "copy /Y ""%SOURCE%"" ""%DEST%"" >nul",
    "echo Exported:",
    "echo   %DEST%",
    "pause"
)

Set-Content -LiteralPath (Join-Path $advancedDir "Import Shared Config.cmd") -Encoding ASCII -Value @(
    "@echo off",
    "setlocal",
    "set ""SOURCE=%~dp0shared-config.json""",
    "set ""TARGET_DIR=%APPDATA%\BuddyParallel""",
    "set ""TARGET=%TARGET_DIR%\config.json""",
    "if not exist ""%SOURCE%"" (",
    "  echo shared-config.json was not found next to this script.",
    "  echo Put the private beta shared config here:",
    "  echo   %SOURCE%",
    "  pause",
    "  exit /b 1",
    ")",
    "echo This will overwrite this Windows account's BuddyParallel config:",
    "echo   %TARGET%",
    "set /p CONFIRM=Type IMPORT to continue: ",
    "if /I not ""%CONFIRM%""==""IMPORT"" (",
    "  echo Import canceled.",
    "  pause",
    "  exit /b 1",
    ")",
    "mkdir ""%TARGET_DIR%"" 2>nul",
    "copy /Y ""%SOURCE%"" ""%TARGET%"" >nul",
    "echo Imported shared BuddyParallel config.",
    "echo Starting BuddyParallel...",
    "start """" ""%~dp0..\BuddyParallel.exe""",
    "pause"
)
