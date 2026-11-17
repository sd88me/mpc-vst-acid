# Acid 3.0.x handoff (2026-11-17)

State: master == rev-sdk merge `531d901`. Latest release `acid-vst-v3.0.1` (published). Tested on the Live III (MPC OS 3.10.1)
and, for 3.0.0, the Force (3.9.1); 3.0.1 NOT yet run on the Force. tested.json has the entries.

## Layout
- `src/acid_core.c` engine (C), `src/sdk/AcidPlugin.cpp` SDK front end (ALSA seq port "Acid"), `tools/` packaging, `tests/run.sh` offline ASan test.
- `vst/` is the older VST2 build, no longer the release path.

## Build / test / release (all manual)
- Test: `MPC_SDK=$HOME/mpc-plugin-builder-sdk bash tests/run.sh` (must print OK). Default SDK path `~/mpc-310-private/...` is absent.
- Package: `MPC_SDK=... tools/package.sh` then `tools/package_catalog.sh` -> `dist/Acid-<v>-{mpc,VST2-Plugins}-{armv7,aarch64}.zip`.
- Release: bump `plugin.json` + README version, add `docs/RELEASE-NOTES-<v>.md`, `gh release create acid-vst-v<v> --draft --target <branch>` with the 4 zips, try on device, publish, add `tested.json` entry, push master.
- CI (`.github/workflows/vst-release.yml`) now points at open-mpc/mpc-vst-plugins (sdk_project) but FAILS: its SDK build compiles only .cpp via zig; Acid has a C core + ALSA. Needs support in mpc-vst-plugins `tools/build.py`. 3.0.0 also had an `-mpc-sdk.zip`; 3.0.1 does not.
- Live III: 192.168.2.217 (root ssh), plugins in `/nvme/VST2 Plugins/`; restart with detached `systemctl restart acvs`. Force: 192.168.1.187.

## 3.0.1 changes
- Regen counted `k % interval` on the song step, which wraps with the MPC loop: a loop as short as the interval never regenerated. Now counts steps in both modes (verified on the Live III).
- Held-note flush (only notes sent on) on stop / locate (>1 beat jump) / close, instead of 2048 note-offs.
- Muted Acid also swallows CCs (slide); port drained only when something was queued.

## OPEN: arp interaction (not fixed, believed MPC-side)
Report: with Link/transport running and Acid's port enabled as a track input ("Track" in MIDI settings), a track with the MPC ARP on stops/hangs or "Acid takes over". Findings: transport stopped = fine; arp off = fine; port Track input off = fine; other tracks' input off, only the 303 listening = still broken; different channels, mute (even with CCs swallowed) no help; Maze Seq does the same. Not tried: notes in a different range than Acid's, Link off, aseqdump capture of the Acid port while it breaks (`aseqdump -p Acid`), a dedicated MIDI track. Next step: report to Akai with this matrix; if a capture shows stray CC120/123 or note-off bursts, look there. Draft reply to the reporter was written but not sent.
