"""
XML Export Module for Smart Edit - Updated for GeneratedScript

Converts generated scripts to Premiere Pro XML format for both single cam and multicam workflows.
Updated to support the new prompt-driven workflow with GeneratedScript objects.
"""

import os
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

# Updated imports for new workflow
try:
    from script_generation import GeneratedScript, ScriptSegment
    # Keep backward compatibility for old workflow
    from script_generation import EditScript, CutDecision, EditAction
    HAS_OLD_SUPPORT = True
except ImportError:
    try:
        from script_generation import GeneratedScript, ScriptSegment
        HAS_OLD_SUPPORT = False
    except ImportError:
        # Fallback definitions for development
        class GeneratedScript:
            pass
        class ScriptSegment:
            pass
        HAS_OLD_SUPPORT = False

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VideoProperties:
    """Video file properties for XML generation"""
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration: float = 0.0
    path: str = ""

class TimecodeUtils:
    """Utility functions for timecode conversion"""
    
    @staticmethod
    def time_to_frames(time_seconds: float, fps: int) -> int:
        """Convert time in seconds to frame count"""
        return int(time_seconds * fps)
    
    @staticmethod
    def frames_to_time(frames: int, fps: int) -> float:
        """Convert frame count to time in seconds"""
        return frames / fps

class PremiereXMLExporter:
    """Handles XML export for Premiere Pro - Updated for GeneratedScript"""
    
    def __init__(self, fps: int = 30, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
        self.templates_dir = Path(__file__).parent / "templates"
    
    def export_generated_script_single_cam(
        self,
        generated_script: GeneratedScript,
        video_path: str,
        output_path: str,
        sequence_name: str = "SmartEdit_Timeline"
    ) -> bool:
        """
        Export single camera generated script to Premiere XML
        
        Args:
            generated_script: Generated script from prompt-driven workflow
            video_path: Path to source video file
            output_path: Where to save the XML file
            sequence_name: Name for the Premiere sequence
            
        Returns:
            bool: Success status
        """
        try:
            logger.info(f"Exporting single cam generated script XML to: {output_path}")
            
            # Get segments that should be kept
            segments = getattr(generated_script, 'segments', [])
            selected_segments = [s for s in segments if getattr(s, 'keep', True)]
            
            if not selected_segments:
                logger.warning("No segments selected for export")
                return False
            
            # Generate clip items for selected segments
            clipitems_xml = self._generate_single_cam_clips_from_generated_script(generated_script, video_path)
            audio_clips_xml = self._generate_single_cam_audio_from_generated_script(generated_script, video_path)
            
            # Calculate final duration
            estimated_duration = getattr(generated_script, 'estimated_duration_seconds', 600)
            final_duration_frames = TimecodeUtils.time_to_frames(estimated_duration, self.fps)
            
            # Create XML content (simplified structure for now)
            xml_content = self._create_basic_single_cam_xml(
                sequence_name, final_duration_frames, clipitems_xml, audio_clips_xml
            )
            
            # Write output
            self._write_xml_file(xml_content, output_path)
            logger.info(f"✅ Single cam generated script XML exported successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export single cam generated script XML: {e}")
            return False
    
    def export_generated_script_multicam(
        self,
        generated_script: GeneratedScript,
        video_paths: List[str],  # List of video file paths
        output_path: str,
        sequence_name: str = "SmartEdit_Multicam"
    ) -> bool:
        """
        Export multicam generated script to Premiere XML
        
        Args:
            generated_script: Generated script from prompt-driven workflow
            video_paths: List of video file paths
            output_path: Where to save the XML file
            sequence_name: Name for the Premiere sequence
            
        Returns:
            bool: Success status
        """
        try:
            logger.info(f"Exporting multicam generated script XML to: {output_path}")
            
            # Get segments that should be kept
            segments = getattr(generated_script, 'segments', [])
            selected_segments = [s for s in segments if getattr(s, 'keep', True)]
            
            if not selected_segments:
                logger.warning("No segments selected for export")
                return False
            
            # Generate multicam timeline
            clipitems_xml = self._generate_multicam_clips_from_generated_script(generated_script, video_paths)
            audio_clips_xml = self._generate_multicam_audio_from_generated_script(generated_script, video_paths)
            
            # Calculate final duration
            estimated_duration = getattr(generated_script, 'estimated_duration_seconds', 600)
            final_duration_frames = TimecodeUtils.time_to_frames(estimated_duration, self.fps)
            
            # Create XML content
            xml_content = self._create_basic_multicam_xml(
                sequence_name, final_duration_frames, clipitems_xml, audio_clips_xml, len(video_paths)
            )
            
            # Write output
            self._write_xml_file(xml_content, output_path)
            logger.info(f"✅ Multicam generated script XML exported successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export multicam generated script XML: {e}")
            return False
    
    def _generate_single_cam_clips_from_generated_script(self, generated_script: GeneratedScript, video_path: str) -> str:
        """Generate clip items for single camera timeline from generated script"""
        clips_xml = ""
        timeline_position = 0
        
        video_path_abs = Path(video_path).absolute().as_posix()
        segments = getattr(generated_script, 'segments', [])
        selected_segments = [s for s in segments if getattr(s, 'keep', True)]
        
        for i, segment in enumerate(selected_segments):
            # Get segment timing
            start_time = getattr(segment, 'start_time', 0.0)
            end_time = getattr(segment, 'end_time', start_time + 5.0)  # Default 5 second duration
            
            # Calculate frame positions
            source_in = TimecodeUtils.time_to_frames(start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(end_time, self.fps)
            duration = source_out - source_in
            
            clip_id = f"clip_{i}_{uuid.uuid4().hex[:8]}"
            file_id = f"file_{i}"
            
            clips_xml += f"""
          <clipitem id="{clip_id}">
            <name>SmartEdit_Clip_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration}</end>
            <in>{source_in}</in>
            <out>{source_out}</out>
            <file id="{file_id}">
              <name>{Path(video_path).stem}</name>
              <pathurl>file://{video_path_abs}</pathurl>
              <rate>
                <timebase>{self.fps}</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
              <media>
                <video>
                  <samplecharacteristics>
                    <width>{self.width}</width>
                    <height>{self.height}</height>
                  </samplecharacteristics>
                </video>
              </media>
            </file>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _generate_single_cam_audio_from_generated_script(self, generated_script: GeneratedScript, video_path: str) -> str:
        """Generate audio clips for single camera timeline from generated script"""
        clips_xml = ""
        timeline_position = 0
        
        video_path_abs = Path(video_path).absolute().as_posix()
        segments = getattr(generated_script, 'segments', [])
        selected_segments = [s for s in segments if getattr(s, 'keep', True)]
        
        for i, segment in enumerate(selected_segments):
            # Get segment timing
            start_time = getattr(segment, 'start_time', 0.0)
            end_time = getattr(segment, 'end_time', start_time + 5.0)
            
            source_in = TimecodeUtils.time_to_frames(start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(end_time, self.fps)
            duration = source_out - source_in
            
            clip_id = f"audio_clip_{i}_{uuid.uuid4().hex[:8]}"
            
            clips_xml += f"""
          <clipitem id="{clip_id}">
            <name>SmartEdit_Audio_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration}</end>
            <in>{source_in}</in>
            <out>{source_out}</out>
            <file id="file_{i}">
              <name>{Path(video_path).stem}</name>
              <pathurl>file://{video_path_abs}</pathurl>
            </file>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _generate_multicam_clips_from_generated_script(self, generated_script: GeneratedScript, video_paths: List[str]) -> str:
        """Generate multicam clips from generated script"""
        clips_xml = ""
        timeline_position = 0
        
        segments = getattr(generated_script, 'segments', [])
        selected_segments = [s for s in segments if getattr(s, 'keep', True)]
        
        for i, segment in enumerate(selected_segments):
            # Get segment timing and video index
            start_time = getattr(segment, 'start_time', 0.0)
            end_time = getattr(segment, 'end_time', start_time + 5.0)
            video_index = getattr(segment, 'video_index', 0)
            
            # Ensure video index is valid
            if video_index >= len(video_paths):
                video_index = 0
            
            source_in = TimecodeUtils.time_to_frames(start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(end_time, self.fps)
            duration = source_out - source_in
            
            clip_id = f"multicam_clip_{i}_{uuid.uuid4().hex[:8]}"
            
            clips_xml += f"""
          <clipitem id="{clip_id}">
            <name>SmartEdit_Multicam_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration}</end>
            <in>{source_in}</in>
            <out>{source_out}</out>
            <multicam>
              <source>multicam-source</source>
              <angle>{video_index + 1}</angle>
            </multicam>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _generate_multicam_audio_from_generated_script(self, generated_script: GeneratedScript, video_paths: List[str]) -> str:
        """Generate multicam audio clips from generated script"""
        clips_xml = ""
        timeline_position = 0
        
        segments = getattr(generated_script, 'segments', [])
        selected_segments = [s for s in segments if getattr(s, 'keep', True)]
        
        for i, segment in enumerate(selected_segments):
            start_time = getattr(segment, 'start_time', 0.0)
            end_time = getattr(segment, 'end_time', start_time + 5.0)
            
            source_in = TimecodeUtils.time_to_frames(start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(end_time, self.fps)
            duration = source_out - source_in
            
            clip_id = f"multicam_audio_{i}_{uuid.uuid4().hex[:8]}"
            
            clips_xml += f"""
          <clipitem id="{clip_id}">
            <name>SmartEdit_Audio_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration}</end>
            <in>{source_in}</in>
            <out>{source_out}</out>
            <multicam>
              <source>multicam-source</source>
              <angle>1</angle>
            </multicam>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _create_basic_single_cam_xml(self, sequence_name: str, duration_frames: int, clipitems_xml: str, audio_clips_xml: str) -> str:
        """Create basic XML structure for single camera"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <project>
    <name>{sequence_name}</name>
    <children>
      <sequence id="sequence-1">
        <name>{sequence_name}</name>
        <duration>{duration_frames}</duration>
        <rate>
          <timebase>{self.fps}</timebase>
          <ntsc>FALSE</ntsc>
        </rate>
        <media>
          <video>
            <format>
              <samplecharacteristics>
                <width>{self.width}</width>
                <height>{self.height}</height>
                <rate>
                  <timebase>{self.fps}</timebase>
                  <ntsc>FALSE</ntsc>
                </rate>
              </samplecharacteristics>
            </format>
            <track>{clipitems_xml}
            </track>
          </video>
          <audio>
            <format>
              <samplecharacteristics>
                <depth>16</depth>
                <samplerate>48000</samplerate>
              </samplecharacteristics>
            </format>
            <track>{audio_clips_xml}
            </track>
          </audio>
        </media>
      </sequence>
    </children>
  </project>
</xmeml>"""
    
    def _create_basic_multicam_xml(self, sequence_name: str, duration_frames: int, clipitems_xml: str, audio_clips_xml: str, camera_count: int) -> str:
        """Create basic XML structure for multicam"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <project>
    <name>{sequence_name}</name>
    <children>
      <sequence id="sequence-1">
        <name>{sequence_name}</name>
        <duration>{duration_frames}</duration>
        <rate>
          <timebase>{self.fps}</timebase>
          <ntsc>FALSE</ntsc>
        </rate>
        <media>
          <video>
            <format>
              <samplecharacteristics>
                <width>{self.width}</width>
                <height>{self.height}</height>
                <rate>
                  <timebase>{self.fps}</timebase>
                  <ntsc>FALSE</ntsc>
                </rate>
              </samplecharacteristics>
            </format>
            <track>{clipitems_xml}
            </track>
          </video>
          <audio>
            <format>
              <samplecharacteristics>
                <depth>16</depth> 
                <samplerate>48000</samplerate>
              </samplecharacteristics>
            </format>
            <track>{audio_clips_xml}
            </track>
          </audio>
        </media>
      </sequence>
    </children>
  </project>
</xmeml>"""
    
    def _write_xml_file(self, xml_content: str, output_path: str):
        """Write XML content to file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(xml_content)
    
    # Backward compatibility methods (keep old API working)
    def export_single_cam(self, edit_script, video_path: str, output_path: str, sequence_name: str = "SmartEdit_Timeline") -> bool:
        """Backward compatibility for old EditScript format"""
        if not HAS_OLD_SUPPORT:
            logger.error("Old EditScript format not supported in this version")
            return False
            
        try:
            # Generate clip items for kept segments
            clipitems_xml = self._generate_single_cam_clips(edit_script, video_path)
            audio_clips_xml = self._generate_audio_clips(edit_script, video_path)
            
            # Calculate final duration
            final_duration_frames = TimecodeUtils.time_to_frames(
                edit_script.estimated_final_duration, self.fps
            )
            
            # Create XML content
            xml_content = self._create_basic_single_cam_xml(
                sequence_name, final_duration_frames, clipitems_xml, audio_clips_xml
            )
            
            # Write output
            self._write_xml_file(xml_content, output_path)
            logger.info(f"✅ Single cam XML exported successfully (legacy mode)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export single cam XML (legacy): {e}")
            return False
    
    def _generate_single_cam_clips(self, edit_script, video_path: str) -> str:
        """Legacy method for old EditScript format"""
        clips_xml = ""
        timeline_position = 0
        
        video_path_abs = Path(video_path).absolute().as_posix()
        
        for i, cut in enumerate(edit_script.cuts):
            if cut.action not in [EditAction.KEEP, EditAction.SPEED_UP]:
                continue
            
            # Calculate frame positions
            source_in = TimecodeUtils.time_to_frames(cut.start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(cut.end_time, self.fps)
            duration = source_out - source_in
            
            # Apply speed factor if present
            if hasattr(cut, 'speed_factor') and cut.speed_factor and cut.speed_factor != 1.0:
                duration = int(duration / cut.speed_factor)
            
            clip_id = f"clip_{i}_{uuid.uuid4().hex[:8]}"
            file_id = f"file_{i}"
            
            clips_xml += f"""
          <clipitem id="{clip_id}">
            <name>SmartEdit_Clip_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration}</end>
            <in>{source_in}</in>
            <out>{source_out}</out>
            <file id="{file_id}">
              <name>{Path(video_path).stem}</name>
              <pathurl>file://{video_path_abs}</pathurl>
              <rate>
                <timebase>{self.fps}</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
              <media>
                <video>
                  <samplecharacteristics>
                    <width>{self.width}</width>
                    <height>{self.height}</height>
                  </samplecharacteristics>
                </video>
              </media>
            </file>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _generate_audio_clips(self, edit_script, video_path: str) -> str:
        """Legacy method for old EditScript format"""
        clips_xml = ""
        timeline_position = 0
        
        video_path_abs = Path(video_path).absolute().as_posix()
        
        for i, cut in enumerate(edit_script.cuts):
            if cut.action not in [EditAction.KEEP, EditAction.SPEED_UP]:
                continue
            
            source_in = TimecodeUtils.time_to_frames(cut.start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(cut.end_time, self.fps)
            duration = source_out - source_in
            
            if hasattr(cut, 'speed_factor') and cut.speed_factor and cut.speed_factor != 1.0:
                duration = int(duration / cut.speed_factor)
            
            clip_id = f"audio_clip_{i}_{uuid.uuid4().hex[:8]}"
            
            clips_xml += f"""
          <clipitem id="{clip_id}">
            <name>SmartEdit_Audio_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration}</end>
            <in>{source_in}</in>
            <out>{source_out}</out>
            <file id="file_{i}">
              <name>{Path(video_path).stem}</name>
              <pathurl>file://{video_path_abs}</pathurl>
            </file>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml

# Updated convenience functions for new workflow
def export_generated_script_xml(
    generated_script: GeneratedScript,
    video_paths: Union[str, List[str]],  # Single path or list of paths
    output_path: str,
    fps: int = 30,
    sequence_name: str = "SmartEdit_Timeline"
) -> bool:
    """
    Export generated script to Premiere XML (works for single cam or multicam)
    
    Args:
        generated_script: Generated script from prompt-driven workflow
        video_paths: Single video path (str) or list of video paths for multicam
        output_path: Where to save the XML file
        fps: Frame rate for timeline
        sequence_name: Name for the Premiere sequence
        
    Returns:
        bool: Success status
    """
    exporter = PremiereXMLExporter(fps=fps)
    
    # Handle both single string and list of strings
    if isinstance(video_paths, str):
        video_paths = [video_paths]
    
    if len(video_paths) == 1:
        return exporter.export_generated_script_single_cam(
            generated_script, video_paths[0], output_path, sequence_name
        )
    else:
        return exporter.export_generated_script_multicam(
            generated_script, video_paths, output_path, sequence_name
        )

# Legacy convenience functions (backward compatibility)
def export_single_cam_xml(edit_script, video_path: str, output_path: str, fps: int = 30, sequence_name: str = "SmartEdit_Timeline") -> bool:
    """Export single camera edit to Premiere XML (legacy)"""
    exporter = PremiereXMLExporter(fps=fps)
    return exporter.export_single_cam(edit_script, video_path, output_path, sequence_name)

def export_multicam_xml(edit_script, video_paths: Dict[str, str], output_path: str, fps: int = 30, sequence_name: str = "SmartEdit_Multicam") -> bool:
    """Export multicam edit to Premiere XML (legacy)"""
    logger.warning("Legacy multicam export not fully implemented for old EditScript format")
    return False

# Example usage
if __name__ == "__main__":
    print("XML Export module ready! (Updated for GeneratedScript)")
    print("Available functions:")
    print("- export_generated_script_xml() - NEW: For prompt-driven workflow")
    print("- export_single_cam_xml() - Legacy: For old EditScript format")
    print("- export_multicam_xml() - Legacy: Limited support")