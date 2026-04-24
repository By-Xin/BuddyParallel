param(
    [switch]$Clean
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

Write-Host "Building BuddyParallel from $specPath"

$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$baseArgs = @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distDir, "--workpath", $buildDir, $specPath)

& $python @baseArgs
