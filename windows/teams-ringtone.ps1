# teams-ringtone — use your own track as a Microsoft Teams ringtone (Windows)
#
# Installs a WAV file into the new Teams "Sounds" folder, where it shows up in
# Settings > Calls > Ringtones. Non-WAV input is converted with ffmpeg if
# available on PATH.
#
# Usage:
#   .\teams-ringtone.ps1 add <audio-file> [name]
#   .\teams-ringtone.ps1 list
#   .\teams-ringtone.ps1 remove <name>
#   .\teams-ringtone.ps1 open
#
# https://github.com/JeffGuo-06/victory-lap

param(
    [Parameter(Position = 0)] [string]$Command = "help",
    [Parameter(Position = 1)] [string]$File,
    [Parameter(Position = 2)] [string]$Name
)

$ErrorActionPreference = "Stop"

$SoundsDir = if ($env:TEAMS_RINGTONE_SOUNDS_DIR) { $env:TEAMS_RINGTONE_SOUNDS_DIR } else {
    Join-Path $env:LOCALAPPDATA "Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Sounds"
}

function Require-Teams {
    $pkg = Join-Path $env:LOCALAPPDATA "Packages\MSTeams_8wekyb3d8bbwe"
    if (-not $env:TEAMS_RINGTONE_SOUNDS_DIR -and -not (Test-Path $pkg)) {
        throw "New Microsoft Teams data folder not found ($pkg). Install the new Teams and launch it once first."
    }
    New-Item -ItemType Directory -Force -Path $SoundsDir | Out-Null
}

switch ($Command) {
    "add" {
        if (-not $File) { throw "usage: teams-ringtone.ps1 add <audio-file> [name]" }
        if (-not (Test-Path $File)) { throw "file not found: $File" }
        Require-Teams

        if (-not $Name) { $Name = [IO.Path]::GetFileNameWithoutExtension($File) }
        $Name = ($Name -replace '[^\w \.-]', '_').Trim()
        $dest = Join-Path $SoundsDir "$Name.wav"

        if ([IO.Path]::GetExtension($File).ToLower() -eq ".wav") {
            Copy-Item $File $dest -Force
        }
        elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
            # Teams reliably detects 16-bit / 44.1 kHz PCM WAV.
            & ffmpeg -y -loglevel error -i $File -ar 44100 -sample_fmt s16 -ac 2 $dest
            if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed to convert '$File'" }
        }
        else {
            throw "Teams needs a WAV file. Either pass a .wav, or install ffmpeg (winget install ffmpeg) so this script can convert for you."
        }

        Write-Host "Installed -> $dest"
        Write-Host ""
        Write-Host "Next: fully quit Teams (system tray > right-click > Quit), reopen it,"
        Write-Host "then pick '$Name' under Settings > Calls > Ringtones."
    }
    "list" {
        Require-Teams
        $sounds = Get-ChildItem -Path $SoundsDir -Filter *.wav -ErrorAction SilentlyContinue
        if ($sounds) { $sounds | ForEach-Object { $_.BaseName } } else { Write-Host "(none)" }
    }
    "remove" {
        if (-not $File) { throw "usage: teams-ringtone.ps1 remove <name>" }
        Require-Teams
        $target = Join-Path $SoundsDir "$File.wav"
        if (-not (Test-Path $target)) { throw "no sound named '$File'" }
        Remove-Item $target
        Write-Host "Removed '$File'. Restart Teams for the change to take effect."
    }
    "open" {
        Require-Teams
        Invoke-Item $SoundsDir
    }
    default {
        Get-Content $PSCommandPath | Select-Object -Skip 1 -First 12 | ForEach-Object { $_ -replace '^# ?', '' }
    }
}
