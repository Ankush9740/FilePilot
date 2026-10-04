[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Installer,
    [string]$IsccPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Build FilePilot on Windows x64.' }
$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $Python) { $Python = Join-Path $repoRoot '.venv-build\Scripts\python.exe' }
$Python = (Get-Command $Python -ErrorAction Stop).Source
$workDir = Join-Path $repoRoot 'build\filepilot-packaging'
$distributionDir = Join-Path $repoRoot 'dist\FilePilot'
$installerDir = Join-Path $repoRoot 'dist\installer'
$ownerName = '.filepilot-packaging-owned'
$ownerText = 'FilePilot packaging v1'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Executable" }
}

function Assert-SafeGeneratedPath {
    param([string]$Path)
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute -notin @($workDir, $distributionDir, $installerDir)) {
        throw "Refusing to clean a path outside FilePilot's generated output: $absolute"
    }
    # Reject junctions/symlinks in ancestors and children before any recursive delete.
    $ancestor = $absolute
    while ($ancestor.StartsWith($repoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing a reparse point in generated output: $ancestor"
            }
        }
        if ($ancestor -eq $repoRoot) { break }
        $ancestor = Split-Path -Parent $ancestor
    }
    if (Test-Path -LiteralPath $absolute) {
        $marker = Join-Path $absolute $ownerName
        if (-not (Test-Path -LiteralPath $marker) -or
            (Get-Content -LiteralPath $marker -Raw).Trim() -ne $ownerText) {
            throw "Output exists without the packaging ownership marker; preserve or move it first: $absolute"
        }
        $links = @(Get-ChildItem -LiteralPath $absolute -Recurse -Force |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
        if ($links.Count) { throw "Refusing to clean output containing reparse points: $absolute" }
    }
}

function Reset-GeneratedDirectory {
    param([string]$Path)
    Assert-SafeGeneratedPath $Path
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Path $ownerName) -Value $ownerText -Encoding ASCII
}

function Find-InnoCompiler {
    if ($IsccPath) { return (Get-Command $IsccPath -ErrorAction Stop).Source }
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
    )
    $registryRoots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($entry in @(Get-ItemProperty $registryRoots -ErrorAction SilentlyContinue)) {
        if ($entry.PSObject.Properties['DisplayName'] -and $entry.DisplayName -like 'Inno Setup*' -and
            $entry.PSObject.Properties['InstallLocation'] -and $entry.InstallLocation) {
            $candidates += Join-Path $entry.InstallLocation 'ISCC.exe'
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

# Fail before cleaning if the interpreter/dependencies do not match the release pins.
$validation = @'
import importlib.metadata as metadata
from pathlib import Path
import platform, sys
assert sys.version_info >= (3, 12), 'Python 3.12+ required'
assert platform.machine().upper() == 'AMD64', 'An x64 Python interpreter is required'
for line in Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith('#'):
        name, expected = line.split('==')
        actual = metadata.version(name)
        assert actual == expected, f'{name}: expected {expected}, got {actual}'
print(f'Build interpreter: {sys.version.split()[0]} x64')
'@
Invoke-Checked $Python @('-c', $validation, (Join-Path $PSScriptRoot 'requirements-windows.txt'))
Invoke-Checked $Python @((Join-Path $PSScriptRoot 'generate_icon.py'))

# Validate all destinations before modifying any output. Never delete build/ or dist/ wholesale.
Assert-SafeGeneratedPath $workDir
Assert-SafeGeneratedPath $distributionDir
if ($Installer) { Assert-SafeGeneratedPath $installerDir }
# Resolve PATH-installed compilers before restricting DLL search for PyInstaller.
$compiler = $null
if ($Installer) { $compiler = Find-InnoCompiler }
Reset-GeneratedDirectory $workDir
Reset-GeneratedDirectory $distributionDir
$previousCache = $env:PYINSTALLER_CONFIG_DIR
$previousPath = $env:PATH
try {
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $workDir 'cache'
    # Keep unrelated tools' DLLs out of binary dependency resolution. Qt hooks
    # add their own wheel directories; all invoked tools have explicit paths.
    $env:PATH = (Split-Path -Parent $Python) + ';' + [Environment]::SystemDirectory
    Invoke-Checked $Python @('-m', 'PyInstaller', '--noconfirm', '--clean',
        '--workpath', $workDir, '--distpath', (Join-Path $repoRoot 'dist'),
        (Join-Path $PSScriptRoot 'FilePilot.spec'))
    # COLLECT replaces its directory, so restore the ownership marker after success.
    Set-Content -LiteralPath (Join-Path $distributionDir $ownerName) -Value $ownerText -Encoding ASCII
    $exePath = Join-Path $distributionDir 'FilePilot.exe'
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "Missing executable: $exePath" }
    Invoke-Checked $Python @((Join-Path $PSScriptRoot 'verify_package.py'), '--exe', $exePath)
    Write-Host "Application: $exePath"
    if ($Installer) {
        if (-not $compiler) {
            throw 'Application built. Install the official Inno Setup compiler (reference: 6.7.3) from https://jrsoftware.org/isdl.php, then rerun with -Installer. No system software was installed.'
        }
        Reset-GeneratedDirectory $installerDir
        Invoke-Checked $compiler @("/DDistributionDir=$distributionDir", "/DInstallerOutputDir=$installerDir",
            (Join-Path $PSScriptRoot 'FilePilot.iss'))
        $setupPath = Join-Path $installerDir 'FilePilot-Setup-1.0.0.exe'
        if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) { throw "Missing installer: $setupPath" }
        Write-Host "Installer: $setupPath"
    } else {
        Write-Host 'Installer configuration is ready. Add -Installer when Inno Setup is available.'
    }
} finally {
    $env:PYINSTALLER_CONFIG_DIR = $previousCache
    $env:PATH = $previousPath
}
