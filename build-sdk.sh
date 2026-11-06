#!/usr/bin/env bash
# Build Acid on the MPC Plugin SDK front end (src/sdk/AcidPlugin.cpp) into build/sdk/"sd88me - VST - Acid"/ : arm32 (Force, MPC Live /
# One / X, glibc 2.31) and arm64 (Live III). The plugin links ALSA (its notes leave through an ALSA sequencer port), so the SDK's zig
# build is not used: both targets are compiled with gcc in Docker (scripts/Dockerfile).
#   ./build-sdk.sh            gen params, build both targets, assemble the folder (plugin.json, version.xml, Plugin Skins)
#   ./build-sdk.sh beta       the same as "Acid 2 Beta" (uid AcIB): installs next to the release
#   ./build-sdk.sh test       the offline test (tests/run.sh) and the SDK's host simulator
# MPC_SDK: the plugin-vibecode-sdk checkout.
set -euo pipefail
cd "$(dirname "$0")"
SDK="${MPC_SDK:-$HOME/mpc-310-private/plugin-vibecode-sdk/plugin-vibecode-sdk}"
[ -f "$SDK/framework/mpc_plugin.h" ] || { echo "need the SDK (MPC_SDK)" >&2; exit 1; }
NAME="Acid"; UID_="'A','c','I','d'"; SLUG=acid
if [ "${1:-}" = beta ]; then NAME="Acid 2 Beta"; UID_="'A','c','I','B'"; SLUG=acid2beta; fi
python3 tools/gen_sdk_params.py
if [ "${1:-}" = test ]; then
  tests/run.sh
  docker image inspect acid-sdk-run >/dev/null 2>&1 || docker build -q -t acid-sdk-run -f scripts/Dockerfile.run scripts >/dev/null
  mkdir -p build/sdk-native
  docker image inspect acid-sdk-x64 >/dev/null 2>&1 || docker build -q -t acid-sdk-x64 --build-arg BASE=gcc:12 scripts >/dev/null
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/b -v "$SDK":/sdk:ro -w /b acid-sdk-x64 sh -c \
    'gcc -O1 -fPIC -c -std=gnu11 -Isrc src/acid_core.c -o build/sdk-native/core.o && g++ -std=c++17 -O1 -fPIC -shared -fvisibility=hidden -I/sdk/framework -Isrc -Isrc/sdk -o build/sdk-native/acid.so src/sdk/AcidPlugin.cpp build/sdk-native/core.o -lasound -lpthread -lm'
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/b -v "$SDK":/sdk:ro -w /b acid-sdk-run sh -c \
    '/sdk/.sdk-tools/host_sim build/sdk-native/acid.so dump > build/sdk-native/params.json; /sdk/.sdk-tools/host_sim build/sdk-native/acid.so test --playing --notes 60 | tail -n 12'
  exit
fi
FOLDER="build/sdk/sd88me - VST - $NAME"
rm -rf "$FOLDER"; mkdir -p "$FOLDER/VST" "$FOLDER/Plugin Skins"
build() {   # <docker platform> <image> <base image> <out>
  docker image inspect "$2" >/dev/null 2>&1 || docker build -q -t "$2" --platform "$1" --build-arg BASE="$3" scripts >/dev/null
  docker run --rm --platform "$1" -u "$(id -u):$(id -g)" -e ACID_N="$NAME" -e ACID_U="$UID_" -e OUT="$4" -e TAG="$2" \
    -v "$PWD":/b -v "$SDK":/sdk:ro -w /b "$2" scripts/compile.sh
}
mkdir -p build
build linux/arm/v7 acid-sdk-arm32 arm32v7/gcc:11-bullseye "$FOLDER/VST/$SLUG-arm32.so" &
build linux/arm64 acid-sdk-arm64 arm64v8/gcc:12-bookworm "$FOLDER/VST/$SLUG-arm64.so" &
wait
python3 - "$NAME" "$SLUG" "$FOLDER" "$UID_" <<'PY'
import json, sys
name, slug, folder, uid = sys.argv[1:]
m = json.load(open("plugin.json"))
m["name"] = name
if name != "Acid":
    m["uid"] = "AcIB"
m["file32"] = "VST/%s-arm32.so" % slug
m["file64"] = "VST/%s-arm64.so" % slug
json.dump(m, open(folder + "/plugin.json", "w"), indent=2)
open(folder + "/version.xml", "w").write('<?xml version="1.0" encoding="utf-8"?>\n<plugincontent version="1.0">\n    <version>%s</version>\n</plugincontent>\n' % m["version"])
PY
# Phase 1: the SDK's generated default skin (pages of 16 parameters). Phase 2 replaces it with skins/ from tools/make_tui.py.
if [ -d skins ]; then cp -r skins/. "$FOLDER/Plugin Skins/"
else
  [ -f build/sdk-native/params.json ] || "$0" test >/dev/null || true
  python3 "$SDK/tools/gen_ui.py" --params build/sdk-native/params.json --out "$FOLDER/Plugin Skins" >/dev/null
  sed -i 's#</plugincontent>#    <uiversion>0.1.0.0</uiversion>\n</plugincontent>#' "$FOLDER/version.xml"
fi
python3 "$SDK/tools/validate.py" "$FOLDER" || true
echo "built: $FOLDER"
