#!/usr/bin/env bash

set -Eeuo pipefail

docker run --rm --tty --name stt-transcription-server-tests \
       --volume ~/.stt-mcp-server-linux/whisper:/.whisper \
       --volume $(pwd)/pytest.ini:/app/pytest.ini \
       --volume $(pwd)/stt_client.py:/app/stt_client.py \
       --volume $(pwd)/tests:/app/tests \
       stt-transcription-server bash -ci "python -m pytest --verbose"
