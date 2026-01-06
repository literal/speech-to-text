"""HTTP API server for speech-to-text transcription.

This server runs inside a Docker container and exposes a simple REST API
for transcribing audio data using Whisper.
"""

import argparse
import io
import logging
import wave
from typing import Any

import numpy as np
import whisper
from flask import Flask, Response, jsonify, request

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Global model instance (loaded once at startup)
model: Any = None
model_name: str = ""


def load_model(name: str = "small.en") -> None:
    """Load the Whisper model."""
    global model, model_name
    logger.info(f"Loading Whisper model: {name}")
    model = whisper.load_model(name)
    model_name = name
    logger.info("Whisper model loaded successfully")


def audio_bytes_to_numpy(audio_data: bytes) -> np.ndarray:
    """Convert raw PCM audio bytes (16-bit, 16kHz, mono) to numpy array."""
    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
    return audio_np


@app.route("/health", methods=["GET"])
def health() -> Response:
    """Health check endpoint."""
    return jsonify({"status": "healthy", "model_loaded": model is not None})


@app.route("/info", methods=["GET"])
def info() -> Response:
    """Server info endpoint."""
    return jsonify({"model": model_name, "model_loaded": model is not None})


@app.route("/transcribe", methods=["POST"])
def transcribe() -> tuple[Response, int]:
    """Transcribe audio data to text.

    Expects raw PCM audio data (16-bit, 16kHz, mono) in request body.

    Optional query parameters:
    - language: Language code for transcription (default: en)
    - pad_seconds: Pad audio to this duration in seconds (default: 0)

    Returns JSON with 'text' field containing transcribed text.
    """
    if model is None:
        return jsonify({"error": "Model not loaded"}), 500

    audio_data = request.data
    if not audio_data:
        return jsonify({"error": "No audio data provided"}), 400

    language = request.args.get("language", "auto")
    pad_seconds = float(request.args.get("pad_seconds", "0"))

    # Use None for auto-detection
    if language == "auto":
        language = None

    logger.info(f"Received {len(audio_data)} bytes of audio data (language: {language or 'auto'})")

    try:
        audio_np = audio_bytes_to_numpy(audio_data)

        # Apply padding if requested
        if pad_seconds > 0:
            sample_rate = 16000
            target_samples = int(pad_seconds * sample_rate)
            if len(audio_np) < target_samples:
                padding_samples = target_samples - len(audio_np)
                current_duration = len(audio_np) / sample_rate
                logger.info(f"Padding audio from {current_duration:.2f}s to {pad_seconds}s")
                audio_np = np.pad(audio_np, (0, padding_samples), mode='constant', constant_values=0.0)

        result = model.transcribe(audio_np, fp16=False, language=language)
        text = result.get("text", "").strip()

        logger.info(f"Transcription completed: '{text}'")
        return jsonify({"text": text}), 200

    except Exception as e:
        logger.exception(f"Transcription error: {e}")
        return jsonify({"error": str(e)}), 500


def main() -> None:
    """Application entry point."""
    parser = argparse.ArgumentParser(description="Transcription API server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to bind to (default: 5000)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="small.en",
        help="Whisper model to use (default: small.en)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load model before starting server
    load_model(args.model)

    # Run Flask server
    logger.info(f"Starting transcription server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
