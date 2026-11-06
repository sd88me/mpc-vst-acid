#!/usr/bin/env bash
# Runs INSIDE the build container (see build-sdk.sh): compile the core + the SDK front end into one shared object.
# env: ACID_N (plugin name), ACID_U (uid as 'A','c','I','d'), OUT, TAG, FLAGS (extra gcc flags)
set -euo pipefail
gcc -O2 -fPIC -fvisibility=hidden -std=gnu11 ${FLAGS:-} -Isrc -c src/acid_core.c -o "build/obj-$TAG.o"
g++ -std=c++17 -O2 -fPIC -shared -fvisibility=hidden -fvisibility-inlines-hidden -fno-gnu-unique -ffunction-sections -fdata-sections \
  -Wall -Wextra -Wno-unused-parameter ${FLAGS:-} -I/sdk/framework -Isrc -Isrc/sdk -DACID_NAME="\"$ACID_N\"" -DACID_UID="$ACID_U" \
  -o "$OUT" src/sdk/AcidPlugin.cpp "build/obj-$TAG.o" \
  -Wl,--gc-sections -Wl,--version-script=/sdk/tools/exports.map -Wl,--exclude-libs,ALL -static-libstdc++ -static-libgcc -lasound -lpthread -lm
strip "$OUT"
echo "-- $(basename "$OUT"): highest glibc needed (arm32 must stay <= 2.32):"; readelf -V "$OUT" | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -n 1
