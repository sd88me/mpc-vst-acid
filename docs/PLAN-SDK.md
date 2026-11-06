# Acid 3.0: the SDK port (branch `rev-sdk`)

Method: `~/mpc-vst-plugins-postlaunch/docs/SDK-PORTING.md` (as used for Welle 0.2 and Dexed 2.0). Plugin first, art second.

## Decisions

- **Engine untouched:** `src/acid_core.c` (the vendored generator) is driven through its string API from `src/sdk/AcidPlugin.cpp` (an `mpc::Plugin`).
  Nothing of the old wrapper (`vst/acid_vst.cpp`, hand-written VST2 ABI, `popup.h`) is used any more.
- **MIDI out:** the SDK doc says the MPC discards a plugin's VST MIDI output. Acid does not use it: the notes leave through an **ALSA sequencer
  port** ("Acid", "Acid 2" ...) exactly as in 2.x, so `libasound` is linked dynamically (the SDK validator flags it; both the Live III and the
  Force have `libasound.so.2`, and 2.x shipped that way). Because of ALSA the SDK's zig build is not used: `build-sdk.sh` compiles both
  targets with gcc in Docker (`scripts/Dockerfile`: arm32 = Force / Live / One / X / Key, glibc 2.31; arm64 = Live III).
- **Parameters:** 217 engine params, frozen order (`vst/params.json` + `vst/params.lock`, taken from the released 2.1.0 table), plus ONE UI-only
  `ui_open` (index 217) that replaces the ten wrapper `<key>__open` pop-up flags. Flags (tools/gen_sdk_params.py): momentary (GENERATE, MUTATE),
  float (density, accent, slide, gate, jitter: shown as %), choice, pushed (edit cells, BLEND, running lights, Chain readout), read-only, edit cell.
- **Parameter 0 is GENERATE** and the host nudges parameter 0 to 1 and back on every prepare: a press counts only after ~40 ms high.
- **Pushed params:** the core changes the edit cells (after GENERATE / MUTATE / density moves / the bar switch) and BLEND (Chain snap) behind
  the host's back. A worker thread (10 ms) reads them back round-robin (24 per pass) and calls `notifyHostParameterChanged`. The running lights
  are read every pass.
- **State:** the framework saves every parameter by id; seeds + hand-locked steps travel as extra state. Edit cells are ignored while a state
  loads (setting them would lock the steps they show). A 2.x text chunk (`key=value;`) is still read: `effSetChunk` is wrapped in `VSTPluginMain`.
- **Version:** 3.0.0 (new platform, new state format, 2.x projects still load). Name `Acid`, uid `AcId` unchanged.

## Phases

1. **Plugin + tests (done, 2026-11-06):** `tests/run.sh` (ASan/UBSan, the real core, step grid / loops / tempo lurches / density / accent / slide / MOD /
   chunk + legacy chunk) passes; the SDK `host_sim` passes. `./build-sdk.sh beta` builds "Acid 2 Beta" (uid AcIB) for arm32 + arm64 with the SDK's
   generated default skin. *Not run on a device yet.*
2. **Device check with the default skin:** the ALSA port appears and a synth track plays; param 0 nudge does not re-roll the pattern; edit cells
   follow GENERATE; save / reload a project; a 2.x project loads. Live III first (`/nvme/VST2 Plugins/`), then the Force (3.9.1: `/sdcard/Synths/`
   + `pluginList-arm`).
3. **Native skin** (`tools/make_tui.py`, from `vst/layout.conf` and the 2.1 module-look art): six tabs SEQ A, EDIT A, SEQ B, EDIT B, MOD, GLOBAL,
   Q-Links 1-8 / 1-16 as in the README; drawn pick-lists via `ui_open` for SCALE, ROOT, REGEN, the LFO division and destinations.
4. **Release 3.0.0:** README (install for both device families), `tools/package.sh`, tag.

## Open

- Does the Force 3.9.1 host accept the SDK build? (Dexed 2.0 did.)
- The SDK skin has no "ink on the NOTE slider" strips yet: reuse `vst/images/note_strip.png` (52x270, 29 frames).
