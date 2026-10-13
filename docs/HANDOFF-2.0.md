# 2.0 work: live knobs, edit pages, running light, MOD tab

Branch: `acid-2.0` (off master at fe1fd5a, i.e. after PR #15 clock-lookahead).
**Nothing here has been run on the Force.** The 1.0.7 look-ahead timing fix from PR #15 is also still waiting for its
listen check, so test and release that first; keep this branch out of that release.

Checked offline only: `vst/test.sh` (ASan/UBSan host test) passes, `vst/build.sh` builds (armhf, glibc 2.17),
skin built and previewed with `tools/studio.py preview` in the `mpc-vst-html-art` image. Build with
`MPC_VST=/home/sam/mpc-vst-plugins ./vst/build.sh` (the script's default `../../mpc-vst` doesn't exist here).

## What changed

1. **Knobs are live (src/acid_core.c).** The generators draw the same random numbers for every step whether or not it ends
   up a rest, so a seed gives each step fixed "rolls" and DENSITY / ACCENT / SLIDE / OCTAVES / ALGO / LENGTH / SCALE only
   move thresholds. A knob move calls `rederive_pattern()` (same seed, live rng untouched). Only Generate / Regen pick a
   new seed. Returning a knob to a value restores the exact pattern.
2. **Accent and slide are independent** (`STEP_ACCSLIDE = 4`, `STEP_IS_ACCENT/SLIDE` macros). Generators, Mutate and
   hand edits can all make both. Playback treats it as an accent that slides.
3. **Per-step locks.** `acid_seq_t.locked[]`: a locked step keeps note/kind through `rederive_pattern()`. Editing or
   mutating a step locks it. Generate, `seed`, Regen clear locks. Saved as `a_locks` / `b_locks`
   (`idx.kind.deg.oct,` per locked step) after the seed in the chunk (chunk buffer 2 KB -> 8 KB).
4. **Edit pages** (tabs SEQ A EDIT / SEQ B EDIT, `vst/layout.conf`). 16 steps shown, `a_edit_bar` switches 1-16 / 17-32.
   Per step: `e<n>_gate` (ON/rest; a rest keeps its note), `e<n>_note` (signed scale steps from the root, -7..+21, slider;
   -1 octave below root up to OCTAVES above; `octaves[]` is now `int8_t`), `e<n>_acc`, `e<n>_sld`, `e<n>_lock`.
   Edit-cell params are derived state: pushed to the host from `processReplacing` (every 4th block, 24 per pass,
   `is_edit_param()` / `is_pushed_param()` in `vst/acid_vst.cpp`) and left out of the saved chunk.
   NOTE sliders use a custom 29-frame filmstrip, `vst/images/note_strip.png` (52x270 frames, fill from the root line),
   drawn by `vst/make_note_strip.py` (see "Regenerating the strip").
5. **Chain blend snaps.** In Chain mode `blend` snaps to 17 positions (A only, 8:1 ... 1:1 ... 1:8, B only) via
   `chain_pos()` / `chain_snap()`; `chain_counts()` plays from the same table. A display-only `chain_view` param feeds a
   readout on GLOBAL (`when=blend_mode:chain`), right of the BLEND knob. `blend` is pushed back to the host after a snap.
6. **GLOBAL page:** MUTE and CV MODE moved into the top band above the panel.
7. README documents the above.

## Known compatibility change

A given seed now yields a different pattern than 1.0.x, so projects saved with 1.0.x will sound different.
No legacy path was written; add one if that matters for the release.

## Check on the Force first

- **NOTE slider value text** under each slider: does MPC print the signed number (e.g. `-3`, `+5`)? Only a blank box in the
  offline preview.
- **Root line:** with the value at 0, is the thumb on the baked root line? (Frame 7 of 29.)
- **Touch:** lane toggles use `ns=0` so their touch box is the switch only; confirm taps on the tight ACC / SLIDE / LOCK
  lanes (50 px pitch) don't hit the neighbour. The skin check reports no lane overlaps. The slider box and the lock lane
  end about 4 px above the panel bottom.
- **Header strip:** the frame's divider line runs through the BAR switch and GENERATE / MUTATE row on the edit tabs.
- **Edit-cell refresh:** after Generate, Mutate, a density move or the BAR switch, do all cells update on screen? The
  pushes are rate-limited (24 changes per 4 blocks).
- **Chain snap:** the knob jumping to the snapped positions while dragging, and the readout text (`A 3 : B 1`). The SEQ
  tabs' BLEND knob snaps too but has no readout there.
- **Q-Links on the edit tabs** only reach BAR / GENERATE / MUTATE (the skin warns about Q-Links on parameters with no
  control on the page, so density etc. were left off). Decide whether that's acceptable.
- **Listen check:** accent+slide together on a step; slide into a rest; length > 16 with the bar switch; save and reload a
  project with locked steps.

## Not done / ideas

- Play-head marker on the edit page.
- Per-step note names (the cells are scale-step numbers, not C/D/E).
- Accent/slide memory on a rest: a step switched off and on again comes back as a plain note.
- Mutate locks the steps it changes, so a heavily mutated pattern stops following the knobs; may want a "clear locks" button.
- Version bump (module.json / vst.json `version`), `tested.json` entry after trying it on the Force, and a release.

## Regenerating the strip

`vst/images/note_strip.png`: 29 frames stacked down, each 52x270, value -7 at the top frame, zero at frame 7 (root line),
bar from the root line to the thumb. If the slider range or size changes, change `frames=` and `w=` / `h=` in the
`slider_v` lines of `vst/layout.conf` to match and redraw it with `vst/make_note_strip.py` (the run command is in its header).
