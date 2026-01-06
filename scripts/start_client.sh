#!/usr/bin/env bash

set -Eeuo pipefail

API_URL=${API_URL:-http://localhost:5000}
KEY=${KEY:-KEY_RIGHTMETA}
LANGUAGE=${LANGUAGE:-auto}
PAD_SECONDS=${PAD_SECONDS:-30}
KEYBOARD_LAYOUT=${KEYBOARD_LAYOUT:-us}
DEBUG=${DEBUG:-}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_PATH="$SCRIPT_DIR/../stt_client.py"

echo "Starting speech-to-text client..."
echo "  API URL: $API_URL"
echo "  Activation key: $KEY"
echo "  Language: $LANGUAGE"
echo "  Keyboard layout: $KEYBOARD_LAYOUT"

CMD="python3 $CLIENT_PATH --api-url $API_URL --key $KEY --language $LANGUAGE --pad-seconds $PAD_SECONDS --layout $KEYBOARD_LAYOUT"

if [ -n "$DEBUG" ]; then
    CMD="$CMD --debug"
fi

exec $CMD
