[![test](https://github.com/marcindulak/stt-mcp-server-linux/actions/workflows/test.yml/badge.svg)](https://github.com/marcindulak/stt-mcp-server-linux/actions/workflows/test.yml)

[![Mentioned in Awesome Claude Code](https://awesome.re/mentioned-badge.svg)](https://github.com/hesreallyhim/awesome-claude-code)

> Co-Authored-By: Claude

# Functionality overview

Local speech-to-text for Linux using Whisper.

The system uses a split architecture:
- **Container**: Runs Whisper transcription model, exposes HTTP API
- **Host**: Lightweight Python client handles keyboard, audio, and text injection via ydotool

Text injection works in any application (terminals, GUI apps, browsers) on both X11 and Wayland.

> [!WARNING]
> This project will create `~/.stt-mcp-server-linux` directory.

# Architecture

```
Host
  +-------------+    audio    +-------------+    text    +-------+
  | evdev +     | ----------> | Container   | ---------> | ydo   |
  | sounddevice |   HTTP POST | /transcribe |            | tool  |
  +-------------+             +-------------+            +-------+
```

**Benefits:**
- Container needs zero device access (secure, simple Docker setup)
- Host component is lightweight (~300 lines Python)
- Transcription API reusable for other purposes
- Can swap transcription backend without touching host code
- Container can run on different machine (remote transcription)
- ydotool works in all applications
- Works on both X11 and Wayland

# Usage

## Prerequisites

1. Install [Docker Engine](https://docs.docker.com/engine/install/) or [Docker Desktop](https://docs.docker.com/desktop/)

2. Install ydotool:

   ```bash
   # Arch/Manjaro
   sudo pacman -S ydotool

   # Debian/Ubuntu
   sudo apt install ydotool
   ```

3. Configure uinput access for ydotool:

   ```bash
   # Create udev rule
   echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-uinput.rules

   # Add user to input group
   sudo usermod -aG input $USER

   # Reload rules
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

   Log out and back in for group changes to take effect.

4. Install Python dependencies for the host client:

   ```bash
   pip install evdev sounddevice requests
   ```

## Setup

1. Clone this repository:

   ```bash
   git clone https://github.com/marcindulak/stt-mcp-server-linux
   cd stt-mcp-server-linux
   ```

2. Build the Docker image:

   ```bash
   bash scripts/build_docker_image.sh
   ```

3. Download the Whisper model:

   ```bash
   bash scripts/download_whisper_model.sh
   ```

## Running

Start the transcription server (in one terminal):

```bash
bash scripts/start_server.sh
```

Start the client (in another terminal):

```bash
bash scripts/start_client.sh
```

Press **Right Super** (Right Windows key) to start recording. Release to transcribe and inject text.

## Running as systemd services

To start STT automatically on boot:

```bash
sudo bash scripts/setup_services.sh
```

This creates and enables three services:
- `ydotoold` - keyboard/mouse input daemon
- `stt-server` - transcription server (Docker)
- `stt-client` - keyboard monitor and audio client

Manage with standard systemctl commands:

```bash
sudo systemctl status stt-server stt-client ydotoold
sudo systemctl restart stt-client
sudo journalctl -u stt-client -f
```

## Configuration

### Server options

```bash
PORT=5000 MODEL=small.en bash scripts/start_server.sh
```

### Client options

```bash
API_URL=http://localhost:5000 \
KEY=KEY_RIGHTMETA \
LANGUAGE=auto \
PAD_SECONDS=30 \
KEYBOARD_LAYOUT=us \
DEBUG=1 \
bash scripts/start_client.sh
```

Available activation keys: `KEY_RIGHTMETA` (Right Super), `KEY_RIGHTCTRL` (Right Ctrl), etc.

Available keyboard layouts: `us`, `de`. Set `KEYBOARD_LAYOUT` to match your system keyboard layout.

# Running tests

## Unit tests

```bash
bash scripts/test_unit.sh
```

## Type checking

```bash
bash scripts/test_mypy.sh
```

# Implementation overview

## Container: transcription_server.py

Flask HTTP API that:
- Loads Whisper model at startup
- Exposes `/transcribe` endpoint (POST raw PCM audio)
- Exposes `/health` endpoint for container health checks
- Returns JSON with transcribed text

## Host: stt_client.py

Lightweight Python client that:
- Monitors keyboard for activation key (evdev)
- Records audio while key is held (sounddevice)
- Sends audio to container API (requests)
- Injects text via ydotool (subprocess)
