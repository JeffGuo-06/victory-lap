# teams-ringtone

Use **your own track** as the incoming-call ringtone in Microsoft Teams.

Teams (the new client) only lets you pick from its built-in ringtones — there's
no upload button. But it *does* scan a `Sounds` folder inside its data
directory and adds any WAV file it finds there to the ringtone dropdown.
`teams-ringtone` automates that: it converts any audio file to the exact WAV
format Teams detects, installs it in the right place, and keeps a backup
library so you can re-apply your sounds after a Teams update.

No app patching, no broken code signatures, no admin rights.

## macOS

### Install

```sh
git clone https://github.com/JeffGuo-06/teams-ringtone.git
cd teams-ringtone
chmod +x teams-ringtone
# optional: put it on your PATH (use /usr/local/bin on Intel Macs)
ln -s "$PWD/teams-ringtone" /opt/homebrew/bin/teams-ringtone
```

No dependencies — audio conversion uses `afconvert`, which ships with macOS.

### Use

```sh
teams-ringtone add ~/Music/my-banger.mp3
```

Then:

1. **Quit Teams completely** (Cmd+Q, or right-click the dock icon → Quit).
2. Reopen Teams.
3. Go to **Settings → Calls → Ringtones** and pick your track for incoming
   calls (you can set it for regular, secondary, and delegated calls).

That's it — incoming Teams calls now play your track.

Other commands:

```sh
teams-ringtone add track.mp3 "Cool Name"   # install under a custom name
teams-ringtone list                        # show installed custom sounds
teams-ringtone remove "Cool Name"          # uninstall a sound
teams-ringtone reapply                     # restore your sounds after a Teams update
teams-ringtone open                        # open the Teams Sounds folder in Finder
teams-ringtone doctor                      # sanity-check your setup
```

Accepts anything CoreAudio can decode: mp3, m4a, aac, wav, aiff, caf, …

Leading/trailing silence is trimmed automatically (DAW bounces are usually
padded with dead space at both ends) — pass `--no-trim` to keep the file
exactly as exported.

## The ringtone

This repo ships a ready-to-use track: [`ringtone/VICTORY LAP CORPORATE REMIX.wav`](ringtone)
(already converted to the 16-bit/44.1 kHz WAV Teams detects). Install it with:

```sh
teams-ringtone add "ringtone/VICTORY LAP CORPORATE REMIX.wav"
```

## Exporting from a DAW (Logic Pro, Ableton, …)

- Bounce/export in any format — WAV, AIFF, MP3, M4A all work; the tool
  normalizes everything to what Teams needs.
- **Keep it to ~10–20 seconds.** Teams rings for about 20 seconds by default
  before the call goes to voicemail (adjustable 10–60s in Teams call
  settings), so only the start of a longer track is ever heard. The tool
  warns if your file is longer than 30s.
- **No need to loop it.** Teams automatically loops files shorter than the
  ring duration, exactly like its built-in ringtones.
- Don't worry about silence padding from your cycle range or song-end
  marker — `add` trims it.

## Windows

The same `Sounds` folder mechanism exists in new Teams for Windows at
`%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Sounds`.

Use the PowerShell script:

```powershell
.\windows\teams-ringtone.ps1 add C:\Music\my-banger.mp3
```

WAV files are copied directly; other formats are converted automatically if
[ffmpeg](https://ffmpeg.org) is on your PATH (`winget install ffmpeg`).

## How it works

New Teams stores its data in a sandboxed container. On macOS that's:

```
~/Library/Containers/com.microsoft.teams2/Data/Library/Application Support/Microsoft/Teams/Sounds
```

Any **16-bit, 44.1 kHz PCM WAV** file placed there appears in the ringtone
dropdown after a full Teams restart. Compressed formats (mp3/aac) are ignored
by Teams, which is why the tool converts everything to that spec first.

Converted tracks are also kept in `~/.teams-ringtone/` so that
`teams-ringtone reapply` can restore everything if a Teams update clears the
Sounds folder.

## Caveats

- **Teams updates** occasionally reset the Sounds folder. Run
  `teams-ringtone reapply`, restart Teams, and re-select your ringtone.
- You need the **new Teams** client (the one Microsoft has shipped since
  2023/2024). The classic Electron client is dead and its old `app.asar` hack
  no longer applies.
- Requires a full Teams quit + reopen before new sounds appear.
- Long tracks work, but each ring plays from the beginning — trim your track
  to the good part for best effect.
- The file-swap mechanics are covered by automated tests (`test/test.sh`).
  The Teams-side behavior (sound appearing in the dropdown) follows Teams'
  documented-by-the-community scanning behavior and may change in future
  Teams versions — if it breaks, please open an issue with your Teams version.

## Contributing

PRs welcome — especially Windows testing/polish, a Linux (Teams PWA) story,
and reports of Teams versions where the Sounds folder behavior changed.

Run the tests on macOS:

```sh
./test/test.sh
```

## License

[MIT](LICENSE)
