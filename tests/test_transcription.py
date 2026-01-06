import sys
import os
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stt_client import AudioRecorder, SpeechToTextClient, TranscriptionClient, YdotoolOutput


class TestAudioRecording:
    """Test audio recording functionality."""

    def setup_method(self):
        """Setup real audio recorder instance."""
        self.recorder = AudioRecorder()

    def test_audio_callback(self):
        """Test audio callback with real queue."""
        test_data = b"audio_test_data"

        self.recorder.audio_callback(test_data, 1024, None, None)

        assert not self.recorder.audio_queue.empty()
        retrieved_data = self.recorder.audio_queue.get()
        assert retrieved_data == test_data

    def test_stop_recording_no_stream(self):
        """Test stopping recording when no stream exists."""
        result = self.recorder.stop_recording()
        assert result == b""


class TestTranscriptionClient:
    """Test transcription client functionality."""

    def test_transcribe_empty_audio(self):
        """Test that empty audio returns empty string."""
        client = TranscriptionClient("http://localhost:5000")
        result = client.transcribe(b"")
        assert result == ""

    @patch('stt_client.requests.post')
    def test_transcribe_success(self, mock_post):
        """Test successful transcription."""
        mock_response = Mock()
        mock_response.json.return_value = {"text": "hello world"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client = TranscriptionClient("http://localhost:5000", language="en")
        result = client.transcribe(b"audio_data")

        assert result == "hello world"
        mock_post.assert_called_once()


class TestYdotoolOutput:
    """Test ydotool output handler."""

    def test_send_empty_text(self):
        """Test that empty text is not sent."""
        output = YdotoolOutput()
        # Should not raise, should just return
        output.send_text("")

    @patch('stt_client.subprocess.run')
    def test_send_text_success(self, mock_run):
        """Test successful text injection."""
        mock_run.return_value = Mock(returncode=0)

        output = YdotoolOutput()
        output.send_text("hello world")

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "ydotool" in call_args
        assert "hello world" in call_args


class TestSpeechToTextClient:
    """Test overall client workflow."""

    def test_key_press_starts_recording(self):
        """Test that key press starts recording."""
        audio_recorder = Mock()
        keyboard_monitor = Mock()
        transcription_client = Mock()
        output_handler = Mock()

        client = SpeechToTextClient(
            audio_recorder, keyboard_monitor,
            transcription_client, output_handler
        )

        client.on_key_press()
        audio_recorder.start_recording.assert_called_once()

    def test_key_release_processes_audio(self):
        """Test that key release processes audio data."""
        audio_recorder = Mock()
        keyboard_monitor = Mock()
        transcription_client = Mock()
        output_handler = Mock()

        audio_recorder.stop_recording.return_value = b"audio_data"
        transcription_client.transcribe.return_value = "transcribed text"

        client = SpeechToTextClient(
            audio_recorder, keyboard_monitor,
            transcription_client, output_handler
        )

        client.on_key_release()

        audio_recorder.stop_recording.assert_called_once()
        transcription_client.transcribe.assert_called_once_with(b"audio_data")
        output_handler.send_text.assert_called_once_with("transcribed text")
