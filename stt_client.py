#!/usr/bin/env python3
"""Host-side speech-to-text client.

This lightweight script runs on the host and handles:
- Keyboard monitoring for activation key (evdev)
- Audio recording (sounddevice)
- Sending audio to container transcription API
- Injecting text via ydotool

Dependencies:
    System: ydotool
    Python: evdev, sounddevice, requests
"""

import argparse
import asyncio
import logging
import os
import queue
import subprocess
import sys
from typing import Any, Callable, List, Optional

import evdev
import requests
import sounddevice

KeyEventCallback = Callable[[], None]

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Manages audio recording and buffering."""

    def __init__(self) -> None:
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.recording_active = False
        self.audio_stream: Optional[sounddevice.RawInputStream] = None

    def audio_callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        """Callback for audio stream data."""
        self.audio_queue.put(bytes(indata))

    def start_recording(self) -> None:
        """Start audio recording."""
        if self.recording_active:
            logger.debug("Recording already active, ignoring start request")
            return

        logger.info("Starting audio recording")
        try:
            self.audio_stream = sounddevice.RawInputStream(
                samplerate=16000, blocksize=2048, dtype='int16', channels=1,
                callback=self.audio_callback
            )
            self.audio_stream.start()
            self.recording_active = True
            logger.info("Audio recording started successfully")
        except (OSError, sounddevice.PortAudioError) as e:
            logger.exception(f"Failed to start audio recording: {e}")
            self._cleanup_failed_stream()
            self.recording_active = False
            raise

    def stop_recording(self) -> bytes:
        """Stop audio recording and return collected audio data."""
        if not self.recording_active:
            logger.debug("Recording not active, nothing to stop")
            return b""

        if not self.audio_stream:
            logger.exception("Audio stream is None but recording is active")
            self.recording_active = False
            return b""

        try:
            logger.info("Stopping audio recording")
            self.recording_active = False
            self.audio_stream.stop()
            self.audio_stream.close()

            audio_bytes = b""
            while not self.audio_queue.empty():
                try:
                    audio_bytes += self.audio_queue.get_nowait()
                except queue.Empty:
                    break

            logger.info(f"Audio recording stopped, collected {len(audio_bytes)} bytes")
            return audio_bytes

        except Exception as e:
            logger.exception(f"Error stopping audio recording: {e}")
            self.recording_active = False
            return b""

    def _cleanup_failed_stream(self) -> None:
        """Clean up audio stream after initialization failure."""
        if self.audio_stream:
            try:
                self.audio_stream.close()
            except Exception as e:
                logger.exception(f"Failed to close audio stream: {e}")
            finally:
                self.audio_stream = None

    def cleanup(self) -> None:
        """Clean up audio resources."""
        try:
            if self.audio_stream:
                if self.recording_active:
                    self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
            self.recording_active = False
            logger.info("Audio resources cleaned up successfully")
        except Exception as e:
            logger.exception(f"Error during audio cleanup: {e}")


class KeyboardMonitor:
    """Monitors keyboard devices for activation key events."""

    def __init__(self, keyboard_name: Optional[str] = None, key_code: str = 'KEY_RIGHTMETA') -> None:
        self.keyboard_name = keyboard_name
        self.key_code = key_code

    async def find_keyboards(self) -> List[evdev.InputDevice]:
        """Find keyboard input devices matching the configured name."""
        logger.info("Scanning for keyboard devices")
        keyboards = []
        available_keyboards = []

        for dev_path in evdev.list_devices():
            try:
                device = evdev.InputDevice(dev_path)
                if "keyboard" in device.name.lower():
                    available_keyboards.append(device.name)
                    if self.keyboard_name is None or self.keyboard_name.lower() == device.name.lower():
                        logger.info(f"Found matching keyboard: {device.name} ({dev_path})")
                        keyboards.append(device)
            except Exception as e:
                logger.debug(f"Could not access device {dev_path}: {e}")

        if not keyboards and self.keyboard_name:
            available_list = ", ".join(available_keyboards) if available_keyboards else "none"
            raise RuntimeError(
                f"No keyboard named '{self.keyboard_name}' found. "
                f"Available keyboards: {available_list}."
            )

        if not keyboards:
            raise RuntimeError(
                "No keyboard input devices found. "
                "Ensure you have appropriate permissions to access /dev/input devices."
            )

        logger.info(f"Found {len(keyboards)} matching keyboard devices")
        return keyboards

    async def monitor_device(self, dev_path: str, on_key_press: KeyEventCallback, on_key_release: KeyEventCallback) -> None:
        """Monitor a single keyboard device for activation key events."""
        dev = evdev.InputDevice(dev_path)
        logger.info(f"Waiting for {self.key_code} key press on {dev.name} ({dev_path})")

        try:
            async for event in dev.async_read_loop():
                if event.type == evdev.ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    if key_event.keycode == self.key_code:
                        if key_event.keystate == key_event.key_down:
                            logger.info(f"{self.key_code} pressed")
                            on_key_press()
                        elif key_event.keystate == key_event.key_up:
                            logger.info(f"{self.key_code} released")
                            on_key_release()
        except Exception as e:
            logger.exception(f"Error monitoring device {dev_path}: {e}")

    async def start_monitoring(self, on_key_press: KeyEventCallback, on_key_release: KeyEventCallback) -> None:
        """Start monitoring all matching keyboards."""
        keyboards = await self.find_keyboards()
        if not keyboards:
            raise RuntimeError("No keyboard input devices found.")

        await asyncio.gather(*(
            self.monitor_device(str(dev.path), on_key_press, on_key_release)
            for dev in keyboards
        ))


class TranscriptionClient:
    """Client for the transcription HTTP API."""

    def __init__(self, api_url: str, language: str = "en", pad_seconds: float = 0.0) -> None:
        self.api_url = api_url.rstrip('/')
        self.language = language
        self.pad_seconds = pad_seconds

    def transcribe(self, audio_data: bytes) -> str:
        """Send audio to transcription API and return text."""
        if not audio_data:
            logger.debug("No audio data to transcribe")
            return ""

        logger.info(f"Sending {len(audio_data)} bytes to transcription API")

        try:
            params = {"language": self.language}
            if self.pad_seconds > 0:
                params["pad_seconds"] = str(self.pad_seconds)

            response = requests.post(
                f"{self.api_url}/transcribe",
                data=audio_data,
                params=params,
                headers={"Content-Type": "application/octet-stream"},
                timeout=60
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("text", "").strip()
            logger.info(f"Transcription result: '{text}'")
            return text

        except requests.exceptions.RequestException as e:
            logger.exception(f"Transcription API error: {e}")
            return ""


# Keyboard layout mappings: character -> (keycode, needs_shift)
# Keycodes from linux/input-event-codes.h
LAYOUT_US = {
    'a': (30, False), 'b': (48, False), 'c': (46, False), 'd': (32, False),
    'e': (18, False), 'f': (33, False), 'g': (34, False), 'h': (35, False),
    'i': (23, False), 'j': (36, False), 'k': (37, False), 'l': (38, False),
    'm': (50, False), 'n': (49, False), 'o': (24, False), 'p': (25, False),
    'q': (16, False), 'r': (19, False), 's': (31, False), 't': (20, False),
    'u': (22, False), 'v': (47, False), 'w': (17, False), 'x': (45, False),
    'y': (21, False), 'z': (44, False),
    'A': (30, True), 'B': (48, True), 'C': (46, True), 'D': (32, True),
    'E': (18, True), 'F': (33, True), 'G': (34, True), 'H': (35, True),
    'I': (23, True), 'J': (36, True), 'K': (37, True), 'L': (38, True),
    'M': (50, True), 'N': (49, True), 'O': (24, True), 'P': (25, True),
    'Q': (16, True), 'R': (19, True), 'S': (31, True), 'T': (20, True),
    'U': (22, True), 'V': (47, True), 'W': (17, True), 'X': (45, True),
    'Y': (21, True), 'Z': (44, True),
    '1': (2, False), '2': (3, False), '3': (4, False), '4': (5, False),
    '5': (6, False), '6': (7, False), '7': (8, False), '8': (9, False),
    '9': (10, False), '0': (11, False),
    '!': (2, True), '@': (3, True), '#': (4, True), '$': (5, True),
    '%': (6, True), '^': (7, True), '&': (8, True), '*': (9, True),
    '(': (10, True), ')': (11, True),
    ' ': (57, False), '\n': (28, False), '\t': (15, False),
    '-': (12, False), '=': (13, False), '[': (26, False), ']': (27, False),
    '\\': (43, False), ';': (39, False), "'": (40, False), '`': (41, False),
    ',': (51, False), '.': (52, False), '/': (53, False),
    '_': (12, True), '+': (13, True), '{': (26, True), '}': (27, True),
    '|': (43, True), ':': (39, True), '"': (40, True), '~': (41, True),
    '<': (51, True), '>': (52, True), '?': (53, True),
}

LAYOUT_DE = {
    'a': (30, False), 'b': (48, False), 'c': (46, False), 'd': (32, False),
    'e': (18, False), 'f': (33, False), 'g': (34, False), 'h': (35, False),
    'i': (23, False), 'j': (36, False), 'k': (37, False), 'l': (38, False),
    'm': (50, False), 'n': (49, False), 'o': (24, False), 'p': (25, False),
    'q': (16, False), 'r': (19, False), 's': (31, False), 't': (20, False),
    'u': (22, False), 'v': (47, False), 'w': (17, False), 'x': (45, False),
    'y': (44, False), 'z': (21, False),  # Y and Z swapped
    'A': (30, True), 'B': (48, True), 'C': (46, True), 'D': (32, True),
    'E': (18, True), 'F': (33, True), 'G': (34, True), 'H': (35, True),
    'I': (23, True), 'J': (36, True), 'K': (37, True), 'L': (38, True),
    'M': (50, True), 'N': (49, True), 'O': (24, True), 'P': (25, True),
    'Q': (16, True), 'R': (19, True), 'S': (31, True), 'T': (20, True),
    'U': (22, True), 'V': (47, True), 'W': (17, True), 'X': (45, True),
    'Y': (44, True), 'Z': (21, True),  # Y and Z swapped
    '1': (2, False), '2': (3, False), '3': (4, False), '4': (5, False),
    '5': (6, False), '6': (7, False), '7': (8, False), '8': (9, False),
    '9': (10, False), '0': (11, False),
    '!': (2, True), '"': (3, True), '§': (4, True), '$': (5, True),
    '%': (6, True), '&': (7, True), '/': (8, True), '(': (9, True),
    ')': (10, True), '=': (11, True),
    ' ': (57, False), '\n': (28, False), '\t': (15, False),
    'ß': (12, False), '´': (13, False), 'ü': (26, False), '+': (27, False),
    '#': (43, False), 'ö': (39, False), 'ä': (40, False), '^': (41, False),
    ',': (51, False), '.': (52, False), '-': (53, False),
    '?': (12, True), '`': (13, True), 'Ü': (26, True), '*': (27, True),
    "'": (43, True), 'Ö': (39, True), 'Ä': (40, True), '°': (41, True),
    ';': (51, True), ':': (52, True), '_': (53, True),
}

KEYBOARD_LAYOUTS = {
    'us': LAYOUT_US,
    'de': LAYOUT_DE,
}


class YdotoolOutput:
    """Output handler using ydotool for text injection with keyboard layout support."""

    KEY_LEFTSHIFT = 42

    def __init__(self, layout: str = 'us', delay_ms: int = 0) -> None:
        self.delay_ms = delay_ms
        self.env = os.environ.copy()
        self.env["YDOTOOL_SOCKET"] = "/tmp/.ydotool_socket"
        if layout not in KEYBOARD_LAYOUTS:
            available = ', '.join(KEYBOARD_LAYOUTS.keys())
            raise ValueError(f"Unknown keyboard layout '{layout}'. Available: {available}")
        self.layout = KEYBOARD_LAYOUTS[layout]
        self.layout_name = layout

    def _char_to_keys(self, char: str) -> Optional[List[str]]:
        """Convert a character to ydotool key sequence."""
        if char not in self.layout:
            logger.warning(f"Character '{char}' not in {self.layout_name} layout, skipping")
            return None

        keycode, needs_shift = self.layout[char]
        if needs_shift:
            return [
                f"{self.KEY_LEFTSHIFT}:1",
                f"{keycode}:1", f"{keycode}:0",
                f"{self.KEY_LEFTSHIFT}:0"
            ]
        else:
            return [f"{keycode}:1", f"{keycode}:0"]

    def send_text(self, text: str) -> None:
        """Send text via ydotool with layout-aware key mapping."""
        if not text:
            logger.debug("Empty text, nothing to send")
            return

        text = text + " "
        logger.info(f"Injecting text via ydotool ({self.layout_name} layout): '{text}'")

        key_sequence: List[str] = []
        for char in text:
            keys = self._char_to_keys(char)
            if keys:
                key_sequence.extend(keys)

        if not key_sequence:
            logger.warning("No valid characters to type")
            return

        try:
            cmd = ["ydotool", "key"] + key_sequence
            result = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
            if result.returncode != 0:
                logger.error(f"ydotool failed with code {result.returncode}: {result.stderr}")
            else:
                logger.info("Text injection successful")

        except FileNotFoundError:
            logger.error("ydotool not found. Please install ydotool.")
        except Exception as e:
            logger.exception(f"Error running ydotool: {e}")


class SpeechToTextClient:
    """Main client coordinating all components."""

    def __init__(
        self,
        audio_recorder: AudioRecorder,
        keyboard_monitor: KeyboardMonitor,
        transcription_client: TranscriptionClient,
        output_handler: YdotoolOutput
    ) -> None:
        self.audio_recorder = audio_recorder
        self.keyboard_monitor = keyboard_monitor
        self.transcription_client = transcription_client
        self.output_handler = output_handler

    def on_key_press(self) -> None:
        """Handle activation key press."""
        logger.info("Key press detected, starting audio recording")
        self.audio_recorder.start_recording()

    def on_key_release(self) -> None:
        """Handle activation key release."""
        logger.info("Key release detected, processing audio")
        audio_data = self.audio_recorder.stop_recording()
        if audio_data:
            text = self.transcription_client.transcribe(audio_data)
            if text:
                self.output_handler.send_text(text)
            else:
                logger.info("Transcription returned empty text")
        else:
            logger.info("No audio data captured")

    def start(self) -> None:
        """Start the speech-to-text client."""
        logger.info("Starting speech-to-text client")

        try:
            asyncio.run(self.keyboard_monitor.start_monitoring(
                self.on_key_press,
                self.on_key_release
            ))
        finally:
            self.audio_recorder.cleanup()


def main() -> None:
    """Application entry point."""
    parser = argparse.ArgumentParser(description="Speech-to-text client")

    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:5000",
        help="URL of transcription API (default: http://localhost:5000)"
    )
    parser.add_argument(
        "--keyboard",
        type=str,
        help="Name of the keyboard to listen to (optional)"
    )
    parser.add_argument(
        "--key",
        type=str,
        default="KEY_RIGHTMETA",
        help="Activation key code (default: KEY_RIGHTMETA for Right Super)"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="auto",
        help="Language code for transcription, or 'auto' for detection (default: auto)"
    )
    parser.add_argument(
        "--pad-seconds",
        type=float,
        default=0.0,
        help="Pad audio to this duration in seconds (default: 0.0)"
    )
    parser.add_argument(
        "--layout",
        type=str,
        default="us",
        help=f"Keyboard layout for text injection (available: {', '.join(KEYBOARD_LAYOUTS.keys())}; default: us)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Create components
    audio_recorder = AudioRecorder()
    keyboard_monitor = KeyboardMonitor(args.keyboard, args.key)
    transcription_client = TranscriptionClient(args.api_url, args.language, args.pad_seconds)
    output_handler = YdotoolOutput(args.layout)

    # Create and start client
    client = SpeechToTextClient(
        audio_recorder,
        keyboard_monitor,
        transcription_client,
        output_handler
    )

    logger.info(f"Speech-to-text client starting")
    logger.info(f"  API URL: {args.api_url}")
    logger.info(f"  Activation key: {args.key}")
    logger.info(f"  Language: {args.language}")

    client.start()


if __name__ == "__main__":
    main()
