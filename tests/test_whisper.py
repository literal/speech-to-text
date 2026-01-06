import sys
import os
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import transcription_server
from transcription_server import audio_bytes_to_numpy, load_model


class TestTranscriptionServer:
    """Test transcription server functionality with actual Whisper model."""

    @classmethod
    def setup_class(cls):
        """Load Whisper model once for all tests."""
        load_model("small.en")

    def load_real_audio(self) -> bytes:
        """Load the real hello speech WAV file.

        Returns raw audio bytes from the test WAV file.
        """
        # https://freesound.org/people/AderuMoro/sounds/213282/
        test_file = os.path.join(os.path.dirname(__file__),
                                "213282__aderumoro__hello-female-friendly-professional-16kHz.wav")

        if not os.path.exists(test_file):
            raise FileNotFoundError(f"Test audio file not found: {test_file}")

        with wave.open(test_file, 'rb') as wav_file:
            audio_data = wav_file.readframes(wav_file.getnframes())

            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            framerate = wav_file.getframerate()

            if channels != 1 or sample_width != 2 or framerate != 16000:
                try:
                    import numpy as np
                    from numpy.typing import NDArray

                    audio_np: NDArray[np.float32]
                    if sample_width == 1:
                        raw_audio = np.frombuffer(audio_data, dtype=np.uint8)
                        audio_np = (raw_audio.astype(np.float32) - 128) / 128.0
                    elif sample_width == 2:
                        raw_audio = np.frombuffer(audio_data, dtype=np.int16)
                        audio_np = raw_audio.astype(np.float32) / 32768.0
                    elif sample_width == 4:
                        raw_audio = np.frombuffer(audio_data, dtype=np.int32)
                        audio_np = raw_audio.astype(np.float32) / 2147483648.0
                    else:
                        return audio_data

                    if channels == 2:
                        audio_np = audio_np.reshape(-1, 2).mean(axis=1)

                    if framerate != 16000:
                        step = framerate / 16000
                        indices = np.arange(0, len(audio_np), step).astype(int)
                        audio_np = audio_np[indices]

                    audio_data = (audio_np * 32767).astype(np.int16).tobytes()
                except ImportError:
                    pass

            return audio_data

    def test_audio_bytes_to_numpy(self):
        """Test conversion of audio bytes to numpy array."""
        import numpy as np

        # Create test audio data
        test_audio = b"\x00\x00\xff\x7f"  # Two 16-bit samples
        result = audio_bytes_to_numpy(test_audio)

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result) == 2

    def test_whisper_transcription_with_real_speech(self):
        """Test Whisper transcription with real 'hello' speech audio."""
        audio_bytes = self.load_real_audio()

        assert len(audio_bytes) > 0

        audio_np = audio_bytes_to_numpy(audio_bytes)
        result = transcription_server.model.transcribe(audio_np, fp16=False, language="en")
        text = result.get("text", "").strip()

        assert isinstance(text, str)
        result_lower = text.lower().strip()
        assert "hello" in result_lower, f"Expected 'hello' in transcription, got: '{text}'"

    def test_empty_audio_handling(self):
        """Test that empty audio is handled gracefully."""
        audio_np = audio_bytes_to_numpy(b"")
        assert len(audio_np) == 0

    def test_file_exists(self):
        """Test that the required audio file exists."""
        test_file = os.path.join(os.path.dirname(__file__),
                                "213282__aderumoro__hello-female-friendly-professional-16kHz.wav")
        assert os.path.exists(test_file), f"Test audio file missing: {test_file}"

    def test_short_audio_handling(self):
        """Test that very short audio is handled gracefully."""
        short_audio = b"\x00\x00" * 1600  # 1600 samples = 0.1s at 16kHz
        audio_np = audio_bytes_to_numpy(short_audio)
        result = transcription_server.model.transcribe(audio_np, fp16=False, language="en")
        text = result.get("text", "").strip()
        assert isinstance(text, str)
