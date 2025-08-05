"""
XML Export Module - Fixed Bugs and Enhanced Premiere Pro Compatibility

Fixes:
- Corrected XML structure to match Premiere format
- Fixed masterclip references and file structure
- Consistent element naming (<name> vs <n>)
- Proper audio track configuration
- Better error handling
"""

import os
import logging
from pathlib import Path
from typing import List, Union
import uuid

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
    """Enhanced XML exporter with better Premiere Pro compatibility"""
    
    def __init__(self, fps: int = 24, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
        # Use TRUE for NTSC even with 24fps (matches Premiere behavior)
        self.ntsc = "TRUE" if fps in [24, 30, 60] else "FALSE"
    
    def export_script(self, script: GeneratedScript, video_paths: Union[str, List[str]], 
                     output_path: str, sequence_name: str = "SmartEdit_Timeline") -> bool:
        """
        Export script to XML - automatically handles single cam vs multicam
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
        """Generate single camera XML with proper Premiere compatibility"""
        
        # Prepare video file info
        video_file = Path(video_path)
        if not video_file.exists():
            logger.warning(f"Video file not found: {video_path}")
        
        file_uri = video_file.absolute().as_uri()
        file_name = video_file.name  # Use full filename with extension
        file_stem = video_file.stem   # Use stem for clip names
        
        # Generate unique IDs
        sequence_uuid = str(uuid.uuid4())
        
        # Calculate total source duration (assuming it's longer than our edit)
        max_source_time = 0
        for segment in segments:
            end_time = getattr(segment, 'end_time', 0.0)
            max_source_time = max(max_source_time, end_time)
        
        source_duration_frames = int((max_source_time + 300) * self.fps)  # Add 5 min buffer
        
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
            
            # Video clip with proper structure
            video_clips += f"""
          <clipitem id="clipitem-{i+1}">
            <masterclipid>masterclip-1</masterclipid>
            <name>Segment_{i+1}</name>
            <enabled>TRUE</enabled>
            <duration>{duration_frames}</duration>
            <rate>
              <timebase>{self.fps}</timebase>
              <ntsc>{self.ntsc}</ntsc>
            </rate>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration_frames}</end>
            <in>{source_in_frames}</in>
            <out>{source_out_frames}</out>
            <file id="file-1"/>
            <sourcetrack>
              <mediatype>video</mediatype>
              <trackindex>1</trackindex>
            </sourcetrack>
            <logginginfo>
              <description></description>
              <scene></scene>
              <shottake></shottake>
              <lognote></lognote>
              <good></good>
              <originalvideofilename></originalvideofilename>
              <originalaudiofilename></originalaudiofilename>
            </logginginfo>
            <colorinfo>
              <lut></lut>
              <lut1></lut1>
              <asc_sop></asc_sop>
              <asc_sat></asc_sat>
              <lut2></lut2>
            </colorinfo>
          </clipitem>"""
            
            # Audio clip with proper channel routing
            audio_clips += f"""
          <clipitem id="audioclip-{i+1}">
            <masterclipid>masterclip-1</masterclipid>
            <name>Audio_{i+1}</name>
            <enabled>TRUE</enabled>
            <duration>{duration_frames}</duration>
            <rate>
              <timebase>{self.fps}</timebase>
              <ntsc>{self.ntsc}</ntsc>
            </rate>
            <start>{timeline_position}</start>
            <end>{timeline_position + duration_frames}</end>
            <in>{source_in_frames}</in>
            <out>{source_out_frames}</out>
            <file id="file-1"/>
            <sourcetrack>
              <mediatype>audio</mediatype>
              <trackindex>1</trackindex>
            </sourcetrack>
            <logginginfo>
              <description></description>
              <scene></scene>
              <shottake></shottake>
              <lognote></lognote>
              <good></good>
              <originalvideofilename></originalvideofilename>
              <originalaudiofilename></originalaudiofilename>
            </logginginfo>
          </clipitem>"""
            
            timeline_position += duration_frames
        
        # Total sequence duration
        total_duration = timeline_position
        
        # Create the complete XML structure
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <project>
    <name>{sequence_name}_Project</name>
    <children>
      <clip id="masterclip-1">
        <name>{file_stem}</name>
        <duration>{source_duration_frames}</duration>
        <rate>
          <timebase>{self.fps}</timebase>
          <ntsc>{self.ntsc}</ntsc>
        </rate>
        <media>
          <video>
            <track>
              <clipitem id="masterclip-video-1">
                <name>{file_stem}</name>
                <enabled>TRUE</enabled>
                <duration>{source_duration_frames}</duration>
                <rate>
                  <timebase>{self.fps}</timebase>
                  <ntsc>{self.ntsc}</ntsc>
                </rate>
                <start>0</start>
                <end>{source_duration_frames}</end>
                <in>0</in>
                <out>{source_duration_frames}</out>
                <file id="file-1">
                  <name>{file_name}</name>
                  <pathurl>{file_uri}</pathurl>
                  <rate>
                    <timebase>{self.fps}</timebase>
                    <ntsc>{self.ntsc}</ntsc>
                  </rate>
                  <duration>{source_duration_frames}</duration>
                  <timecode>
                    <rate>
                      <timebase>{self.fps}</timebase>
                      <ntsc>{self.ntsc}</ntsc>
                    </rate>
                    <string>00:00:00:00</string>
                    <frame>0</frame>
                    <displayformat>NDF</displayformat>
                  </timecode>
                  <media>
                    <video>
                      <samplecharacteristics>
                        <rate>
                          <timebase>{self.fps}</timebase>
                          <ntsc>{self.ntsc}</ntsc>
                        </rate>
                        <width>{self.width}</width>
                        <height>{self.height}</height>
                        <anamorphic>FALSE</anamorphic>
                        <pixelaspectratio>square</pixelaspectratio>
                        <fielddominance>none</fielddominance>
                      </samplecharacteristics>
                    </video>
                    <audio>
                      <samplecharacteristics>
                        <depth>16</depth>
                        <samplerate>48000</samplerate>
                      </samplecharacteristics>
                      <channelcount>2</channelcount>
                    </audio>
                  </media>
                </file>
                <logginginfo>
                  <description></description>
                  <scene></scene>
                  <shottake></shottake>
                  <lognote></lognote>
                  <good></good>
                  <originalvideofilename></originalvideofilename>
                  <originalaudiofilename></originalaudiofilename>
                </logginginfo>
                <colorinfo>
                  <lut></lut>
                  <lut1></lut1>
                  <asc_sop></asc_sop>
                  <asc_sat></asc_sat>
                  <lut2></lut2>
                </colorinfo>
              </clipitem>
            </track>
          </video>
          <audio>
            <track>
              <clipitem id="masterclip-audio-1">
                <name>{file_stem}</name>
                <enabled>TRUE</enabled>
                <duration>{source_duration_frames}</duration>
                <rate>
                  <timebase>{self.fps}</timebase>
                  <ntsc>{self.ntsc}</ntsc>
                </rate>
                <start>0</start>
                <end>{source_duration_frames}</end>
                <in>0</in>
                <out>{source_duration_frames}</out>
                <file id="file-1"/>
                <sourcetrack>
                  <mediatype>audio</mediatype>
                  <trackindex>1</trackindex>
                </sourcetrack>
                <logginginfo>
                  <description></description>
                  <scene></scene>
                  <shottake></shottake>
                  <lognote></lognote>
                  <good></good>
                  <originalvideofilename></originalvideofilename>
                  <originalaudiofilename></originalaudiofilename>
                </logginginfo>
              </clipitem>
            </track>
          </audio>
        </media>
      </clip>
      <sequence id="sequence-1">
        <uuid>{sequence_uuid}</uuid>
        <duration>{total_duration}</duration>
        <rate>
          <timebase>{self.fps}</timebase>
          <ntsc>{self.ntsc}</ntsc>
        </rate>
        <name>{sequence_name}</name>
        <media>
          <video>
            <format>
              <samplecharacteristics>
                <rate>
                  <timebase>{self.fps}</timebase>
                  <ntsc>{self.ntsc}</ntsc>
                </rate>
                <width>{self.width}</width>
                <height>{self.height}</height>
                <anamorphic>FALSE</anamorphic>
                <pixelaspectratio>square</pixelaspectratio>
                <fielddominance>none</fielddominance>
                <colordepth>24</colordepth>
              </samplecharacteristics>
            </format>
            <track>
              <enabled>TRUE</enabled>
              <locked>FALSE</locked>{video_clips}
            </track>
          </video>
          <audio>
            <numOutputChannels>2</numOutputChannels>
            <format>
              <samplecharacteristics>
                <depth>16</depth>
                <samplerate>48000</samplerate>
              </samplecharacteristics>
            </format>
            <outputs>
              <group>
                <index>1</index>
                <numchannels>1</numchannels>
                <downmix>0</downmix>
                <channel>
                  <index>1</index>
                </channel>
              </group>
              <group>
                <index>2</index>
                <numchannels>1</numchannels>
                <downmix>0</downmix>
                <channel>
                  <index>2</index>
                </channel>
              </group>
            </outputs>
            <track>
              <enabled>TRUE</enabled>
              <locked>FALSE</locked>
              <outputchannelindex>1</outputchannelindex>{audio_clips}
            </track>
          </audio>
        </media>
        <timecode>
          <rate>
            <timebase>{self.fps}</timebase>
            <ntsc>{self.ntsc}</ntsc>
          </rate>
          <string>00:00:00:00</string>
          <frame>0</frame>
          <displayformat>NDF</displayformat>
        </timecode>
        <logginginfo>
          <description></description>
          <scene></scene>
          <shottake></shottake>
          <lognote></lognote>
          <good></good>
          <originalvideofilename></originalvideofilename>
          <originalaudiofilename></originalaudiofilename>
        </logginginfo>
      </sequence>
    </children>
  </project>
</xmeml>"""
    
    def _create_multicam_xml(self, segments: List[ScriptSegment], video_paths: List[str], sequence_name: str) -> str:
        """Generate multicam XML - simplified implementation"""
        
        logger.info("Creating multicam XML with simplified structure")
        
        # For now, create a basic multicam structure
        # Full multicam would require much more complex XML
        
        try:
            # Calculate the full duration we need to cover
            max_duration = 0
            for segment in segments:
                end_time = getattr(segment, 'end_time', 0.0)
                max_duration = max(max_duration, end_time)
            
            # Ensure we have a minimum duration
            if max_duration <= 0:
                max_duration = 600  # Default 10 minutes if no segments
            
            total_duration_frames = int(max_duration * self.fps)
            sequence_uuid = str(uuid.uuid4())
            
            # Create file definitions for all cameras
            file_definitions = ""
            for i, video_path in enumerate(video_paths):
                try:
                    video_file = Path(video_path)
                    if not video_file.exists():
                        logger.warning(f"Video file not found: {video_path}")
                        continue
                        
                    file_uri = video_file.absolute().as_uri()
                    file_name = video_file.name
                    
                    file_definitions += f"""
      <file id="file-{i+1}">
        <name>{file_name}</name>
        <pathurl>{file_uri}</pathurl>
        <rate>
          <timebase>{self.fps}</timebase>
          <ntsc>{self.ntsc}</ntsc>
        </rate>
        <duration>{total_duration_frames}</duration>
        <timecode>
          <rate>
            <timebase>{self.fps}</timebase>
            <ntsc>{self.ntsc}</ntsc>
          </rate>
          <string>00:00:00:00</string>
          <frame>0</frame>
          <displayformat>NDF</displayformat>
        </timecode>
        <media>
          <video>
            <samplecharacteristics>
              <rate>
                <timebase>{self.fps}</timebase>
                <ntsc>{self.ntsc}</ntsc>
              </rate>
              <width>{self.width}</width>
              <height>{self.height}</height>
              <anamorphic>FALSE</anamorphic>
              <pixelaspectratio>square</pixelaspectratio>
              <fielddominance>none</fielddominance>
            </samplecharacteristics>
          </video>
          <audio>
            <samplecharacteristics>
              <depth>16</depth>
              <samplerate>48000</samplerate>
            </samplecharacteristics>
            <channelcount>2</channelcount>
          </audio>
        </media>
      </file>"""
                except Exception as e:
                    logger.error(f"Error processing video file {video_path}: {e}")
                    continue
            
            # Simple multicam sequence - just puts first camera on timeline
            # Real multicam would need multicam source clips, angle switching, etc.
            video_clips = f"""
          <clipitem id="multicam-clip-1">
            <name>Multicam_Main</name>
            <enabled>TRUE</enabled>
            <duration>{total_duration_frames}</duration>
            <rate>
              <timebase>{self.fps}</timebase>
              <ntsc>{self.ntsc}</ntsc>
            </rate>
            <start>0</start>
            <end>{total_duration_frames}</end>
            <in>0</in>
            <out>{total_duration_frames}</out>
            <file id="file-1"/>
            <sourcetrack>
              <mediatype>video</mediatype>
              <trackindex>1</trackindex>
            </sourcetrack>
            <logginginfo>
              <description></description>
              <scene></scene>
              <shottake></shottake>
              <lognote></lognote>
              <good></good>
              <originalvideofilename></originalvideofilename>
              <originalaudiofilename></originalaudiofilename>
            </logginginfo>
            <colorinfo>
              <lut></lut>
              <lut1></lut1>
              <asc_sop></asc_sop>
              <asc_sat></asc_sat>
              <lut2></lut2>
            </colorinfo>
          </clipitem>"""
            
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <project>
    <name>{sequence_name}_Multicam_Project</name>
    <children>{file_definitions}
      <sequence id="sequence-1">
        <uuid>{sequence_uuid}</uuid>
        <name>{sequence_name}_Multicam_Timeline</name>
        <duration>{total_duration_frames}</duration>
        <rate>
          <timebase>{self.fps}</timebase>
          <ntsc>{self.ntsc}</ntsc>
        </rate>
        <media>
          <video>
            <format>
              <samplecharacteristics>
                <rate>
                  <timebase>{self.fps}</timebase>
                  <ntsc>{self.ntsc}</ntsc>
                </rate>
                <width>{self.width}</width>
                <height>{self.height}</height>
                <anamorphic>FALSE</anamorphic>
                <pixelaspectratio>square</pixelaspectratio>
                <fielddominance>none</fielddominance>
                <colordepth>24</colordepth>
              </samplecharacteristics>
            </format>
            <track>
              <enabled>TRUE</enabled>
              <locked>FALSE</locked>{video_clips}
            </track>
          </video>
          <audio>
            <numOutputChannels>2</numOutputChannels>
            <format>
              <samplecharacteristics>
                <depth>16</depth>
                <samplerate>48000</samplerate>
              </samplecharacteristics>
            </format>
            <outputs>
              <group>
                <index>1</index>
                <numchannels>1</numchannels>
                <downmix>0</downmix>
                <channel>
                  <index>1</index>
                </channel>
              </group>
              <group>
                <index>2</index>
                <numchannels>1</numchannels>
                <downmix>0</downmix>
                <channel>
                  <index>2</index>
                </channel>
              </group>
            </outputs>
            <track>
              <enabled>TRUE</enabled>
              <locked>FALSE</locked>
              <outputchannelindex>1</outputchannelindex>
            </track>
          </audio>
        </media>
        <timecode>
          <rate>
            <timebase>{self.fps}</timebase>
            <ntsc>{self.ntsc}</ntsc>
          </rate>
          <string>00:00:00:00</string>
          <frame>0</frame>
          <displayformat>NDF</displayformat>
        </timecode>
        <logginginfo>
          <description></description>
          <scene></scene>
          <shottake></shottake>
          <lognote></lognote>
          <good></good>
          <originalvideofilename></originalvideofilename>
          <originalaudiofilename></originalaudiofilename>
        </logginginfo>
      </sequence>
    </children>
  </project>
</xmeml>"""
        
        except Exception as e:
            logger.error(f"Error creating multicam XML: {e}")
            # Fall back to single cam
            return self._create_single_cam_xml(segments, video_paths[0], sequence_name)
    
    def _save_xml(self, xml_content: str, output_path: str):
        """Save XML to file"""
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(xml_content)
        except Exception as e:
            logger.error(f"Failed to save XML file: {e}")
            raise

# Simple convenience function
def export_script_to_xml(script: GeneratedScript, video_paths: Union[str, List[str]], 
                        output_path: str, fps: int = 24, sequence_name: str = "SmartEdit") -> bool:
    """
    Simple function to export script to XML with better Premiere compatibility
    """
    exporter = XMLExporter(fps=fps)
    return exporter.export_script(script, video_paths, output_path, sequence_name)

# Example usage
if __name__ == "__main__":
    print("Enhanced XML Export Module - Fixed Bugs!")
    print("Key improvements:")
    print("- Fixed XML structure and nesting")
    print("- Consistent element naming")
    print("- Proper masterclip references")
    print("- Better error handling")
    print("- Corrected file paths and durations")