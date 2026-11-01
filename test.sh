#!/bin/bash
# Runs all tests: Python receiver unit tests, then CaptureKit (incl. Swift -> receiver E2E).
set -euo pipefail
cd "$(dirname "$0")"

(cd server && python3 -m unittest -v test_stash_server test_note_title)

# Command Line Tools ship swift-testing but don't wire its macro plugin; load it explicitly.
PLUGIN=/Library/Developer/CommandLineTools/usr/lib/swift/host/plugins/testing/libTestingMacros.dylib
EXTRA=()
[ -f "$PLUGIN" ] && ! xcode-select -p | grep -q Xcode.app && EXTRA=(-Xswiftc -load-plugin-library -Xswiftc "$PLUGIN")
(cd ios/CaptureKit && swift test ${EXTRA[@]+"${EXTRA[@]}"})
