param(
    [switch]$Recreate,
    [string]$BasePython = ""
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
$venvDir = Join-Path $companionRoot ".venv-build"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not $BasePython) {
    if ($env:BUDDYPARALLEL_BASE_PYTHON) {
        $BasePython = $env:BUDDYPARALLEL_BASE_PYTHON
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $BasePython = (Get-Command python).Source
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $BasePython = "py"
    } else {
        throw "Could not find a base Python launcher. Pass -BasePython explicitly."
    }
}

if ($Recreate -and (Test-Path $venvDir)) {
    Remove-Item -Recurse -Force $venvDir
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating build environment at $venvDir"
    Invoke-CheckedExternal $BasePython -m venv $venvDir
}

Write-Host "Using build environment: $venvPython"

Invoke-CheckedExternal $venvPython -m pip install --upgrade pip setuptools wheel

Push-Location $companionRoot
try {
    Invoke-CheckedExternal $venvPython -m pip install --editable ".[build,tray,serial,ble]"
}
finally {
    Pop-Location
}

Write-Host "BuddyParallel build environment is ready."
