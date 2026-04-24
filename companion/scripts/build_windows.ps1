param(
    [switch]$Clean,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$companionRoot = Join-Path $repoRoot "companion"
$specPath = Join-Path $companionRoot "packaging\buddy_parallel.spec"
$distDir = Join-Path $repoRoot "dist"
$buildDir = Join-Path $repoRoot "build\pyinstaller"

if ($Clean) {
    Remove-Item -Recurse -Force $distDir -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue
}

if (-not $PythonExe) {
    if ($env:BUDDYPARALLEL_PYTHON) {
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

$baseArgs = @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distDir, "--workpath", $buildDir, $specPath)

& $PythonExe @baseArgs
