#!/usr/bin/env bash

set -Eeuo pipefail

# Setup systemd services for STT server and client

if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

echo "Setting up STT services for user: $ACTUAL_USER"
echo "Project directory: $PROJECT_DIR"

# --- ydotoold service ---
echo ""
echo "Creating ydotoold service..."
cat > /etc/systemd/system/ydotoold.service << 'EOF'
[Unit]
Description=ydotool daemon
Documentation=man:ydotool(1)

[Service]
ExecStart=/usr/bin/ydotoold --socket-perm=0660
ExecStartPost=/usr/bin/sleep 0.1
ExecStartPost=/usr/bin/chgrp input /tmp/.ydotool_socket
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# --- STT Server service ---
echo "Creating stt-server service..."
cat > /etc/systemd/system/stt-server.service << EOF
[Unit]
Description=Speech-to-Text Transcription Server
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=$ACTUAL_USER
Environment=MODEL=small
ExecStart=$PROJECT_DIR/scripts/start_server.sh
ExecStop=/usr/bin/docker stop stt-transcription-server
Restart=on-failure
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

# --- STT Client service ---
echo "Creating stt-client service..."
cat > /etc/systemd/system/stt-client.service << EOF
[Unit]
Description=Speech-to-Text Client
After=stt-server.service ydotoold.service
Requires=ydotoold.service
Wants=stt-server.service

[Service]
Type=simple
User=$ACTUAL_USER
Environment=KEYBOARD_LAYOUT=de
Environment=LANGUAGE=auto
ExecStartPre=/usr/bin/sleep 2
ExecStart=$PROJECT_DIR/scripts/start_client.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "Reloading systemd daemon..."
systemctl daemon-reload

echo ""
echo "Enabling services..."
systemctl enable ydotoold.service
systemctl enable stt-server.service
systemctl enable stt-client.service

echo ""
echo "Starting services..."
systemctl start ydotoold.service
systemctl start stt-server.service
systemctl start stt-client.service

echo ""
echo "Services status:"
echo "--- ydotoold ---"
systemctl status ydotoold.service --no-pager || true
echo ""
echo "--- stt-server ---"
systemctl status stt-server.service --no-pager || true
echo ""
echo "--- stt-client ---"
systemctl status stt-client.service --no-pager || true

echo ""
echo "Done! Services installed and started."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status stt-server stt-client ydotoold"
echo "  sudo journalctl -u stt-server -f"
echo "  sudo journalctl -u stt-client -f"
