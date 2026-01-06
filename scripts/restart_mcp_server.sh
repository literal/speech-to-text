#!/usr/bin/env bash

set -Eeuo pipefail

CONTAINER_NAME=${CONTAINER_NAME:-stt-mcp-server-linux}
DEBUG=${DEBUG:-human}
MODE=${MODE:-mcp}
OUTPUT=${OUTPUT:-tmux}
TMUX_SESSION=${TMUX_SESSION:-claude}
TMUX_TMPDIR=${TMUX_TMPDIR:-~/.stt-mcp-server-linux/tmux}

docker stop "$CONTAINER_NAME" || true
docker rm "$CONTAINER_NAME" || true

DOCKER_CMD="docker run --rm --interactive --name $CONTAINER_NAME"
# IPC namespace sharing is required for tmux socket communication
DOCKER_CMD="$DOCKER_CMD --ipc=host"
DOCKER_CMD="$DOCKER_CMD --device /dev/input"
if [ -d "/dev/snd" ]; then
    DOCKER_CMD="$DOCKER_CMD --device /dev/snd"
fi
# PulseAudio support
DOCKER_CMD="$DOCKER_CMD --volume /run/user/$(id -u)/pulse:/run/user/$(id -u)/pulse"
DOCKER_CMD="$DOCKER_CMD --env PULSE_SERVER=unix:/run/user/$(id -u)/pulse/native"
# The /dev/input group owner ID may differ outside/inside the container.
# For the keyboard detection to work inside of the container,
# the user inside of the container must be the member
# of the /dev/input group ID present outside of the container.
INPUT_GID=$(getent group input | cut -d: -f3)
DOCKER_CMD="$DOCKER_CMD --group-add $INPUT_GID"
# Same for audio group - needed for ALSA device access
AUDIO_GID=$(getent group audio | cut -d: -f3)
DOCKER_CMD="$DOCKER_CMD --group-add $AUDIO_GID"
DOCKER_CMD="$DOCKER_CMD --volume ~/.stt-mcp-server-linux/whisper:/.whisper"
# Mount the tmux socket file directly to bypass directory permission checks
DOCKER_CMD="$DOCKER_CMD --volume $TMUX_TMPDIR/tmux-$(id -u)/default:/.tmux-socket"
DOCKER_CMD="$DOCKER_CMD --volume $(pwd)/tests:/app/tests"
DOCKER_CMD="$DOCKER_CMD stt-mcp-server-linux"
DOCKER_CMD="$DOCKER_CMD /home/nonroot/venv/bin/python /app/stt_mcp_server_linux.py"
DOCKER_CMD="$DOCKER_CMD --debug $DEBUG"
DOCKER_CMD="$DOCKER_CMD --mode $MODE"
DOCKER_CMD="$DOCKER_CMD --output $OUTPUT"
DOCKER_CMD="$DOCKER_CMD --pad-up-to-seconds 30"
DOCKER_CMD="$DOCKER_CMD --session $TMUX_SESSION"
DOCKER_CMD="$DOCKER_CMD --tmux-socket /.tmux-socket"

eval $DOCKER_CMD
