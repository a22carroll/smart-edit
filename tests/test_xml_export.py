"""
Test suite for xml_export.py module

Tests XML export functionality for both single cam and multicam workflows.
"""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch, mock_open
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

from xml_export import (
    PremiereXMLExporter,
    TimecodeUtils,
    VideoProperties,
    export_single_cam_xml,
    export_multicam_xml
)

from script_generation import (
    EditScript,
    CutDecision,
    TransitionPoint,
    EditAction,
    ConfidenceLevel
)

class TestTimecodeUtils(unittest.TestCase):
    """Test TimecodeUtils class"""
    
    def test_time_to_frames_30fps(self):
        """Test time to frames conversion at 30fps"""
        self.assertEqual(TimecodeUtils.time_to_frames(1.0, 30), 30)
        self.assertEqual(TimecodeUtils.time_to_frames(2.5, 30), 75)
        self.assertEqual(TimecodeUtils.time_to_frames(0.0, 30), 0)
        self.assertEqual(TimecodeUtils.time_to_frames(10.333, 30), 309)  # Truncates
    
    def test_time_to_frames_24fps(self):
        """Test time to frames conversion at 24fps"""
        self.assertEqual(TimecodeUtils.time_to_frames(1.0, 24), 24)
        self.assertEqual(TimecodeUtils.time_to_frames(2.5, 24), 60)
    
    def test_frames_to_time(self):
        """Test frames to time conversion"""
        self.assertAlmostEqual(TimecodeUtils.frames_to_time(30, 30), 1.0, places=3)
        self.assertAlmostEqual(TimecodeUtils.frames_to_time(75, 30), 2.5, places=3)
        self.assertAlmostEqual(TimecodeUtils.frames_to_time(24, 24), 1.0, places=3)

class TestVideoProperties(unittest.TestCase):
    """Test VideoProperties dataclass"""
    
    def test_default_properties(self):
        """Test default video properties"""
        props = VideoProperties()
        
        self.assertEqual(props.width, 1920)
        self.assertEqual(props.height, 1080)
        self.assertEqual(props.fps, 30)
        self.assertEqual(props.duration, 0.0)
        self.assertEqual(props.path, "")
    
    def test_custom_properties(self):
        """Test custom video properties"""
        props = VideoProperties(
            width=3840,
            height=2160,
            fps=60,
            duration=120.5,
            path="/path/to/video.mp4"
        )
        
        self.assertEqual(props.width, 3840)
        self.assertEqual(props.height, 2160)
        self.assertEqual(props.fps, 60)
        self.assertEqual(props.duration, 120.5)
        self.assertEqual(props.path, "/path/to/video.mp4")

class TestPremiereXMLExporter(unittest.TestCase):
    """Test PremiereXMLExporter class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.exporter = PremiereXMLExporter(fps=30, width=1920, height=1080)
        
        # Create mock edit script
        self.mock_cuts = [
            CutDecision(
                segment_id=0,
                start_time=0.0,
                end_time=3.0,
                original_text="Hello, welcome to the test.",
                action=EditAction.KEEP,
                reason="Important content",
                confidence=ConfidenceLevel.HIGH
            ),
            CutDecision(
                segment_id=1,
                start_time=3.5,
                end_time=7.0,
                original_text="Um, this is filler content.",
                action=EditAction.REMOVE,
                reason="Contains filler",
                confidence=ConfidenceLevel.HIGH
            ),
            CutDecision(
                segment_id=2,
                start_time=7.5,
                end_time=10.0,
                original_text="This is slow speech.",
                action=EditAction.SPEED_UP,
                reason="Slow speech rate",
                confidence=ConfidenceLevel.MEDIUM,
                speed_factor=1.5
            )
        ]
        
        self.mock_transitions = [
            TransitionPoint(
                from_segment_id=0,
                to_segment_id=2,
                transition_type="cut",
                duration=0.0,
                reason="Natural sentence boundary"
            )
        ]
        
        self.mock_edit_script = EditScript(
            cuts=self.mock_cuts,
            transitions=self.mock_transitions,
            estimated_final_duration=4.67,  # 3.0 + (2.5/1.5)
            original_duration=10.0,
            compression_ratio=0.467,
            metadata={"test": "data"}
        )
    
    def test_exporter_initialization(self):
        """Test exporter initialization"""
        exporter = PremiereXMLExporter(fps=24, width=3840, height=2160)
        
        self.assertEqual(exporter.fps, 24)
        self.assertEqual(exporter.width, 3840)
        self.assertEqual(exporter.height, 2160)
        self.assertTrue(exporter.templates_dir.name == "templates")
    
    @patch('xml_export.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_load_template_success(self, mock_file, mock_exists):
        """Test successful template loading"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = "<xml>test template</xml>"
        
        template_content = self.exporter._load_template("test_template.xml")
        
        self.assertEqual(template_content, "<xml>test template</xml>")
        mock_file.assert_called_once()
    
    @patch('xml_export.Path.exists')
    def test_load_template_not_found(self, mock_exists):
        """Test template loading when file doesn't exist"""
        mock_exists.return_value = False
        
        with self.assertRaises(FileNotFoundError):
            self.exporter._load_template("nonexistent.xml")
    
    def test_generate_single_cam_clips(self):
        """Test single cam clip generation"""
        video_path = "/path/to/video.mp4"
        clips_xml = self.exporter._generate_single_cam_clips(self.mock_edit_script, video_path)
        
        # Should have 2 clips (KEEP and SPEED_UP actions only)
        self.assertEqual(clips_xml.count('<clipitem'), 2)
        self.assertEqual(clips_xml.count('</clipitem>'), 2)
        
        # Check for video path in clips (Windows format: file://C:/path/to/video.mp4)
        self.assertIn("file://", clips_xml)
        self.assertIn("video.mp4", clips_xml)
        
        # Check for speed effect (should only appear once for the SPEED_UP clip)
        self.assertIn("Time Remap", clips_xml)
        self.assertIn("150", clips_xml)  # 1.5 * 100 = 150%
    
    def test_generate_audio_clips(self):
        """Test audio clip generation"""
        video_path = "/path/to/video.mp4"
        audio_xml = self.exporter._generate_audio_clips(self.mock_edit_script, video_path)
        
        # Should have 2 audio clips matching video clips (KEEP and SPEED_UP actions)
        self.assertEqual(audio_xml.count('<clipitem'), 2)
        self.assertEqual(audio_xml.count('</clipitem>'), 2)
        
        # Check for audio clip naming (clips are numbered based on segment_id, not sequentially)
        self.assertIn("SmartEdit_Audio_1", audio_xml)  # First kept clip (segment 0)
        self.assertIn("SmartEdit_Audio_3", audio_xml)  # Second kept clip (segment 2)
    
    def test_generate_multicam_source_tracks(self):
        """Test multicam source track generation"""
        video_paths = {
            "Camera_1": "/path/to/cam1.mp4",
            "Camera_2": "/path/to/cam2.mp4"
        }
        
        tracks_xml = self.exporter._generate_multicam_source_tracks(video_paths)
        
        # Should have 2 tracks
        self.assertEqual(tracks_xml.count('<track>'), 2)
        self.assertEqual(tracks_xml.count('</track>'), 2)
        
        # Check for camera names and paths (Windows format)
        self.assertIn("Camera_1", tracks_xml)
        self.assertIn("Camera_2", tracks_xml)
        self.assertIn("file://", tracks_xml)
        self.assertIn("cam1.mp4", tracks_xml)
        self.assertIn("cam2.mp4", tracks_xml)
    
    def test_generate_multicam_edit_decisions(self):
        """Test multicam edit decision generation"""
        video_paths = {
            "Camera_1": "/path/to/cam1.mp4",
            "Camera_2": "/path/to/cam2.mp4"
        }
        
        decisions_xml = self.exporter._generate_multicam_edit_decisions(
            self.mock_edit_script, video_paths
        )
        
        # Should have 2 clips (KEEP and SPEED_UP actions)
        self.assertEqual(decisions_xml.count('<clipitem'), 2)
        self.assertEqual(decisions_xml.count('</clipitem>'), 2)
        
        # Check for multicam references
        self.assertIn("<multicam>", decisions_xml)
        self.assertIn("<source>multicam-source</source>", decisions_xml)
        self.assertIn("<angle>1</angle>", decisions_xml)  # Default to first camera
    
    @patch('xml_export.PremiereXMLExporter._load_template')
    @patch('xml_export.PremiereXMLExporter._write_xml_file')
    def test_export_single_cam_success(self, mock_write, mock_load_template):
        """Test successful single cam export"""
        mock_load_template.return_value = """
        <sequence>
            <name>{sequence_name}</name>
            <duration>{total_duration}</duration>
            <clipitems>{clipitems}</clipitems>
            <audio>{audio_clips}</audio>
        </sequence>
        """
        
        video_path = "/path/to/video.mp4"
        output_path = "/output/test.xml"
        
        result = self.exporter.export_single_cam(
            self.mock_edit_script, video_path, output_path, "Test_Sequence"
        )
        
        self.assertTrue(result)
        mock_load_template.assert_called_once_with("premiere_single.xml")
        mock_write.assert_called_once()
        
        # Check that write was called with formatted XML
        written_xml = mock_write.call_args[0][0]
        self.assertIn("Test_Sequence", written_xml)
        # Duration should be around 140 frames (4.67 * 30 ≈ 140)
        self.assertTrue(any(str(d) in written_xml for d in [140, 141, 139]))
    
    @patch('xml_export.PremiereXMLExporter._load_template')
    @patch('xml_export.PremiereXMLExporter._write_xml_file')
    def test_export_multicam_success(self, mock_write, mock_load_template):
        """Test successful multicam export"""
        mock_load_template.return_value = """
        <sequence>
            <name>{sequence_name}</name>
            <total_duration>{total_duration}</total_duration>
            <final_duration>{final_duration}</final_duration>
            <source_tracks>{source_tracks}</source_tracks>
            <edit_decisions>{edit_decisions}</edit_decisions>
        </sequence>
        """
        
        video_paths = {
            "Camera_1": "/path/to/cam1.mp4",
            "Camera_2": "/path/to/cam2.mp4"
        }
        output_path = "/output/multicam.xml"
        
        result = self.exporter.export_multicam(
            self.mock_edit_script, video_paths, output_path, "Multicam_Sequence"
        )
        
        self.assertTrue(result)
        mock_load_template.assert_called_once_with("premiere_multicam.xml")
        mock_write.assert_called_once()
        
        # Check that write was called with formatted XML
        written_xml = mock_write.call_args[0][0]
        self.assertIn("Multicam_Sequence", written_xml)
        self.assertIn("300", written_xml)  # Total duration in frames (10.0 * 30)
        # Final duration should be around 140 frames (4.67 * 30 ≈ 140)
        self.assertTrue(any(str(d) in written_xml for d in [140, 141, 139]))
    
    @patch('xml_export.PremiereXMLExporter._load_template')
    def test_export_template_not_found(self, mock_load_template):
        """Test export when template file is missing"""
        mock_load_template.side_effect = FileNotFoundError("Template not found")
        
        result = self.exporter.export_single_cam(
            self.mock_edit_script, "/video.mp4", "/output.xml"
        )
        
        self.assertFalse(result)
    
    def test_write_xml_file_creates_directory(self):
        """Test that XML file writing creates output directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "subdir", "test.xml")
            xml_content = "<xml>test content</xml>"
            
            self.exporter._write_xml_file(xml_content, output_path)
            
            # Check that file was created
            self.assertTrue(os.path.exists(output_path))
            
            # Check content
            with open(output_path, 'r') as f:
                content = f.read()
            self.assertEqual(content, xml_content)

class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_cuts = [
            CutDecision(
                segment_id=0,
                start_time=0.0,
                end_time=3.0,
                original_text="Test content",
                action=EditAction.KEEP,
                reason="Important",
                confidence=ConfidenceLevel.HIGH
            )
        ]
        
        self.mock_edit_script = EditScript(
            cuts=self.mock_cuts,
            transitions=[],
            estimated_final_duration=3.0,
            original_duration=5.0,
            compression_ratio=0.6,
            metadata={}
        )
    
    @patch('xml_export.PremiereXMLExporter.export_single_cam')
    def test_export_single_cam_xml_convenience(self, mock_export):
        """Test single cam convenience function"""
        mock_export.return_value = True
        
        result = export_single_cam_xml(
            self.mock_edit_script,
            "/video.mp4",
            "/output.xml",
            fps=24,
            sequence_name="Test"
        )
        
        self.assertTrue(result)
        # Check that exporter was created with correct fps and export was called
        mock_export.assert_called_once_with(
            self.mock_edit_script, "/video.mp4", "/output.xml", "Test"
        )
    
    @patch('xml_export.PremiereXMLExporter.export_multicam')
    def test_export_multicam_xml_convenience(self, mock_export):
        """Test multicam convenience function"""
        mock_export.return_value = True
        
        video_paths = {"cam1": "/cam1.mp4", "cam2": "/cam2.mp4"}
        
        result = export_multicam_xml(
            self.mock_edit_script,
            video_paths,
            "/output.xml",
            fps=60,
            sequence_name="MultiTest"
        )
        
        self.assertTrue(result)
        # Check that exporter was created with correct fps and export was called
        mock_export.assert_called_once_with(
            self.mock_edit_script, video_paths, "/output.xml", "MultiTest"
        )

class TestXMLValidation(unittest.TestCase):
    """Test XML output validation"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.exporter = PremiereXMLExporter()
        
        # Create minimal edit script
        self.edit_script = EditScript(
            cuts=[
                CutDecision(
                    segment_id=0,
                    start_time=0.0,
                    end_time=5.0,
                    original_text="Test",
                    action=EditAction.KEEP,
                    reason="Test",
                    confidence=ConfidenceLevel.HIGH
                )
            ],
            transitions=[],
            estimated_final_duration=5.0,
            original_duration=5.0,
            compression_ratio=1.0,
            metadata={}
        )
    
    def test_single_cam_xml_structure(self):
        """Test that generated single cam XML has valid structure"""
        clips_xml = self.exporter._generate_single_cam_clips(self.edit_script, "/test.mp4")
        
        # Should be parseable as XML fragment
        # Wrap in root element for parsing
        wrapped_xml = f"<root>{clips_xml}</root>"
        
        try:
            root = ET.fromstring(wrapped_xml)
            clipitems = root.findall('.//clipitem')
            self.assertEqual(len(clipitems), 1)
            
            # Check required elements exist
            clipitem = clipitems[0]
            self.assertIsNotNone(clipitem.find('start'))
            self.assertIsNotNone(clipitem.find('end'))
            self.assertIsNotNone(clipitem.find('in'))
            self.assertIsNotNone(clipitem.find('out'))
            self.assertIsNotNone(clipitem.find('file'))
            
        except ET.ParseError as e:
            # Print the XML for debugging if it fails to parse
            print(f"Failed to parse XML: {wrapped_xml}")
            self.fail(f"Generated XML is not valid: {e}")
    
    def test_multicam_xml_structure(self):
        """Test that generated multicam XML has valid structure"""
        video_paths = {"cam1": "/cam1.mp4"}
        decisions_xml = self.exporter._generate_multicam_edit_decisions(
            self.edit_script, video_paths
        )
        
        # Should be parseable as XML fragment
        wrapped_xml = f"<root>{decisions_xml}</root>"
        
        try:
            root = ET.fromstring(wrapped_xml)
            clipitems = root.findall('.//clipitem')
            self.assertEqual(len(clipitems), 1)
            
            # Check multicam specific elements
            clipitem = clipitems[0]
            multicam = clipitem.find('multicam')
            self.assertIsNotNone(multicam)
            self.assertIsNotNone(multicam.find('source'))
            self.assertIsNotNone(multicam.find('angle'))
            
        except ET.ParseError as e:
            # Print the XML for debugging if it fails to parse
            print(f"Failed to parse XML: {wrapped_xml}")
            self.fail(f"Generated multicam XML is not valid: {e}")

class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.exporter = PremiereXMLExporter()
    
    def test_empty_edit_script(self):
        """Test handling of empty edit script"""
        empty_script = EditScript(
            cuts=[],
            transitions=[],
            estimated_final_duration=0.0,
            original_duration=0.0,
            compression_ratio=0.0,
            metadata={}
        )
        
        clips_xml = self.exporter._generate_single_cam_clips(empty_script, "/test.mp4")
        
        # Should handle empty gracefully
        self.assertEqual(clips_xml.strip(), "")
    
    def test_only_removed_cuts(self):
        """Test script with only REMOVE actions"""
        remove_only_script = EditScript(
            cuts=[
                CutDecision(
                    segment_id=0,
                    start_time=0.0,
                    end_time=5.0,
                    original_text="Remove this",
                    action=EditAction.REMOVE,
                    reason="Filler",
                    confidence=ConfidenceLevel.HIGH
                )
            ],
            transitions=[],
            estimated_final_duration=0.0,
            original_duration=5.0,
            compression_ratio=0.0,
            metadata={}
        )
        
        clips_xml = self.exporter._generate_single_cam_clips(remove_only_script, "/test.mp4")
        
        # Should produce no clips
        self.assertEqual(clips_xml.strip(), "")
    
    def test_extreme_speed_factor(self):
        """Test handling of extreme speed factors"""
        speed_script = EditScript(
            cuts=[
                CutDecision(
                    segment_id=0,
                    start_time=0.0,
                    end_time=10.0,
                    original_text="Very slow",
                    action=EditAction.SPEED_UP,
                    reason="Extremely slow",
                    confidence=ConfidenceLevel.HIGH,
                    speed_factor=5.0  # 5x speed
                )
            ],
            transitions=[],
            estimated_final_duration=2.0,
            original_duration=10.0,
            compression_ratio=0.2,
            metadata={}
        )
        
        clips_xml = self.exporter._generate_single_cam_clips(speed_script, "/test.mp4")
        
        # Should handle extreme speed factor
        self.assertIn("500", clips_xml)  # 5.0 * 100 = 500%
        self.assertIn("Time Remap", clips_xml)

if __name__ == '__main__':
    # Set up test logging
    import logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise during tests
    
    # Run tests
    unittest.main(verbosity=2)