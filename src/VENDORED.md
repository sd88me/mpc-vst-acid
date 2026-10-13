# Vendored: acid_core.c / acid_core.h

Source: `sd88me/force-acid`, `src/acid_core.c` + `src/acid_core.h`
Vendored at commit: `e40708729fb9020a6469d46aaf0ee8153d72be73` (2026-09-26)
License: GPLv3 (same author, same license as this repo — see `LICENSE`).

This is the shared DSP/sequencer engine also used by the Force Shadow addon
(force-acid repo, `addon/`). It is vendored here rather than built against a
submodule so this VST port stays self-contained. Since 2.0.0 this copy has diverged from that commit (live knobs, edit-page cells and locks, the MOD LFOs, the
song-locked step, the density fix); treat it as the source of truth here. To take engine changes from
force-acid, diff by hand rather than copying the files over.
