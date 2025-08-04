"""
XML Export Module for Smart Edit

Converts edit scripts to Premiere Pro XML format for both single cam and multicam workflows.
"""

import os
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

# Import from our modules
from script_generation import EditScript, CutDecision, EditAction

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
    """Handles XML export for Premiere Pro"""
    
    def __init__(self, fps: int = 30, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
        self.templates_dir = Path(__file__).parent / "templates"
    
    def export_single_cam(
        self,
        edit_script: EditScript,
        video_path: str,
        output_path: str,
        sequence_name: str = "SmartEdit_Timeline"
    ) -> bool:
        """
        Export single camera edit script to Premiere XML
        
        Args:
            edit_script: Edit decisions from script generation
            video_path: Path to source video file
            output_path: Where to save the XML file
            sequence_name: Name for the Premiere sequence
            
        Returns:
            bool: Success status
        """
        try:
            logger.info(f"Exporting single cam XML to: {output_path}")
            
            # Generate clip items for kept segments
            clipitems_xml = self._generate_single_cam_clips(edit_script, video_path)
            audio_clips_xml = self._generate_audio_clips(edit_script, video_path)
            
            # Calculate final duration
            final_duration_frames = TimecodeUtils.time_to_frames(
                edit_script.estimated_final_duration, self.fps
            )
            
            # Load and fill template
            xml_content = self._load_template("premiere_single.xml")
            xml_output = xml_content.format(
                sequence_name=sequence_name,
                total_duration=final_duration_frames,
                fps=self.fps,
                width=self.width,
                height=self.height,
                clipitems=clipitems_xml,
                audio_clips=audio_clips_xml
            )
            
            # Write output
            self._write_xml_file(xml_output, output_path)
            logger.info(f"✅ Single cam XML exported successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export single cam XML: {e}")
            return False
    
    def export_multicam(
        self,
        edit_script: EditScript,
        video_paths: Dict[str, str],  # {camera_id: file_path}
        output_path: str,
        sequence_name: str = "SmartEdit_Multicam"
    ) -> bool:
        """
        Export multicam edit script to Premiere XML
        
        Args:
            edit_script: Edit decisions from script generation
            video_paths: Dictionary mapping camera IDs to file paths
            output_path: Where to save the XML file
            sequence_name: Name for the Premiere sequence
            
        Returns:
            bool: Success status
        """
        try:
            logger.info(f"Exporting multicam XML to: {output_path}")
            
            # Generate source tracks for each camera
            source_tracks_xml = self._generate_multicam_source_tracks(video_paths)
            audio_tracks_xml = self._generate_multicam_audio_tracks(video_paths)
            
            # Generate edit decisions timeline
            edit_decisions_xml = self._generate_multicam_edit_decisions(edit_script, video_paths)
            audio_decisions_xml = self._generate_multicam_audio_decisions(edit_script, video_paths)
            
            # Calculate durations
            total_duration_frames = TimecodeUtils.time_to_frames(
                edit_script.original_duration, self.fps
            )
            final_duration_frames = TimecodeUtils.time_to_frames(
                edit_script.estimated_final_duration, self.fps
            )
            
            # Load and fill template
            xml_content = self._load_template("premiere_multicam.xml")
            xml_output = xml_content.format(
                sequence_name=sequence_name,
                total_duration=total_duration_frames,
                final_duration=final_duration_frames,
                fps=self.fps,
                width=self.width,
                height=self.height,
                source_tracks=source_tracks_xml,
                audio_tracks=audio_tracks_xml,
                edit_decisions=edit_decisions_xml,
                audio_decisions=audio_decisions_xml
            )
            
            # Write output
            self._write_xml_file(xml_output, output_path)
            logger.info(f"✅ Multicam XML exported successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export multicam XML: {e}")
            return False
    
    def _generate_single_cam_clips(self, edit_script: EditScript, video_path: str) -> str:
        """Generate clip items for single camera timeline"""
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
            if cut.speed_factor and cut.speed_factor != 1.0:
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
              <duration>{TimecodeUtils.time_to_frames(edit_script.original_duration, self.fps)}</duration>
              <media>
                <video>
                  <samplecharacteristics>
                    <width>{self.width}</width>
                    <height>{self.height}</height>
                  </samplecharacteristics>
                </video>
              </media>
            </file>"""
            
            # Add speed effect if needed
            if cut.speed_factor and cut.speed_factor != 1.0:
                clips_xml += f"""
            <filter>
              <effect>
                <name>Time Remap</name>
                <effectid>timeremap</effectid>
                <effecttype>motion</effecttype>
                <mediatype>video</mediatype>
                <parameter>
                  <parameterid>speed</parameterid>
                  <value>{cut.speed_factor * 100}</value>
                </parameter>
              </effect>
            </filter>"""
            
            clips_xml += """
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _generate_audio_clips(self, edit_script: EditScript, video_path: str) -> str:
        """Generate audio clips matching video clips"""
        clips_xml = ""
        timeline_position = 0
        
        video_path_abs = Path(video_path).absolute().as_posix()
        
        for i, cut in enumerate(edit_script.cuts):
            if cut.action not in [EditAction.KEEP, EditAction.SPEED_UP]:
                continue
            
            source_in = TimecodeUtils.time_to_frames(cut.start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(cut.end_time, self.fps)
            duration = source_out - source_in
            
            if cut.speed_factor and cut.speed_factor != 1.0:
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
    
    def _generate_multicam_source_tracks(self, video_paths: Dict[str, str]) -> str:
        """Generate source tracks for multicam sequence"""
        tracks_xml = ""
        
        for track_idx, (camera_id, video_path) in enumerate(video_paths.items()):
            video_path_abs = Path(video_path).absolute().as_posix()
            clip_id = f"source_{camera_id}_{uuid.uuid4().hex[:8]}"
            file_id = f"file_{camera_id}"
            
            tracks_xml += f"""
        <track>
          <clipitem id="{clip_id}">
            <name>{camera_id}</name>
            <start>0</start>
            <end>{{total_duration}}</end>
            <in>0</in>
            <out>{{total_duration}}</out>
            <file id="{file_id}">
              <name>{camera_id}</name>
              <pathurl>file://{video_path_abs}</pathurl>
              <rate>
                <timebase>{self.fps}</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
            </file>
          </clipitem>
        </track>"""
        
        return tracks_xml
    
    def _generate_multicam_audio_tracks(self, video_paths: Dict[str, str]) -> str:
        """Generate audio tracks for multicam sequence"""
        tracks_xml = ""
        
        for camera_id, video_path in video_paths.items():
            video_path_abs = Path(video_path).absolute().as_posix()
            clip_id = f"audio_source_{camera_id}_{uuid.uuid4().hex[:8]}"
            
            tracks_xml += f"""
        <track>
          <clipitem id="{clip_id}">
            <name>{camera_id}_Audio</name>
            <start>0</start>
            <end>{{total_duration}}</end>
            <in>0</in>
            <out>{{total_duration}}</out>
            <file id="file_{camera_id}">
              <name>{camera_id}</name>
              <pathurl>file://{video_path_abs}</pathurl>
            </file>
          </clipitem>
        </track>"""
        
        return tracks_xml
    
    def _generate_multicam_edit_decisions(self, edit_script: EditScript, video_paths: Dict[str, str]) -> str:
        """Generate edit decisions for multicam timeline"""
        clips_xml = ""
        timeline_position = 0
        camera_ids = list(video_paths.keys())
        
        for i, cut in enumerate(edit_script.cuts):
            if cut.action not in [EditAction.KEEP, EditAction.SPEED_UP]:
                continue
            
            # Determine which camera angle to use
            angle_id = 0  # Default to first camera
            if hasattr(cut, 'camera_id') and cut.camera_id in camera_ids:
                angle_id = camera_ids.index(cut.camera_id)
            
            source_in = TimecodeUtils.time_to_frames(cut.start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(cut.end_time, self.fps)
            duration = source_out - source_in
            
            if cut.speed_factor and cut.speed_factor != 1.0:
                duration = int(duration / cut.speed_factor)
            
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
              <angle>{angle_id + 1}</angle>
            </multicam>
          </clipitem>"""
            
            timeline_position += duration
        
        return clips_xml
    
    def _generate_multicam_audio_decisions(self, edit_script: EditScript, video_paths: Dict[str, str]) -> str:
        """Generate audio decisions for multicam timeline"""
        clips_xml = ""
        timeline_position = 0
        
        for i, cut in enumerate(edit_script.cuts):
            if cut.action not in [EditAction.KEEP, EditAction.SPEED_UP]:
                continue
            
            source_in = TimecodeUtils.time_to_frames(cut.start_time, self.fps)
            source_out = TimecodeUtils.time_to_frames(cut.end_time, self.fps)
            duration = source_out - source_in
            
            if cut.speed_factor and cut.speed_factor != 1.0:
                duration = int(duration / cut.speed_factor)
            
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
    
    def _load_template(self, template_name: str) -> str:
        """Load XML template from templates directory"""
        template_path = self.templates_dir / template_name
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def _write_xml_file(self, xml_content: str, output_path: str):
        """Write XML content to file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(xml_content)

# Convenience functions
def export_single_cam_xml(
    edit_script: EditScript,
    video_path: str,
    output_path: str,
    fps: int = 30,
    sequence_name: str = "SmartEdit_Timeline"
) -> bool:
    """Export single camera edit to Premiere XML"""
    exporter = PremiereXMLExporter(fps=fps)
    return exporter.export_single_cam(edit_script, video_path, output_path, sequence_name)

def export_multicam_xml(
    edit_script: EditScript,
    video_paths: Dict[str, str],
    output_path: str,
    fps: int = 30,
    sequence_name: str = "SmartEdit_Multicam"
) -> bool:
    """Export multicam edit to Premiere XML"""
    exporter = PremiereXMLExporter(fps=fps)
    return exporter.export_multicam(edit_script, video_paths, output_path, sequence_name)

# Example usage
if __name__ == "__main__":
    # This would typically be used with real edit scripts
    print("XML Export module ready!")
    print("Available functions:")
    print("- export_single_cam_xml()")
    print("- export_multicam_xml()")