# VICTORY LAP 🏆

**Every call. Every meeting. VICTORY LAP CORPORATE REMIX.**

One command replaces *every* Microsoft Teams call and meeting sound —
incoming ringtone, outgoing ring, meeting join/leave, reminders, all 24 of
them — with VICTORY LAP CORPORATE REMIX. Fully reversible. Teams is the
first supported platform; more call apps are coming.

## Install (macOS)

```sh
git clone https://github.com/JeffGuo-06/victory-lap.git
cd victory-lap
./install.sh
```

That's it. The installer:

1. auto-detects your call apps (currently: new Microsoft Teams),
2. asks once for confirmation (and installs `ffmpeg` via Homebrew if needed),
3. warms Teams' sound cache if necessary (it walks you through it and waits),
4. quits Teams for you, patches every sound, and reopens it.

Undo everything just as easily:

```sh
./install.sh --undo
```

### Have an AI agent?

Tell it:

> Clone https://github.com/JeffGuo-06/victory-lap and run `./install.sh --yes`

`--yes` answers every prompt, including quitting/reopening Teams.

## Install (Windows)

New Teams for Windows scans a `Sounds` folder for custom ringtones, so no
patching is needed for the incoming ringtone:

```powershell
git clone https://github.com/JeffGuo-06/victory-lap.git
cd victory-lap
.\windows\teams-ringtone.ps1 add "ringtone\VICTORY LAP CORPORATE REMIX.wav"
```

Then restart Teams and pick it under **Settings → Calls → Ringtones**.
(A full patch-all port for Windows — meeting sounds included — is on the
roadmap; the cache design is identical to macOS.)

## How it works (macOS)

New Teams is a native shell around an Edge WebView; the app itself is a web
app that fetches its sounds from Microsoft's CDN
(`https://teams.public.onecdn.static.microsoft/evergreen-assets/audio/*.mp3`)
with `cache-control: max-age=31536000, immutable` — meaning Teams plays
whatever bytes sit in its browser cache and never re-checks them.

`scripts/patch_cache.py` rewrites those cached entries in place:

- parses Chromium's *simple cache* sparse-entry format (header, key, sparse
  ranges each guarded by a CRC32)
- re-encodes the track to mp3 sized for each sound — 24s/96kbps for the big
  ringtones, stepping down to short mono clips for the ~25 KB meeting
  blips — padded inside an ID3v2 tag so every replacement is
  **byte-for-byte the same size** as the original (cached HTTP headers and
  the cache index stay valid)
- recomputes each range's CRC32 so Chromium accepts the data
- backs up every original to `~/.teams-ringtone/cache-backups/`

No app patching, no broken signatures, no proxies, no admin rights. Worst
case, Teams evicts an entry and re-downloads the stock sound — the hack can
never break Teams.

**Why not the documented "Sounds folder" on macOS?** Several guides claim
Teams for Mac scans a Sounds folder for custom WAVs. We tested this
empirically on Teams 26225 (correct 16-bit/44.1kHz WAVs, both candidate
folder locations, clean restarts): **the Mac client never scans it.** That
mechanism is Windows-only.

## Power-user CLI

The `teams-ringtone` CLI underneath the installer lets you use your own
track or target individual sounds:

```sh
teams-ringtone replace ~/Music/mytrack.mp3        # replace default incoming ring
teams-ringtone replace mytrack.mp3 bop            # replace a specific preset
teams-ringtone cached                             # list sounds + patch state
teams-ringtone restore-original [sound]           # back to stock
teams-ringtone doctor                             # check your setup
python3 scripts/patch_cache.py patch-all my.mp3   # everything, custom track
```

Symlink it onto your PATH:
`ln -s "$PWD/teams-ringtone" /opt/homebrew/bin/teams-ringtone`
(`/usr/local/bin` on Intel Macs).

## Caveats

- A Teams update or cache eviction can restore stock sounds. Nothing breaks —
  re-run `./install.sh`.
- Patching requires Teams to be fully quit; the installer handles that.
- Teams rings ~20s before voicemail, so the ringtones use the track's first
  ~24 seconds. Meeting blips use proportionally shorter clips.

## Roadmap

- Windows `install.ps1` with the same auto-detect/patch-all flow
- More platforms: Zoom, Slack huddles, Google Meet (PRs welcome — the
  pattern to follow: find where the app caches its sounds, replace bytes,
  keep sizes/checksums valid)
- `--offset/--duration` to pick the section of the track

## Tests

```sh
./test/test.sh                      # CLI + audio pipeline
python3 test/test_patch_cache.py    # cache parser/patcher round-trip
```

CI runs shellcheck and both suites on every push.

## License

[MIT](LICENSE)
