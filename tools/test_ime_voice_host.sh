#!/usr/bin/env bash
# Run the real Kotlin draft and ownership logic against deterministic Android test doubles.
set -euo pipefail
tool_dir="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$tool_dir/.." && pwd)"
src="$root/app/android/app/src/main/kotlin/org/example/phonecontroller"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
compiler="${KOTLINC:-kotlinc}"
bash_compiler=("$compiler")
if [[ -f "$compiler" && ! -x "$compiler" ]]; then bash_compiler=(bash "$compiler"); fi
"${bash_compiler[@]}" -nowarn "$src/ImeVoiceDraft.kt" "$src/RelayInputOwner.kt" "$tool_dir"/ime_voice_host/*.kt -include-runtime -d "$out/ime-voice-tests.jar"
"${JAVA_HOME:+$JAVA_HOME/bin/}java" -jar "$out/ime-voice-tests.jar"
