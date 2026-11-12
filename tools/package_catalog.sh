#!/usr/bin/env bash
# The catalog-shaped release zips, from the release build (build/sdk/"sd88me - VST - Acid", made by ./build-sdk.sh or tools/package.sh):
#   dist/Acid-<ver>-mpc-armv7.zip, -mpc-aarch64.zip   per CPU, made by mpc-vst-plugins' tools/release.py (manifest, install.sh /
#                                                     uninstall.sh that Plugin Manager and the desktop installer run)
# The folder keeps its name ("sd88me - VST - Acid") and its id, so the installer replaces an older Acid (1.x / 2.x) in place.
# The .so sits at the folder root as acid.so.
# MPC_VST: an mpc-vst-plugins checkout with tools/release.py.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins-postlaunch}"
[ -f "$MPC_VST/tools/release.py" ] || { echo "need mpc-vst-plugins with tools/release.py (MPC_VST)" >&2; exit 1; }
DIR="sd88me - VST - Acid"; SRC="$here/build/sdk/$DIR"
[ -f "$SRC/VST/acid-arm32.so" ] || { echo "missing $SRC: run ./build-sdk.sh first" >&2; exit 1; }
VER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SRC/plugin.json")
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["uid"]=="AcId" and "Beta" not in m["name"] else "not the release identity")' "$SRC/plugin.json"
out="$here/dist"; mkdir -p "$out"
for pair in armv7:arm32:file32 aarch64:arm64:file64; do
  IFS=: read -r cpu so key <<<"$pair"
  st="$here/build/catalog/$cpu"; rm -rf "${st:?}"; mkdir -p "$st/$DIR"
  cp -r "$SRC/Plugin Skins" "$SRC/version.xml" "$st/$DIR/"
  python3 - "$SRC/plugin.json" "$st/$DIR/plugin.json" "$key" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("file32", None); m.pop("file64", None)
m[sys.argv[3]] = "acid.so"
json.dump(m, open(sys.argv[2], "w"), indent=2)
PY
  cp "$SRC/VST/acid-$so.so" "$st/acid.so"
  printf '<PLUGIN name="Acid" descriptiveName="Acid" format="VST" category="Synth" manufacturer="sd88me" version="%s" file="acid.so" uid="41634964" isInstrument="1" fileTime="0" infoUpdateTime="0" numInputs="0" numOutputs="2" isShell="0"/>\n' "$VER" > "$st/entry.xml"
  python3 "$MPC_VST/tools/release.py" --so "$st/acid.so" --skin "$st/$DIR" --entry "$st/entry.xml" --version "$VER" \
    --repo sd88me/mpc-vst-acid --license GPL-3.0-only --id acid \
    --about "TB-303-style acid bassline sequencer: two blendable lines with generate/mutate, driving a synth track over MIDI, with a touchscreen skin and Q-Links." \
    -o "$st/dist"
  z=$(ls "$st/dist"/*.zip); cp "$z" "$out/Acid-$VER-mpc-$cpu.zip"
done
ls -la "$out"/Acid-"$VER"-mpc-*.zip
