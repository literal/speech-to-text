#!/usr/bin/env bash

set -Eeuo pipefail

MODEL=${MODEL:-small.en}

mkdir -p ~/.speech-to-text/whisper && chmod 0700 ~/.speech-to-text/whisper
docker run --rm --tty --name speech-to-text-download \
       --env MODEL="$MODEL" \
       --volume ~/.speech-to-text/whisper:/.whisper \
       --volume $(pwd)/scripts:/app/scripts \
       stt-transcription-server bash -ci "python scripts/download_whisper_model.py"
