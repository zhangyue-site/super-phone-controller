#!/usr/bin/env bash
set -euo pipefail
tools_dir="$(cd "$(dirname "$0")" && pwd)"
src="$tools_dir/../app/android/app/src/main/kotlin/org/example/phonecontroller"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
compiler="${KOTLINC:-kotlinc}"
run=("$compiler")
if [[ -f "$compiler" && ! -x "$compiler" ]]; then run=(bash "$compiler"); fi
"${run[@]}" "$src/OfficialUpdatePolicy.kt" "$tools_dir/update-host/OfficialUpdatePolicyTest.kt" -include-runtime -d "$out/update-tests.jar"
"${JAVA_HOME:+$JAVA_HOME/bin/}java" -jar "$out/update-tests.jar"
