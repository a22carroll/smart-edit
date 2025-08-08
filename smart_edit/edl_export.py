"""
EDL Export Module - Edit Decision List Generation

Converts generated scripts to EDL format for universal compatibility
with video editing systems. EDL is a simple text-based format that
describes edit decisions with timecodes and source references.
"""

import os
import logging
from pathlib import Path
from typing import List, Union, Dict, Optional
from datetime import timedelta

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

class EDLExporter:
    """EDL exporter for generated scripts"""
    
    def __init__(self, fps: int = 24):
        """
        Initialize EDL exporter
        
        Args:
            fps: Frame rate for timecode calculations (default 24)
        """
        self.fps = fps
    
    def export_script(self, script: GeneratedScript, video_paths: Union[str, List[str]], 
                     output_path: str, sequence_name: str = "SmartEdit_Timeline",
                     custom_clip_names: Optional[Dict[int, str]] = None) -> bool:
        """
        Export script to EDL format
        
        Args:
            script: Generated script with segments
            video_paths: List of video file paths (or single path)
            output_path: Output EDL file path
            sequence_name: Name for the sequence
            custom_clip_names: Optional dict mapping video_index to custom clip names
        
        Returns:
            bool: True if successful, False otherwise
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
            
            logger.info(f"Exporting {len(segments)} segments to EDL format")
            
            # Generate EDL content
            edl_content = self._create_edl(segments, video_paths, sequence_name, custom_clip_names)
            
            # Save to file
            self._save_edl(edl_content, output_path)
            logger.info(f"✅ EDL exported to: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ EDL export failed: {e}")
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
                
                # Validate timing - reduced minimum duration to 1 frame
                min_duration = 1.0 / self.fps  # 1 frame duration
                if end > start and (end - start) >= min_duration:
                    segments.append(seg)
                else:
                    logger.warning(f"Skipping segment with invalid timing: {start}s to {end}s")
        
        if not segments and script.segments:
            logger.warning("No segments marked to keep, using all segments")
            segments = script.segments
        
        return segments
    
    def _create_edl(self, segments: List[ScriptSegment], video_paths: List[str], 
                   sequence_name: str, custom_clip_names: Optional[Dict[int, str]] = None) -> str:
        """Create EDL content from segments"""
        
        # EDL Header
        edl_lines = [
            f"TITLE: {sequence_name}",
            f"FCM: NON-DROP FRAME",
        ]
        
        # Track timeline position
        timeline_position = 0.0
        
        # Generate edit entries
        for i, segment in enumerate(segments):
            edit_number = f"{i+1:03d}"  # 001, 002, etc.
            
            # Get segment timing
            source_start = getattr(segment, 'start_time', 0.0)
            source_end = getattr(segment, 'end_time', source_start + 1.0)
            duration = source_end - source_start
            
            # Get video index for source reference
            video_index = getattr(segment, 'video_index', 0)
            
            # Ensure video index is within range
            if video_index >= len(video_paths):
                logger.warning(f"Video index {video_index} out of range, using 0")
                video_index = 0
            
            # Get source file name and make it EDL-compliant
            source_reel = self._sanitize_reel_name(Path(video_paths[video_index]).stem)
            
            # Calculate timeline positions
            timeline_start = timeline_position
            timeline_end = timeline_position + duration
            
            # Convert to timecode
            source_tc_in = self._seconds_to_timecode(source_start)
            source_tc_out = self._seconds_to_timecode(source_end)
            timeline_tc_in = self._seconds_to_timecode(timeline_start)
            timeline_tc_out = self._seconds_to_timecode(timeline_end)
            
            # Get clip name - use custom name if available, otherwise original filename
            if custom_clip_names and video_index in custom_clip_names:
                clip_name = custom_clip_names[video_index]
            else:
                clip_name = Path(video_paths[video_index]).name
            
            # EDL edit entry format matching your sample:
            # Uses AA/V for combined audio/video track like professional EDLs
            edl_lines.extend([
                f"{edit_number}  {source_reel:<8} AA/V  C        {source_tc_in} {source_tc_out} {timeline_tc_in} {timeline_tc_out} ",
                f"* FROM CLIP NAME: {clip_name}",
            ])
            
            # Add segment content as comment if available
            content = getattr(segment, 'content', '')
            if content:
                # Clean content for EDL comment (single line, max ~60 chars)
                clean_content = content.replace('\n', ' ').replace('\r', ' ')
                if len(clean_content) > 60:
                    clean_content = clean_content[:57] + "..."
                edl_lines.append(f"* SEGMENT: {clean_content}")
            
            # Update timeline position
            timeline_position = timeline_end
        
        return "\n".join(edl_lines)
    
    def _sanitize_reel_name(self, filename: str) -> str:
        """Sanitize filename for EDL reel name (max 8 chars, alphanumeric)"""
        
        # Remove file extension and convert to uppercase
        name = filename.upper()
        
        # Replace invalid characters with underscores
        sanitized = ""
        for char in name:
            if char.isalnum():
                sanitized += char
            else:
                sanitized += "_"
        
        # Truncate to 8 characters maximum
        if len(sanitized) > 8:
            sanitized = sanitized[:8]
        
        # Ensure we have at least one character
        if not sanitized:
            sanitized = "CLIP001"
        
        return sanitized
    
    def _seconds_to_timecode(self, seconds: float) -> str:
        """Convert seconds to timecode format (HH:MM:SS:FF)"""
        
        # Handle negative values - clamp to zero
        if seconds < 0:
            return "00:00:00:00"
        
        # Calculate hours, minutes, seconds, frames
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        # Use round() for more accurate frame calculation
        frames = round((seconds % 1) * self.fps)
        
        # Handle frame overflow (can happen with rounding)
        if frames >= self.fps:
            frames = 0
            secs += 1
            if secs >= 60:
                secs = 0
                minutes += 1
                if minutes >= 60:
                    minutes = 0
                    hours += 1
        
        # Ensure values are within valid ranges
        hours = min(hours, 23)
        minutes = min(minutes, 59)
        secs = min(secs, 59)
        frames = min(frames, self.fps - 1)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    
    def _save_edl(self, edl_content: str, output_path: str):
        """Save EDL content to file"""
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(edl_content)
                
        except Exception as e:
            logger.error(f"Failed to save EDL file: {e}")
            raise

class CMX3600EDLExporter(EDLExporter):
    """CMX 3600 standard EDL exporter with enhanced compatibility"""
    
    def _create_edl(self, segments: List[ScriptSegment], video_paths: List[str], 
                   sequence_name: str, custom_clip_names: Optional[Dict[int, str]] = None) -> str:
        """Create CMX 3600 compliant EDL matching professional standards"""
        
        # CMX 3600 Header
        edl_lines = [
            f"TITLE: {sequence_name}",
            f"FCM: NON-DROP FRAME",
        ]
        
        timeline_position = 0.0
        
        for i, segment in enumerate(segments):
            edit_number = f"{i+1:03d}"
            
            # Get timing
            source_start = getattr(segment, 'start_time', 0.0)
            source_end = getattr(segment, 'end_time', source_start + 1.0)
            duration = source_end - source_start
            
            # Get source
            video_index = getattr(segment, 'video_index', 0)
            if video_index >= len(video_paths):
                video_index = 0
            
            # Create proper reel name (2 chars like AX, BX, etc.)
            if len(video_paths) == 1:
                source_reel = "AX"  # Single source like your sample
            else:
                # Multiple sources: AX, BX, CX, etc.
                reel_letter = chr(65 + video_index)  # A, B, C, etc.
                source_reel = f"{reel_letter}X"
            
            # Timeline positions
            timeline_start = timeline_position
            timeline_end = timeline_position + duration
            
            # Timecodes
            source_tc_in = self._seconds_to_timecode(source_start)
            source_tc_out = self._seconds_to_timecode(source_end)
            timeline_tc_in = self._seconds_to_timecode(timeline_start)
            timeline_tc_out = self._seconds_to_timecode(timeline_end)
            
            # Get clip name - use custom name if available, otherwise original filename
            if custom_clip_names and video_index in custom_clip_names:
                clip_name = custom_clip_names[video_index]
            else:
                clip_name = Path(video_paths[video_index]).name
            
            # CMX 3600 format with AA/V track (combined audio/video)
            edl_lines.extend([
                f"{edit_number}  {source_reel:<8} AA/V  C        {source_tc_in} {source_tc_out} {timeline_tc_in} {timeline_tc_out} ",
                f"* FROM CLIP NAME: {clip_name}",
            ])
            
            timeline_position = timeline_end
        
        return "\n".join(edl_lines)

# Convenience function
def export_script_to_edl(script: GeneratedScript, video_paths: Union[str, List[str]], 
                        output_path: str, fps: int = 24, sequence_name: str = "SmartEdit",
                        edl_format: str = "standard", custom_clip_names: Optional[Dict[int, str]] = None) -> bool:
    """
    Export script to EDL format
    
    Args:
        script: Generated script with segments
        video_paths: List of video file paths (or single path)
        output_path: Output EDL file path
        fps: Frame rate for timecode calculations (default 24)
        sequence_name: Name for the sequence
        edl_format: EDL format variant ("standard" or "cmx3600")
        custom_clip_names: Optional dict mapping video_index to custom clip names
    
    Returns:
        bool: True if successful, False otherwise
    """
    if edl_format.lower() == "cmx3600":
        exporter = CMX3600EDLExporter(fps=fps)
    else:
        exporter = EDLExporter(fps=fps)
    
    return exporter.export_script(script, video_paths, output_path, sequence_name, custom_clip_names)

# Example usage and format documentation
if __name__ == "__main__":
    print("EDL Export Module")
    print("=" * 50)
    print()
    print("EDL (Edit Decision List) Format:")
    print("- Simple text-based format")
    print("- Universal compatibility across editing systems") 
    print("- Contains edit decisions with timecodes")
    print("- Much simpler than XML project files")
    print()
    print("Example EDL entry:")
    print("001  AX       AA/V  C        01:00:10:15 01:00:15:20 01:00:00:00 01:00:05:05 ")
    print("* FROM CLIP NAME: my_video_file.mp4")
    print("* SEGMENT: Introduction to the main topic...")
    print()
    print("Format breakdown:")
    print("- 001: Edit number")
    print("- AX: Source reel name (professional 2-char format)")
    print("- AA/V: Combined audio/video track") 
    print("- C: Cut transition")
    print("- Timecodes: Source IN, Source OUT, Timeline IN, Timeline OUT")
    print("- Comments start with * and include FROM CLIP NAME")
    print()
    print("Key improvements based on professional sample:")
    print("- Uses AA/V track designation (combined audio/video)")
    print("- Professional 2-character reel names (AX, BX, etc.)")
    print("- Proper spacing and trailing spaces")
    print("- No empty lines between edits (compact format)")
    print("- Simplified comment structure")