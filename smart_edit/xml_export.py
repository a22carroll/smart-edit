"""
XML Export Module - Simplified and Fixed

Converts generated scripts to Premiere Pro XML format.
No external templates needed - generates XML directly.
"""

import os
import logging
from pathlib import Path
from typing import List, Union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple import handling
try:
    from script_generation import GeneratedScript, ScriptSegment
except ImportError:
    try:
        from .script_generation import GeneratedScript, ScriptSegment
    except ImportError:
        # Fallback for development
        logger.warning("Could not import GeneratedScript - using fallbacks")
        class GeneratedScript:
            pass
        class ScriptSegment:
            pass

class XMLExporter:
    """Simple, reliable XML exporter for Premiere Pro"""
    
    def __init__(self, fps: int = 30, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
    
    def export_script(self, script: GeneratedScript, video_paths: Union[str, List[str]], 
                     output_path: str, sequence_name: str = "SmartEdit_Timeline") -> bool:
        """
        Export script to XML - automatically handles single cam vs multicam
        
        Args:
            script: Generated script with segments
            video_paths: Single video path (str) or list for multicam
            output_path: Where to save the XML file
            sequence_name: Name for the timeline
        """
        try:
            # Convert single path to list
            if isinstance(video_paths, str):
                video_paths = [video_paths]
            
            # Validate inputs
            if not video_paths:
                raise ValueError("No video paths provided")
            
            # Get segments to export
            segments = self._get_valid_segments(script)
            if not segments:
                raise ValueError("No valid segments to export")
            
            logger.info(f"Exporting {len(segments)} segments from {len(video_paths)} video(s)")
            
            # Generate XML based on camera count
            if len(video_paths) == 1:
                xml_content = self._create_single_cam_xml(segments, video_paths[0], sequence_name)
            else:
                xml_content = self._create_multicam_xml(segments, video_paths, sequence_name)
            
            # Save to file
            self._save_xml(xml_content, output_path)
            logger.info(f"✅ XML exported to: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ XML export failed: {e}")
            return False
    
    def _get_valid_segments(self, script: GeneratedScript) -> List[ScriptSegment]:
        """Extract valid segments from script"""
        
        if not hasattr(script, 'segments'):
            logger.error("Script has no segments attribute")
            return []
        
        # Get segments marked to keep
        segments = []
        for seg in script.segments:
            if getattr(seg, 'keep', True):  # Default to True if no keep attribute
                start = getattr(seg, 'start_time', 0.0)
                end = getattr(seg, 'end_time', 0.0)
                
                # Validate timing
                if end > start and (end - start) > 0.1:  # At least 0.1 second
                    segments.append(seg)
                else:
                    logger.warning(f"Skipping segment with invalid timing: {start}s to {end}s")
        
        if not segments and script.segments:
            logger.warning("No segments marked to keep, using all segments")
            segments = script.segments
        
        return segments
    
    def _create_single_cam_xml(self, segments: List[ScriptSegment], video_path: str, sequence_name: str) -> str:
        """Generate single camera XML"""
        
        # Prepare video file info
        video_file = Path(video_path)
        if not video_file.exists():
            logger.warning(f"Video file not found: {video_path}")
        
        file_uri = video_file.absolute().as_uri()
        file_name = video_file.stem
        
        # Generate clips
        video_clips = ""
        audio_clips = ""
        timeline_position = 0
        
        for i, segment in enumerate(segments):
            start_time = getattr(segment, 'start_time', 0.0)
            end_time = getattr(segment, 'end_time', start_time + 1.0)
            
            # Convert to frames
            source_in_frames = int(start_time * self.fps)
            source_out_frames = int(end_time * self.fps)
            duration_frames = source_out_frames - source_in_frames
            
            if duration_frames <= 0:
                continue
            
            # Video clip
            video_clips += f"""
          <clipitem id="clip-{i+1}">
            <name>Segment_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration_frames}</end>
            <in>{source_in_frames}</in>
            <out>{source_out_frames}</out>
            <file id="file-1">
              <name>{file_name}</name>
              <pathurl>{file_uri}</pathurl>
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
                <audio>
                  <samplecharacteristics>
                    <depth>16</depth>
                    <samplerate>48000</samplerate>
                  </samplecharacteristics>
                </audio>
              </media>
            </file>
          </clipitem>"""
            
            # Audio clip (same timing)
            audio_clips += f"""
          <clipitem id="audio-{i+1}">
            <name>Audio_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration_frames}</end>
            <in>{source_in_frames}</in>
            <out>{source_out_frames}</out>
            <file id="file-1"/>
          </clipitem>"""
            
            timeline_position += duration_frames
        
        # Total sequence duration
        total_duration = timeline_position
        
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <project>
    <name>{sequence_name}_Project</name>
    <children>
      <sequence id="sequence-1">
        <name>{sequence_name}</name>
        <duration>{total_duration}</duration>
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
            <track>{video_clips}
            </track>
          </video>
          <audio>
            <format>
              <samplecharacteristics>
                <depth>16</depth>
                <samplerate>48000</samplerate>
              </samplecharacteristics>
            </format>
            <track>{audio_clips}
            </track>
          </audio>
        </media>
      </sequence>
    </children>
  </project>
</xmeml>"""
    
    def _create_multicam_xml(self, segments: List[ScriptSegment], video_paths: List[str], sequence_name: str) -> str:
        """Generate multicam XML"""
        
        # For multicam, we need to reference which camera each segment uses
        video_clips = ""
        audio_clips = ""
        timeline_position = 0
        
        for i, segment in enumerate(segments):
            start_time = getattr(segment, 'start_time', 0.0)
            end_time = getattr(segment, 'end_time', start_time + 1.0)
            video_index = getattr(segment, 'video_index', 0)
            
            # Ensure video index is valid
            if video_index >= len(video_paths):
                logger.warning(f"Invalid video index {video_index}, using 0")
                video_index = 0
            
            # Convert to frames
            source_in_frames = int(start_time * self.fps)
            source_out_frames = int(end_time * self.fps)
            duration_frames = source_out_frames - source_in_frames
            
            if duration_frames <= 0:
                continue
            
            # Get video file info
            video_file = Path(video_paths[video_index])
            file_uri = video_file.absolute().as_uri()
            file_name = video_file.stem
            
            # Video clip with camera angle
            video_clips += f"""
          <clipitem id="clip-{i+1}">
            <name>Cam{video_index+1}_Segment_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration_frames}</end>
            <in>{source_in_frames}</in>
            <out>{source_out_frames}</out>
            <file id="file-{video_index+1}">
              <name>{file_name}</name>
              <pathurl>{file_uri}</pathurl>
              <rate>
                <timebase>{self.fps}</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
            </file>
          </clipitem>"""
            
            # Audio clip (typically from camera 1)
            audio_clips += f"""
          <clipitem id="audio-{i+1}">
            <name>Audio_{i+1}</name>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration_frames}</end>
            <in>{source_in_frames}</in>
            <out>{source_out_frames}</out>
            <file id="file-1"/>
          </clipitem>"""
            
            timeline_position += duration_frames
        
        total_duration = timeline_position
        
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <project>
    <name>{sequence_name}_Multicam</name>
    <children>
      <sequence id="sequence-1">
        <name>{sequence_name}</name>
        <duration>{total_duration}</duration>
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
            <track>{video_clips}
            </track>
          </video>
          <audio>
            <format>
              <samplecharacteristics>
                <depth>16</depth>
                <samplerate>48000</samplerate>
              </samplecharacteristics>
            </format>
            <track>{audio_clips}
            </track>
          </audio>
        </media>
      </sequence>
    </children>
  </project>
</xmeml>"""
    
    def _save_xml(self, xml_content: str, output_path: str):
        """Save XML to file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xml_content)

# Simple convenience function
def export_script_to_xml(script: GeneratedScript, video_paths: Union[str, List[str]], 
                        output_path: str, fps: int = 30, sequence_name: str = "SmartEdit") -> bool:
    """
    Simple function to export script to XML
    
    Args:
        script: Generated script object
        video_paths: Video file path(s) - string for single cam, list for multicam  
        output_path: Where to save the XML file
        fps: Frame rate (default 30)
        sequence_name: Timeline name in Premiere
    
    Returns:
        bool: Success/failure
    """
    exporter = XMLExporter(fps=fps)
    return exporter.export_script(script, video_paths, output_path, sequence_name)

# Example usage
if __name__ == "__main__":
    print("XML Export Module - No Templates Needed!")
    print("Usage:")
    print("success = export_script_to_xml(script, 'video.mp4', 'output.xml')")
    print("success = export_script_to_xml(script, ['cam1.mp4', 'cam2.mp4'], 'multicam.xml')")