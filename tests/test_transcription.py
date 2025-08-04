"""
Test suite for transcription.py module

Tests transcription functionality with mock data and real scenarios.
"""

import os
import tempfile
import json
import unittest
import logging
from unittest.mock import Mock, patch, MagicMock, call
import subprocess
from pathlib import Path

# Import the module to test
import sys
sys.path.append(r'C:\Users\a22ca\OneDrive\Desktop\smart-edit\smart_edit')  # Note: also removed \transcription.py

from transcription import (
    SmartTranscriber,
    TranscriptionConfig,
    TranscriptSegment,
    WordTimestamp,
    ContentSection,
    TranscriptionResult,
    transcribe_video
)

class TestTranscriptionConfig(unittest.TestCase):
    """Test TranscriptionConfig class"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = TranscriptionConfig()
        
        self.assertTrue(config.accuracy_mode)
        self.assertEqual(config.language, "auto")
        self.assertTrue(config.enable_speaker_detection)
        self.assertTrue(config.enable_word_timestamps)
        self.assertEqual(config.model_size, "base")
        self.assertIn("um", config.filler_words)
        self.assertIn("uh", config.filler_words)
    
    def test_custom_config(self):
        """Test custom configuration"""
        custom_fillers = ["er", "hmm"]
        config = TranscriptionConfig(
            accuracy_mode=False,
            language="en",
            model_size="base",
            filler_words=custom_fillers
        )
        
        self.assertFalse(config.accuracy_mode)
        self.assertEqual(config.language, "en")
        self.assertEqual(config.model_size, "base")
        self.assertEqual(config.filler_words, custom_fillers)
    
    @patch('torch.cuda.is_available')
    def test_device_selection_cuda(self, mock_cuda):
        """Test CUDA device selection"""
        mock_cuda.return_value = True
        config = TranscriptionConfig(device="auto")
        self.assertEqual(config.device, "cuda")
    
    @patch('torch.cuda.is_available')
    def test_device_selection_cpu(self, mock_cuda):
        """Test CPU fallback"""
        mock_cuda.return_value = False
        config = TranscriptionConfig(device="auto")
        self.assertEqual(config.device, "cpu")

class TestSmartTranscriber(unittest.TestCase):
    """Test SmartTranscriber class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = TranscriptionConfig(model_size="base")  # Use smaller model for tests
        
        # Mock video file
        self.test_video_path = "/test/video.mp4"
        self.test_audio_path = "/tmp/video_audio_123.wav"
        
        # Mock Whisper result
        self.mock_whisper_result = {
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "Hello, welcome to the test.",
                    "avg_logprob": -0.5,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.95},
                        {"word": "welcome", "start": 0.6, "end": 1.2, "probability": 0.92},
                        {"word": "to", "start": 1.3, "end": 1.4, "probability": 0.98},
                        {"word": "the", "start": 1.5, "end": 1.7, "probability": 0.96},
                        {"word": "test", "start": 1.8, "end": 3.0, "probability": 0.94}
                    ]
                },
                {
                    "start": 3.5,
                    "end": 6.0,
                    "text": "This is a test segment.",
                    "avg_logprob": -0.3,
                    "words": [
                        {"word": "This", "start": 3.5, "end": 3.8, "probability": 0.97},
                        {"word": "is", "start": 3.9, "end": 4.1, "probability": 0.99},
                        {"word": "a", "start": 4.2, "end": 4.3, "probability": 0.95},
                        {"word": "test", "start": 4.4, "end": 4.8, "probability": 0.93},
                        {"word": "segment", "start": 4.9, "end": 6.0, "probability": 0.91}
                    ]
                }
            ]
        }
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_init_success(self, mock_load_model, mock_subprocess):
        """Test successful initialization"""
        mock_subprocess.return_value = Mock(returncode=0)
        mock_model = Mock()
        mock_load_model.return_value = mock_model
        
        transcriber = SmartTranscriber(self.config)
        
        self.assertEqual(transcriber.config, self.config)
        self.assertEqual(transcriber.model, mock_model)
        mock_load_model.assert_called_once_with("base", device=self.config.device)
    
    @patch('subprocess.run')
    def test_init_ffmpeg_missing(self, mock_subprocess):
        """Test initialization fails when FFmpeg is missing"""
        mock_subprocess.side_effect = FileNotFoundError()
        
        with self.assertRaises(RuntimeError) as context:
            SmartTranscriber(self.config)
        
        self.assertIn("FFmpeg not found", str(context.exception))
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_validate_files_success(self, mock_load_model, mock_subprocess):
        """Test file validation with valid files"""
        mock_subprocess.return_value = Mock(returncode=0)
        mock_load_model.return_value = Mock()
        
        transcriber = SmartTranscriber(self.config)
        
        with patch('os.path.exists') as mock_exists, \
             patch('os.path.getsize') as mock_getsize:
            mock_exists.return_value = True
            mock_getsize.return_value = 1024 * 1024  # 1MB
            
            # Should not raise
            transcriber._validate_files([self.test_video_path])
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_validate_files_not_found(self, mock_load_model, mock_subprocess):
        """Test file validation with missing file"""
        mock_subprocess.return_value = Mock(returncode=0)
        mock_load_model.return_value = Mock()
        
        transcriber = SmartTranscriber(self.config)
        
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            
            with self.assertRaises(FileNotFoundError):
                transcriber._validate_files([self.test_video_path])
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_validate_files_empty(self, mock_load_model, mock_subprocess):
        """Test file validation with empty file"""
        mock_subprocess.return_value = Mock(returncode=0)
        mock_load_model.return_value = Mock()
        
        transcriber = SmartTranscriber(self.config)
        
        with patch('os.path.exists') as mock_exists, \
             patch('os.path.getsize') as mock_getsize:
            mock_exists.return_value = True
            mock_getsize.return_value = 0
            
            with self.assertRaises(ValueError):
                transcriber._validate_files([self.test_video_path])
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    @patch('tempfile.gettempdir')
    @patch('time.time')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_extract_audio_success(self, mock_getsize, mock_exists, mock_time, 
                                 mock_tempdir, mock_load_model, mock_subprocess):
        """Test successful audio extraction"""
        # Setup mocks
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # FFmpeg validation
            Mock(returncode=0)   # Audio extraction
        ]
        mock_load_model.return_value = Mock()
        mock_tempdir.return_value = "/tmp"
        mock_time.return_value = 123456
        mock_exists.return_value = True
        mock_getsize.return_value = 1024 * 1024  # 1MB
        
        transcriber = SmartTranscriber(self.config)
        result_path = transcriber._extract_audio(self.test_video_path)
        
        expected_path = os.path.join("/tmp", "video_audio_123456.wav")
        self.assertEqual(result_path, expected_path)
        
        # Check FFmpeg command
        extract_call = mock_subprocess.call_args_list[1]
        args = extract_call[0][0]
        self.assertEqual(args[0], 'ffmpeg')
        self.assertIn(self.test_video_path, args)
        self.assertIn(expected_path, args)
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_extract_audio_ffmpeg_fail(self, mock_load_model, mock_subprocess):
        """Test audio extraction with FFmpeg failure"""
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # FFmpeg validation
            subprocess.CalledProcessError(1, 'ffmpeg', stderr='FFmpeg error')
        ]
        mock_load_model.return_value = Mock()
        
        transcriber = SmartTranscriber(self.config)
        
        with self.assertRaises(RuntimeError) as context:
            transcriber._extract_audio(self.test_video_path)
        
        self.assertIn("FFmpeg failed", str(context.exception))
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    def test_transcribe_audio_success(self, mock_remove, mock_getsize, mock_exists, 
                                    mock_load_model, mock_subprocess):
        """Test successful audio transcription"""
        # Setup mocks
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # FFmpeg validation
            Mock(returncode=0)   # Audio extraction
        ]
        mock_model = Mock()
        mock_model.transcribe.return_value = self.mock_whisper_result
        mock_load_model.return_value = mock_model
        mock_exists.return_value = True
        mock_getsize.return_value = 1024 * 1024
        
        transcriber = SmartTranscriber(self.config)
        
        with patch.object(transcriber, '_extract_audio') as mock_extract:
            mock_extract.return_value = self.test_audio_path
            
            result = transcriber._transcribe_audio(self.test_video_path)
            
            self.assertEqual(result, self.mock_whisper_result)
            mock_model.transcribe.assert_called_once()
            mock_remove.assert_called_once_with(self.test_audio_path)

class TestSegmentProcessing(unittest.TestCase):
    """Test segment processing methods"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = TranscriptionConfig(model_size="base")
        
        with patch('subprocess.run') as mock_subprocess, \
             patch('transcription.whisper.load_model') as mock_load_model:
            mock_subprocess.return_value = Mock(returncode=0)
            mock_load_model.return_value = Mock()
            self.transcriber = SmartTranscriber(self.config)
    
    def test_analyze_speech_rate(self):
        """Test speech rate analysis"""
        # Slow speech (1 word per second)
        slow_segment = {"start": 0.0, "end": 4.0, "text": "Hello there friend buddy"}
        self.assertEqual(self.transcriber._analyze_speech_rate(slow_segment), "slow")
        
        # Fast speech (4 words per second)
        fast_segment = {"start": 0.0, "end": 1.0, "text": "Hello there friend buddy"}
        self.assertEqual(self.transcriber._analyze_speech_rate(fast_segment), "fast")
        
        # Normal speech (2 words per second)
        normal_segment = {"start": 0.0, "end": 2.0, "text": "Hello there friend buddy"}
        self.assertEqual(self.transcriber._analyze_speech_rate(normal_segment), "normal")
        
        # Zero duration
        zero_segment = {"start": 0.0, "end": 0.0, "text": "Hello"}
        self.assertEqual(self.transcriber._analyze_speech_rate(zero_segment), "normal")
    
    def test_classify_content_type(self):
        """Test content type classification"""
        # Greeting
        greeting = self.transcriber._classify_content_type("Hello, welcome to the show", 0, 10)
        self.assertEqual(greeting, "greeting")
        
        # Topic introduction
        topic_intro = self.transcriber._classify_content_type("Today we'll discuss Python", 1, 10)
        self.assertEqual(topic_intro, "greeting")
        
        # Conclusion
        conclusion = self.transcriber._classify_content_type("Thank you for watching", 8, 10)
        self.assertEqual(conclusion, "conclusion")
        
        # Transition
        transition = self.transcriber._classify_content_type("Now let's move on to the next topic", 5, 10)
        self.assertEqual(transition, "transition")
        
        # Main point
        main_point = self.transcriber._classify_content_type("This is really important to remember", 5, 10)
        self.assertEqual(main_point, "main_point")
        
        # Question
        question = self.transcriber._classify_content_type("What do you think about this?", 5, 10)
        self.assertEqual(question, "main_point")
        
        # Supporting
        supporting = self.transcriber._classify_content_type("This is just some regular text", 5, 10)
        self.assertEqual(supporting, "supporting")
    
    def test_calculate_pause_after(self):
        """Test pause calculation"""
        segments = [
            {"start": 0.0, "end": 3.0},
            {"start": 4.0, "end": 7.0},
            {"start": 7.2, "end": 10.0}
        ]
        
        # Pause between first and second segment
        pause1 = self.transcriber._calculate_pause_after(segments[0], segments, 0)
        self.assertEqual(pause1, 1.0)  # 4.0 - 3.0
        
        # Small pause between second and third segment
        pause2 = self.transcriber._calculate_pause_after(segments[1], segments, 1)
        self.assertAlmostEqual(pause2, 0.2, places=1)   # 7.2 - 7.0
        
        # No pause after last segment
        pause3 = self.transcriber._calculate_pause_after(segments[2], segments, 2)
        self.assertEqual(pause3, 0.0)
    
    def test_find_natural_breaks(self):
        """Test natural break detection"""
        segments = [
            TranscriptSegment(
                start=0.0, end=3.0, text="Hello.", speaker="Speaker_1",
                confidence=0.9, sentence_boundary=True, pause_after=1.0,
                speech_rate="normal", contains_filler=False,
                content_type="greeting", words=[]
            ),
            TranscriptSegment(
                start=4.0, end=7.0, text="Now let's begin", speaker="Speaker_1",
                confidence=0.9, sentence_boundary=False, pause_after=0.2,
                speech_rate="normal", contains_filler=False,
                content_type="transition", words=[]
            )
        ]
        
        breaks = self.transcriber._find_natural_breaks(segments)
        
        # Should include sentence boundary with long pause and transition start
        self.assertIn(3.0, breaks)  # Sentence boundary with pause > 0.5
        self.assertIn(4.0, breaks)  # Transition start
    
    def test_find_speaker_changes(self):
        """Test speaker change detection"""
        segments = [
            TranscriptSegment(
                start=0.0, end=3.0, text="Hello", speaker="Speaker_1",
                confidence=0.9, sentence_boundary=True, pause_after=0.5,
                speech_rate="normal", contains_filler=False,
                content_type="greeting", words=[]
            ),
            TranscriptSegment(
                start=3.5, end=6.0, text="Hi there", speaker="Speaker_2",
                confidence=0.9, sentence_boundary=True, pause_after=0.3,
                speech_rate="normal", contains_filler=False,
                content_type="greeting", words=[]
            ),
            TranscriptSegment(
                start=6.5, end=9.0, text="How are you", speaker="Speaker_1",
                confidence=0.9, sentence_boundary=True, pause_after=0.2,
                speech_rate="normal", contains_filler=False,
                content_type="supporting", words=[]
            )
        ]
        
        changes = self.transcriber._find_speaker_changes(segments)
        
        # Should detect changes from Speaker_1 to Speaker_2 and back
        self.assertIn(3.5, changes)  # First speaker change
        self.assertIn(6.5, changes)  # Second speaker change
        self.assertEqual(len(changes), 2)

class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    def test_transcribe_video_single_file(self, mock_remove, mock_getsize, mock_exists,
                                        mock_load_model, mock_subprocess):
        """Test complete transcription workflow for single video"""
        # Setup mocks
        mock_subprocess.side_effect = [
            Mock(returncode=0),  # FFmpeg validation
            Mock(returncode=0)   # Audio extraction
        ]
        
        mock_whisper_result = {
            "language": "en",
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "Hello, welcome to the test.",
                    "avg_logprob": -0.5,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.95}
                    ]
                }
            ]
        }
        
        mock_model = Mock()
        mock_model.transcribe.return_value = mock_whisper_result
        mock_load_model.return_value = mock_model
        mock_exists.return_value = True
        mock_getsize.return_value = 1024 * 1024
        
        config = TranscriptionConfig(model_size="base")
        
        with patch('tempfile.gettempdir') as mock_tempdir, \
             patch('time.time') as mock_time:
            mock_tempdir.return_value = "/tmp"
            mock_time.return_value = 123456
            
            result = transcribe_video("/test/video.mp4", config)
            
            # Verify result structure
            self.assertIsInstance(result, TranscriptionResult)
            self.assertEqual(len(result.segments), 1)
            self.assertEqual(result.metadata['language_detected'], 'en')
            self.assertEqual(result.metadata['video_count'], 1)
            self.assertIn("Hello, welcome to the test.", result.full_text)
    
    def test_save_and_load_result(self):
        """Test saving and loading results"""
        # Create a sample result
        segments = [
            TranscriptSegment(
                start=0.0, end=3.0, text="Test segment", speaker="Speaker_1",
                confidence=0.9, sentence_boundary=True, pause_after=0.5,
                speech_rate="normal", contains_filler=False,
                content_type="greeting", words=[]
            )
        ]
        
        result = TranscriptionResult(
            segments=segments,
            natural_breaks=[3.0],
            speaker_changes=[],
            content_sections=[],
            metadata={"test": "data"},
            full_text="Test segment"
        )
        
        config = TranscriptionConfig(model_size="base")
        
        with patch('subprocess.run') as mock_subprocess, \
             patch('transcription.whisper.load_model') as mock_load_model:
            mock_subprocess.return_value = Mock(returncode=0)
            mock_load_model.return_value = Mock()
            
            transcriber = SmartTranscriber(config)
            
            # Test saving to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                temp_path = f.name
            
            try:
                transcriber.save_result(result, temp_path)
                
                # Verify file was created and contains expected data
                self.assertTrue(os.path.exists(temp_path))
                
                with open(temp_path, 'r') as f:
                    loaded_data = json.load(f)
                
                self.assertEqual(len(loaded_data['segments']), 1)
                self.assertEqual(loaded_data['segments'][0]['text'], "Test segment")
                self.assertEqual(loaded_data['full_text'], "Test segment")
                self.assertEqual(loaded_data['metadata']['test'], "data")
                
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios"""
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_whisper_model_loading_failure(self, mock_load_model, mock_subprocess):
        """Test handling of Whisper model loading failure"""
        mock_subprocess.return_value = Mock(returncode=0)
        mock_load_model.side_effect = Exception("Model loading failed")
        
        with self.assertRaises(Exception) as context:
            SmartTranscriber()
        
        self.assertIn("Model loading failed", str(context.exception))
    
    @patch('subprocess.run')
    @patch('transcription.whisper.load_model')
    def test_empty_segments_handling(self, mock_load_model, mock_subprocess):
        """Test handling of empty transcription results"""
        mock_subprocess.return_value = Mock(returncode=0)
        mock_model = Mock()
        mock_model.transcribe.return_value = {"language": "en", "segments": []}
        mock_load_model.return_value = mock_model
        
        transcriber = SmartTranscriber()
        
        with patch.object(transcriber, '_validate_files'), \
             patch.object(transcriber, '_extract_audio') as mock_extract, \
             patch('os.remove'):
            mock_extract.return_value = "/tmp/test.wav"
            
            result = transcriber.transcribe_video("/test/video.mp4")
            
            self.assertEqual(len(result.segments), 0)
            self.assertEqual(len(result.natural_breaks), 0)
            self.assertEqual(len(result.speaker_changes), 0)
            self.assertEqual(result.full_text, "")

if __name__ == '__main__':
    # Set up test logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise during tests
    
    # Run tests
    unittest.main(verbosity=2)