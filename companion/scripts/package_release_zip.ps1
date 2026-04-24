param(
    [string]$Version = "",
    [string]$Platform = "windows-x64",
    [switch]$SkipVsix
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$distDir = Join-Path $repoRoot "dist"
$appDir = Join-Path $distDir "BuddyParallel"
$exePath = Join-Path $appDir "BuddyParallel.exe"
$setupShortcut = Join-Path $appDir "Setup Board.cmd"

if (-not (Test-Path $exePath)) {
    throw "Packaged app not found: $exePath. Run companion\scripts\build_windows.ps1 first."
}
if (-not (Test-Path $setupShortcut)) {
    throw "Setup shortcut not found: $setupShortcut. Run companion\scripts\build_windows.ps1 first."
}

$requiredFirmware = @("bootloader.bin", "partitions.bin", "boot_app0.bin", "firmware.bin")
$primaryFirmwareDir = Join-Path $appDir "_internal\firmware\m5stickc-plus"
if (-not (Test-Path $primaryFirmwareDir)) {
    $primaryFirmwareDir = Join-Path $appDir "firmware\m5stickc-plus"
}
foreach ($name in $requiredFirmware) {
    $match = Get-ChildItem -Path $primaryFirmwareDir -Filter $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $match) {
        throw "Packaged M5StickC Plus firmware artifact not found in ${primaryFirmwareDir}: $name"
    }
}

$coreS3FirmwareDir = Join-Path $appDir "_internal\firmware\m5stack-cores3"
if (-not (Test-Path $coreS3FirmwareDir)) {
    $coreS3FirmwareDir = Join-Path $appDir "firmware\m5stack-cores3"
}
$coreS3FirmwareBin = Join-Path $coreS3FirmwareDir "firmware.bin"
if (Test-Path $coreS3FirmwareBin) {
    foreach ($name in $requiredFirmware) {
        $match = Get-ChildItem -Path $coreS3FirmwareDir -Filter $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $match) {
            throw "Packaged CoreS3 firmware artifact not found in ${coreS3FirmwareDir}: $name"
        }
    }
} else {
    Write-Warning "CoreS3 firmware.bin is not present in this package yet. Build env:m5stack-cores3 before cutting a CoreS3-enabled release: $coreS3FirmwareDir"
}

$forbiddenConfigNames = @(
    "config.json",
    "state.json",
    "runtime.json",
    "buddy-parallel.log",
    "shared-config.json"
)
$forbiddenConfigs = @(
    Get-ChildItem -Path $appDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $forbiddenConfigNames -contains $_.Name }
)
if ($forbiddenConfigs.Count -gt 0) {
    $paths = ($forbiddenConfigs | ForEach-Object { $_.FullName }) -join ", "
    throw "Refusing to package local or shared runtime config files: $paths"
}

$vsixPath = ""
if (-not $SkipVsix) {
    $vsixScript = Join-Path $repoRoot "vscode-extension\scripts\package_vsix.ps1"
    if (-not (Test-Path $vsixScript)) {
        throw "VS Code extension packaging script not found: $vsixScript"
    }
    & powershell -ExecutionPolicy Bypass -File $vsixScript -OutputDir $distDir
    if ($LASTEXITCODE -ne 0) {
        throw "VS Code extension VSIX packaging failed."
    }
    $vsix = Get-ChildItem -Path $distDir -Filter "BuddyParallel-vscode-*.vsix" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $vsix) {
        throw "VS Code extension VSIX was not created."
    }
    $vsixPath = $vsix.FullName
    $extensionDest = Join-Path $appDir "vscode-extension"
    New-Item -ItemType Directory -Force -Path $extensionDest | Out-Null
    Copy-Item -LiteralPath $vsixPath -Destination (Join-Path $extensionDest (Split-Path $vsixPath -Leaf)) -Force
}

if (-not $Version) {
    $initPath = Join-Path $repoRoot "companion\app\buddy_parallel\__init__.py"
    $initText = Get-Content -LiteralPath $initPath -Raw
    if ($initText -notmatch '__version__\s*=\s*"([^"]+)"') {
        throw "Could not read BuddyParallel version from $initPath."
    }
    $Version = $Matches[1]
}

$zipName = "BuddyParallel-v$Version-$Platform.zip"
$zipPath = Join-Path $distDir $zipName
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

Push-Location $distDir
try {
    Compress-Archive -Path "BuddyParallel" -DestinationPath $zipPath -CompressionLevel Optimal
}
finally {
    Pop-Location
}

Write-Host "Release zip ready: $zipPath"
