param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

function ConvertTo-XmlText {
    param([string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}

$extensionRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $extensionRoot "..")).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "dist"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$packagePath = Join-Path $extensionRoot "package.json"
$package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
$name = [string]$package.name
$publisher = [string]$package.publisher
$version = [string]$package.version
$displayName = [string]$package.displayName
$description = [string]$package.description
$engine = [string]$package.engines.vscode

if (-not $name -or -not $publisher -or -not $version) {
    throw "VS Code extension package.json must include name, publisher, and version."
}

$vsixName = "BuddyParallel-vscode-$version.vsix"
$vsixPath = Join-Path $OutputDir $vsixName
$zipPath = Join-Path $OutputDir "BuddyParallel-vscode-$version.zip"
$staging = Join-Path $OutputDir ".vsix-staging-$version"
if (Test-Path $staging) {
    Remove-Item -Recurse -Force $staging
}
if (Test-Path $vsixPath) {
    Remove-Item -Force $vsixPath
}
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
New-Item -ItemType Directory -Force -Path (Join-Path $staging "extension") | Out-Null

$extensionFiles = @(
    "package.json",
    "README.md",
    "extension.js",
    "codex-monitor.js",
    "workspace-monitor.js"
)
foreach ($relativePath in $extensionFiles) {
    $source = Join-Path $extensionRoot $relativePath
    if (-not (Test-Path $source)) {
        throw "Required extension file is missing: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $staging "extension\$relativePath")
}

$contentTypes = @'
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="js" ContentType="application/javascript"/>
  <Default Extension="md" ContentType="text/markdown"/>
  <Default Extension="vsixmanifest" ContentType="text/xml"/>
  <Default Extension="xml" ContentType="text/xml"/>
</Types>
'@
Set-Content -LiteralPath (Join-Path $staging "[Content_Types].xml") -Value $contentTypes -Encoding UTF8

$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="$(ConvertTo-XmlText "$publisher.$name")" Version="$(ConvertTo-XmlText $version)" Publisher="$(ConvertTo-XmlText $publisher)"/>
    <DisplayName>$(ConvertTo-XmlText $displayName)</DisplayName>
    <Description xml:space="preserve">$(ConvertTo-XmlText $description)</Description>
    <Categories>Other</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="$(ConvertTo-XmlText $engine)"/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Code.Readme" Path="extension/README.md" Addressable="true"/>
  </Assets>
</PackageManifest>
"@
Set-Content -LiteralPath (Join-Path $staging "extension.vsixmanifest") -Value $manifest -Encoding UTF8

Push-Location $staging
try {
    Compress-Archive -Path ".\*" -DestinationPath $zipPath -CompressionLevel Optimal
    Move-Item -LiteralPath $zipPath -Destination $vsixPath
}
finally {
    Pop-Location
    Remove-Item -Recurse -Force $staging
}

Write-Host "VSIX ready: $vsixPath"
