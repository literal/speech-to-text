#!/usr/bin/env bash

set -Eeuo pipefail

bash scripts/build_docker_image.sh

docker run --rm --tty --name stt-transcription-server-mypy \
       --volume $(pwd)/transcription_server.py:/app/transcription_server.py \
       --volume $(pwd)/stt_client.py:/app/stt_client.py \
       --volume $(pwd)/tests:/app/tests \
       stt-transcription-server bash -ci "python -m mypy ."
