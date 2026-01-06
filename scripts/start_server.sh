#!/usr/bin/env bash

set -Eeuo pipefail

CONTAINER_NAME=${CONTAINER_NAME:-stt-transcription-server}
PORT=${PORT:-5000}
MODEL=${MODEL:-small.en}

# Clean up any existing container
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting transcription server on port $PORT with model $MODEL..."

# Use exec so docker run becomes PID 1 and receives signals directly
exec docker run --rm \
    --name "$CONTAINER_NAME" \
    --publish "$PORT:5000" \
    --volume ~/.stt-mcp-server-linux/whisper:/.whisper \
    stt-transcription-server \
    /home/nonroot/venv/bin/python /app/transcription_server.py --model "$MODEL"
