# Installs a Lekhak shortcut into the current user's Start Menu (and
# optionally the Desktop). No admin rights needed.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 -Desktop
#   powershell ... -Uninstall
#
# The shortcut runs the checkout's .venv interpreter with `-m lekhak`
# (pythonw.exe, so no console window appears), falling back to a `lekhak`
# command already on PATH.

param(
    [switch]$Desktop,
    [switch]$Uninstall
)

$repo = Split-Path -Parent $PSScriptRoot
$icon = Join-Path $repo "packaging\lekhak.ico"

function Find-Launcher {
    $pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
    if (Test-Path $pythonw) {
        return @{ Target = $pythonw; Arguments = "-m lekhak" }
    }
    $console = Get-Command lekhak -ErrorAction SilentlyContinue
    if ($console) {
        return @{ Target = $console.Source; Arguments = "" }
    }
    Write-Error ("No Lekhak launcher found. Install it first:`n" +
        "  py -3 -m venv `"$repo\.venv`"`n" +
        "  `"$repo\.venv\Scripts\pip`" install -e `"$repo`"")
    exit 1
}

function New-LekhakShortcut([string]$path, $launcher) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $launcher.Target
    $shortcut.Arguments = $launcher.Arguments
    $shortcut.WorkingDirectory = $repo
    $shortcut.IconLocation = $icon
    $shortcut.Description = "Plan and write long-form documents"
    $shortcut.Save()
    Write-Host "installed $path"
}

$programs = [Environment]::GetFolderPath("Programs")  # Start Menu
$shortcuts = @(
    (Join-Path $programs "Lekhak.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Lekhak.lnk")
)
if (-not $Desktop) { $shortcuts = @($shortcuts[0]) }

if ($Uninstall) {
    $found = $false
    foreach ($path in @(
        (Join-Path $programs "Lekhak.lnk"),
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "Lekhak.lnk")
    )) {
        if (Test-Path $path) {
            Remove-Item $path
            Write-Host "removed $path"
            $found = $true
        }
    }
    if (-not $found) { Write-Host "nothing to remove" }
    exit 0
}

if (-not (Test-Path $icon)) {
    Write-Warning "packaging\lekhak.ico missing - shortcut will use a generic icon"
}
$launcher = Find-Launcher
foreach ($path in $shortcuts) { New-LekhakShortcut $path $launcher }
