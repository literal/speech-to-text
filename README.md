# Speech-to-Text for Linux

> [!IMPORTANT]
> This project is for **Linux only** (X11 and Wayland).

> Based on [stt-mcp-server-linux](https://github.com/marcindulak/stt-mcp-server-linux) by [marcindulak](https://github.com/marcindulak), licensed under Apache 2.0.

## Functionality overview

Local speech-to-text for Linux using Whisper.

The system uses a split architecture:
- **Container**: Runs Whisper transcription model, exposes HTTP API
- **Host**: Lightweight Python client handles keyboard, audio, and text injection via ydotool

Text injection works in any application (terminals, GUI apps, browsers) on both X11 and Wayland.

> [!WARNING]
> This project will create `~/.speech-to-text` directory.

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
   git clone https://github.com/literal/speech-to-text
   cd speech-to-text
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

Install and start the systemd services:

```bash
sudo bash scripts/setup_services.sh
```

This creates and enables three services:
- `ydotoold` - keyboard/mouse input daemon (system service)
- `stt-server` - transcription server in Docker (system service)
- `stt-client` - keyboard monitor and audio client (user service)

> [!NOTE]
> The `stt-client` runs as a user service to access PipeWire audio.

Manage system services:

```bash
sudo systemctl status stt-server ydotoold
sudo systemctl restart stt-server
sudo journalctl -u stt-server -f
```

Manage stt-client (user service):

```bash
systemctl --user status stt-client
systemctl --user restart stt-client
journalctl --user -u stt-client -f
```

### Usage

Press and hold **Right Super** (Right Windows key) to record. Release to transcribe and inject text at the cursor. The activation key can be changed in the [configuration](#client-options).

## Configuration

Configuration options are set in `scripts/setup_services.sh`. Edit this file before running the setup, or modify the service files afterwards.

### Server options

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `small.en` | Whisper model to use |
| `PORT` | `5000` | HTTP port for the transcription API |

Service file: `/etc/systemd/system/stt-server.service`

### Client options

| Variable | Default | Description |
|----------|---------|-------------|
| `KEYBOARD_LAYOUT` | `de` | Keyboard layout (`us`, `de`) |
| `LANGUAGE` | `auto` | Transcription language or `auto` |
| `KEY` | `KEY_RIGHTMETA` | Activation key |
| `PAD_SECONDS` | `30` | Silence padding in seconds |

Service file: `~/.config/systemd/user/stt-client.service`

After modifying service files, reload and restart:

```bash
# For stt-server
sudo systemctl daemon-reload
sudo systemctl restart stt-server

# For stt-client
systemctl --user daemon-reload
systemctl --user restart stt-client
```

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
- Exposes `/info` endpoint (returns model name and load status)
- Returns JSON with transcribed text

## Host: stt_client.py

Lightweight Python client that:
- Monitors keyboard for activation key (evdev)
- Records audio while key is held (sounddevice)
- Sends audio to container API (requests)
- Injects text via ydotool (subprocess)
