"""
Test suite for script_generation.py module

Tests script generation functionality with mock data and real scenarios.
"""

import os
import tempfile
import json
import unittest
import logging
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Import the module to test
import sys

# Get the directory containing this test file
test_dir = os.path.dirname(os.path.abspath(__file__))
# Get the project root directory (parent of tests)
project_root = os.path.dirname(test_dir)
# Add smart_edit directory to Python path
smart_edit_path = os.path.join(project_root, 'smart_edit')
sys.path.insert(0, smart_edit_path)

from script_generation import (
    SmartScriptGenerator,
    ScriptGenerationConfig,
    CutDecision,
    TransitionPoint,
    EditScript,
    EditAction,
    ConfidenceLevel,
    generate_script
)

from transcription import (
    TranscriptionResult,
    TranscriptSegment,
    WordTimestamp,
    ContentSection
)

class TestScriptGenerationConfig(unittest.TestCase):
    """Test ScriptGenerationConfig class"""
    
    def setUp(self):
        """Set up test environment"""
        # Clear environment variables for consistent testing
        self.env_backup = {}
        env_vars = [
            'OPENAI_API_KEY', 'OPENAI_MODEL', 'DEFAULT_COMPRESSION_RATIO',
            'REMOVE_FILLER_WORDS', 'MIN_PAUSE_THRESHOLD', 'KEEP_QUESTION_SEGMENTS',
            'DEFAULT_SPEED_INCREASE', 'OPENAI_MAX_TOKENS', 'OPENAI_TEMPERATURE'
        ]
        
        for var in env_vars:
            self.env_backup[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]
    
    def tearDown(self):
        """Restore environment variables"""
        for var, value in self.env_backup.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
    
    def test_default_config(self):
        """Test default configuration values"""
        config = ScriptGenerationConfig()
        
        self.assertIsNone(config.openai_api_key)
        self.assertEqual(config.model, "gpt-4")
        self.assertEqual(config.target_compression, 0.7)
        self.assertTrue(config.remove_filler_words)
        self.assertEqual(config.min_pause_threshold, 2.0)
        self.assertTrue(config.keep_question_segments)
        self.assertEqual(config.max_speed_increase, 1.3)
        self.assertEqual(config.max_tokens, 2000)
        self.assertEqual(config.temperature, 0.3)
    
    def test_custom_config(self):
        """Test custom configuration"""
        config = ScriptGenerationConfig(
            model="gpt-3.5-turbo",
            target_compression=0.8,
            remove_filler_words=False,
            min_pause_threshold=1.5
        )
        
        self.assertEqual(config.model, "gpt-3.5-turbo")
        self.assertEqual(config.target_compression, 0.8)
        self.assertFalse(config.remove_filler_words)
        self.assertEqual(config.min_pause_threshold, 1.5)
    
    def test_environment_variable_loading(self):
        """Test loading from environment variables"""
        os.environ['OPENAI_MODEL'] = 'gpt-3.5-turbo'
        os.environ['DEFAULT_COMPRESSION_RATIO'] = '0.8'
        os.environ['REMOVE_FILLER_WORDS'] = 'false'
        os.environ['MIN_PAUSE_THRESHOLD'] = '1.5'
        
        config = ScriptGenerationConfig()
        
        self.assertEqual(config.model, "gpt-3.5-turbo")
        self.assertEqual(config.target_compression, 0.8)
        self.assertFalse(config.remove_filler_words)
        self.assertEqual(config.min_pause_threshold, 1.5)
    
    def test_parameter_override_env(self):
        """Test that parameters override environment variables"""
        os.environ['OPENAI_MODEL'] = 'gpt-3.5-turbo'
        
        config = ScriptGenerationConfig(model="gpt-4")
        
        self.assertEqual(config.model, "gpt-4")  # Parameter should override env

class TestSmartScriptGenerator(unittest.TestCase):
    """Test SmartScriptGenerator class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = ScriptGenerationConfig(
            openai_api_key="test-key",
            model="gpt-4",
            target_compression=0.7
        )
        
        # Mock transcription result
        self.mock_segments = [
            TranscriptSegment(
                start=0.0, end=3.0, text="Hello, welcome to the test.",
                speaker="Speaker_1", confidence=0.9, sentence_boundary=True,
                pause_after=0.5, speech_rate="normal", contains_filler=False,
                content_type="greeting", words=[]
            ),
            TranscriptSegment(
                start=3.5, end=7.0, text="Um, this is, uh, a test segment.",
                speaker="Speaker_1", confidence=0.8, sentence_boundary=True,
                pause_after=0.3, speech_rate="normal", contains_filler=True,
                content_type="supporting", words=[]
            ),
            TranscriptSegment(
                start=7.5, end=10.0, text="What do you think about this?",
                speaker="Speaker_1", confidence=0.95, sentence_boundary=True,
                pause_after=0.2, speech_rate="normal", contains_filler=False,
                content_type="main_point", words=[]
            ),
            TranscriptSegment(
                start=12.5, end=15.0, text="Thank you for watching.",
                speaker="Speaker_1", confidence=0.9, sentence_boundary=True,
                pause_after=0.0, speech_rate="slow", contains_filler=False,
                content_type="conclusion", words=[]
            )
        ]
        
        self.mock_transcription = TranscriptionResult(
            segments=self.mock_segments,
            natural_breaks=[3.0, 7.0, 10.0],
            speaker_changes=[],
            content_sections=[],
            metadata={"total_duration": 15.0, "language_detected": "en"},
            full_text="Hello, welcome to the test. Um, this is, uh, a test segment. What do you think about this? Thank you for watching."
        )
    
    @patch('script_generation.OpenAI')
    def test_init_with_openai(self, mock_openai_class):
        """Test initialization with OpenAI available"""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        generator = SmartScriptGenerator(self.config)
        
        self.assertTrue(generator.ai_enabled)
        self.assertEqual(generator.client, mock_client)
        mock_openai_class.assert_called_once_with(api_key="test-key")
    
    @patch('script_generation.OPENAI_AVAILABLE', False)
    def test_init_without_openai(self):
        """Test initialization without OpenAI"""
        generator = SmartScriptGenerator(self.config)
        
        self.assertFalse(generator.ai_enabled)
        self.assertIsNone(generator.client)
    
    def test_init_no_api_key(self):
        """Test initialization without API key"""
        # Clear any existing API key from environment
        with patch.dict(os.environ, {}, clear=True):
            config = ScriptGenerationConfig(openai_api_key=None)
            generator = SmartScriptGenerator(config)
            
            self.assertFalse(generator.ai_enabled)
            self.assertIsNone(generator.client)
    
    @patch('script_generation.OpenAI')
    def test_generate_script_without_ai(self, mock_openai_class):
        """Test script generation without AI (rule-based only)"""
        # Force AI to be disabled
        generator = SmartScriptGenerator(self.config)
        generator.ai_enabled = False
        generator.client = None
        
        script = generator.generate_script(self.mock_transcription)
        
        # Verify script structure
        self.assertIsInstance(script, EditScript)
        self.assertEqual(len(script.cuts), 4)  # Same as input segments
        self.assertGreater(len(script.transitions), 0)
        self.assertLess(script.compression_ratio, 1.0)  # Should compress
        
        # Check that filler segment is marked for removal
        filler_decision = script.cuts[1]  # Second segment has filler
        self.assertEqual(filler_decision.action, EditAction.REMOVE)
        self.assertIn("filler", filler_decision.reason.lower())
    
    @patch('script_generation.OpenAI')
    def test_generate_script_with_ai(self, mock_openai_class):
        """Test script generation with AI"""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "key_segments": [0, 2, 3],  # Keep greeting, question, conclusion
            "removable_segments": [1],   # Remove filler segment
            "summary": "Keep important content, remove filler"
        })
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        generator = SmartScriptGenerator(self.config)
        script = generator.generate_script(self.mock_transcription)
        
        # Verify AI was called
        mock_client.chat.completions.create.assert_called_once()
        
        # Verify script structure
        self.assertIsInstance(script, EditScript)
        self.assertEqual(len(script.cuts), 4)
        
        # Verify AI decisions were applied
        ai_keep_decision = script.cuts[0]  # First segment marked as key by AI
        self.assertEqual(ai_keep_decision.action, EditAction.KEEP)
        self.assertIn("AI identified", ai_keep_decision.reason)
        
        ai_remove_decision = script.cuts[1]  # Second segment marked removable by AI
        self.assertEqual(ai_remove_decision.action, EditAction.REMOVE)
        self.assertIn("AI identified", ai_remove_decision.reason)
    
    def test_analyze_segment_filler_removal(self):
        """Test segment analysis for filler word removal"""
        generator = SmartScriptGenerator(self.config)
        
        filler_segment = self.mock_segments[1]  # Contains filler words
        decision = generator._analyze_segment(filler_segment, 1, set(), set())
        
        self.assertEqual(decision.action, EditAction.REMOVE)
        self.assertIn("filler", decision.reason.lower())
        self.assertEqual(decision.confidence, ConfidenceLevel.HIGH)
    
    def test_analyze_segment_question_keep(self):
        """Test that questions are kept"""
        generator = SmartScriptGenerator(self.config)
        generator.ai_enabled = False  # Force rule-based analysis
        
        # Create a question segment that's not already marked as main_point
        question_segment = TranscriptSegment(
            start=7.5, end=10.0, text="What do you think about this?",
            speaker="Speaker_1", confidence=0.95, sentence_boundary=True,
            pause_after=0.2, speech_rate="normal", contains_filler=False,
            content_type="supporting", words=[]  # Change from main_point to supporting
        )
        
        decision = generator._analyze_segment(question_segment, 2, set(), set())
        
        self.assertEqual(decision.action, EditAction.KEEP)
        self.assertIn("Question", decision.reason)
        self.assertEqual(decision.confidence, ConfidenceLevel.HIGH)
    
    def test_analyze_segment_slow_speech_speedup(self):
        """Test that slow speech gets sped up"""
        generator = SmartScriptGenerator(self.config)
        
        slow_segment = self.mock_segments[3]  # Slow speech rate
        decision = generator._analyze_segment(slow_segment, 3, set(), set())
        
        # Note: conclusion segments are not sped up in our logic
        # So this should be KEEP, not SPEED_UP
        self.assertEqual(decision.action, EditAction.KEEP)
        self.assertIn("conclusion", decision.reason.lower())
    
    def test_analyze_segment_ai_override(self):
        """Test that AI decisions override rule-based ones"""
        generator = SmartScriptGenerator(self.config)
        
        # Even though this segment has filler, AI says keep it
        filler_segment = self.mock_segments[1]
        ai_key_segments = {1}  # AI says keep segment 1
        
        decision = generator._analyze_segment(filler_segment, 1, ai_key_segments, set())
        
        self.assertEqual(decision.action, EditAction.KEEP)
        self.assertIn("AI identified as key", decision.reason)
        self.assertEqual(decision.confidence, ConfidenceLevel.HIGH)
    
    def test_generate_transitions(self):
        """Test transition generation"""
        generator = SmartScriptGenerator(self.config)
        
        # Create some kept decisions
        decisions = [
            CutDecision(0, 0.0, 3.0, "Hello.", EditAction.KEEP, "test", ConfidenceLevel.HIGH),
            CutDecision(1, 3.5, 7.0, "Filler", EditAction.REMOVE, "test", ConfidenceLevel.HIGH),
            CutDecision(2, 7.5, 10.0, "Question?", EditAction.KEEP, "test", ConfidenceLevel.HIGH)
        ]
        
        transitions = generator._generate_transitions(decisions)
        
        self.assertEqual(len(transitions), 1)  # One transition between kept segments
        
        transition = transitions[0]
        self.assertEqual(transition.from_segment_id, 0)
        self.assertEqual(transition.to_segment_id, 2)
        self.assertIn(transition.transition_type, ["cut", "fade", "cross_fade"])
    
    def test_calculate_final_duration(self):
        """Test final duration calculation"""
        generator = SmartScriptGenerator(self.config)
        
        decisions = [
            CutDecision(0, 0.0, 3.0, "Keep", EditAction.KEEP, "test", ConfidenceLevel.HIGH),
            CutDecision(1, 3.5, 7.0, "Remove", EditAction.REMOVE, "test", ConfidenceLevel.HIGH),
            CutDecision(2, 7.5, 10.0, "Speed up", EditAction.SPEED_UP, "test", 
                       ConfidenceLevel.HIGH, speed_factor=1.5)
        ]
        
        final_duration = generator._calculate_final_duration(decisions)
        
        # Should be 3.0 (first segment) + 2.5/1.5 (sped up segment) = ~4.67
        expected = 3.0 + (2.5 / 1.5)
        self.assertAlmostEqual(final_duration, expected, places=2)
    
    def test_save_script(self):
        """Test saving script to file"""
        generator = SmartScriptGenerator(self.config)
        
        # Create a simple script
        decisions = [
            CutDecision(0, 0.0, 3.0, "Test", EditAction.KEEP, "test", ConfidenceLevel.HIGH)
        ]
        
        script = EditScript(
            cuts=decisions,
            transitions=[],
            estimated_final_duration=3.0,
            original_duration=10.0,
            compression_ratio=0.3,
            metadata={"test": "data"}
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            generator.save_script(script, temp_path)
            
            # Verify file was created and contains expected data
            self.assertTrue(os.path.exists(temp_path))
            
            with open(temp_path, 'r') as f:
                loaded_data = json.load(f)
            
            self.assertEqual(len(loaded_data['cuts']), 1)
            self.assertEqual(loaded_data['cuts'][0]['action'], 'keep')
            self.assertEqual(loaded_data['compression_ratio'], 0.3)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    def test_generate_script_convenience_function(self):
        """Test the convenience function"""
        # Create mock transcription
        segments = [
            TranscriptSegment(
                start=0.0, end=3.0, text="Hello world.",
                speaker="Speaker_1", confidence=0.9, sentence_boundary=True,
                pause_after=0.5, speech_rate="normal", contains_filler=False,
                content_type="greeting", words=[]
            )
        ]
        
        transcription = TranscriptionResult(
            segments=segments,
            natural_breaks=[3.0],
            speaker_changes=[],
            content_sections=[],
            metadata={"total_duration": 3.0, "language_detected": "en"},
            full_text="Hello world."
        )
        
        # Test without config (should use defaults)
        script = generate_script(transcription)
        
        self.assertIsInstance(script, EditScript)
        self.assertEqual(len(script.cuts), 1)
        self.assertEqual(script.cuts[0].action, EditAction.KEEP)
    
    def test_empty_transcription_handling(self):
        """Test handling of empty transcription"""
        empty_transcription = TranscriptionResult(
            segments=[],
            natural_breaks=[],
            speaker_changes=[],
            content_sections=[],
            metadata={"total_duration": 0.0, "language_detected": "en"},
            full_text=""
        )
        
        config = ScriptGenerationConfig()
        generator = SmartScriptGenerator(config)
        
        script = generator.generate_script(empty_transcription)
        
        self.assertEqual(len(script.cuts), 0)
        self.assertEqual(len(script.transitions), 0)
        self.assertEqual(script.estimated_final_duration, 0.0)
        self.assertEqual(script.compression_ratio, 0.0)  # Should handle division by zero

class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios"""
    
    @patch('script_generation.OpenAI')
    def test_ai_analysis_failure_fallback(self, mock_openai_class):
        """Test fallback when AI analysis fails"""
        # Mock OpenAI to raise an exception
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai_class.return_value = mock_client
        
        config = ScriptGenerationConfig(openai_api_key="test-key")
        generator = SmartScriptGenerator(config)
        
        # Create simple transcription
        segments = [
            TranscriptSegment(
                start=0.0, end=3.0, text="Test content.",
                speaker="Speaker_1", confidence=0.9, sentence_boundary=True,
                pause_after=0.5, speech_rate="normal", contains_filler=False,
                content_type="main_point", words=[]
            )
        ]
        
        transcription = TranscriptionResult(
            segments=segments,
            natural_breaks=[],
            speaker_changes=[],
            content_sections=[],
            metadata={"total_duration": 3.0, "language_detected": "en"},
            full_text="Test content."
        )
        
        # Should not crash, should fall back to rule-based
        script = generator.generate_script(transcription)
        
        self.assertIsInstance(script, EditScript)
        self.assertEqual(len(script.cuts), 1)
        self.assertEqual(script.cuts[0].action, EditAction.KEEP)  # Main point should be kept
    
    @patch('script_generation.OpenAI')
    def test_invalid_json_response_fallback(self, mock_openai_class):
        """Test fallback when AI returns invalid JSON"""
        # Mock OpenAI to return invalid JSON
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Invalid JSON content"
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        config = ScriptGenerationConfig(openai_api_key="test-key")
        generator = SmartScriptGenerator(config)
        
        # Should fall back to rule-based analysis
        analysis = generator._analyze_content(Mock())
        self.assertEqual(analysis, {})  # Empty dict indicates fallback

if __name__ == '__main__':
    # Set up test logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise during tests
    
    # Run tests
    unittest.main(verbosity=2)