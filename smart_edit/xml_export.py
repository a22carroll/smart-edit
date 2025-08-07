"""
XML Export Module - Enhanced with Video Groups Support

Fixes:
- Added video_groups parameter support
- Smart multicam handling based on groups
- Corrected XML structure to match Premiere format
- Fixed masterclip references and file structure
- Consistent element naming (<name> vs <n>)
- Proper audio track configuration
- Better error handling
"""

import os
import logging
from pathlib import Path
from typing import List, Union, Dict, Optional
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
    """Enhanced XML exporter with video groups support and better Premiere Pro compatibility"""
    
    def __init__(self, fps: int = 24, width: int = 1920, height: int = 1080):
        self.fps = fps
        self.width = width
        self.height = height
        # Use TRUE for NTSC even with 24fps (matches Premiere behavior)
        self.ntsc = "TRUE" if fps in [24, 30, 60] else "FALSE"
    
    def export_script(self, script: GeneratedScript, video_paths: Union[str, List[str]], 
                     output_path: str, sequence_name: str = "SmartEdit_Timeline", 
                     video_groups: Optional[Dict[str, List[str]]] = None) -> bool:
        """
        Export script to XML with video groups support
        
        Args:
            script: Generated script with segments
            video_paths: List of video file paths
            output_path: Output XML file path
            sequence_name: Name for the sequence
            video_groups: Dictionary mapping group names to video paths
                         e.g., {"Single": [path1], "Multicam A": [path2, path3]}
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
            
            # If no groups provided, create default grouping
            if video_groups is None:
                if len(video_paths) == 1:
                    video_groups = {"Single": video_paths}
                else:
                    video_groups = {"Multicam A": video_paths}
                    
            # Log grouping information
            for group_name, paths in video_groups.items():
                logger.info(f"Group '{group_name}': {len(paths)} video(s)")
            
            # Generate XML based on grouping
            xml_content = self._create_grouped_xml(segments, video_groups, sequence_name)
            
            # Save to file
            self._save_xml(xml_content, output_path)
            logger.info(f"✅ XML exported to: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ XML export failed: {e}")
            return False
    
    def _create_grouped_xml(self, segments: List[ScriptSegment], video_groups: Dict[str, List[str]], 
                           sequence_name: str) -> str:
        """Create XML with proper group handling"""
        
        # Determine the export strategy
        multicam_groups = {k: v for k, v in video_groups.items() if len(v) > 1}
        single_videos = []
        for group_name, paths in video_groups.items():
            if len(paths) == 1:
                single_videos.extend(paths)
        
        if len(multicam_groups) == 1 and not single_videos:
            # Pure multicam case
            group_name, video_paths = next(iter(multicam_groups.items()))
            logger.info(f"Creating pure multicam XML for group: {group_name}")
            return self._create_multicam_xml(segments, video_paths, f"{sequence_name}_{group_name}")
            
        elif len(multicam_groups) == 0 and len(single_videos) == 1:
            # Pure single cam case
            logger.info("Creating single cam XML")
            return self._create_single_cam_xml(segments, single_videos[0], sequence_name)
            
        else:
            # Mixed case - create combined timeline
            logger.info("Creating mixed timeline with multiple groups")
            return self._create_mixed_xml(segments, video_groups, sequence_name)
    
    def _create_mixed_xml(self, segments: List[ScriptSegment], video_groups: Dict[str, List[str]], 
                         sequence_name: str) -> str:
        """Create XML for mixed single and multicam clips"""
        
        # For now, flatten all videos into one timeline
        # This is a simplified approach - full implementation would create 
        # multicam source clips for grouped videos
        all_videos = []
        for group_name, paths in video_groups.items():
            all_videos.extend(paths)
        
        if len(all_videos) == 1:
            return self._create_single_cam_xml(segments, all_videos[0], sequence_name)
        else:
            # Create a basic multicam structure with all videos
            return self._create_multicam_xml(segments, all_videos, sequence_name)
    
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
      """Generate multicam XML with cuts based on script segments"""
    
      logger.info(f"Creating multicam XML with {len(video_paths)} cameras and {len(segments)} cut segments")
      
      try:
          # Calculate source duration
          max_source_time = 0
          for segment in segments:
              end_time = getattr(segment, 'end_time', 0.0)
              max_source_time = max(max_source_time, end_time)
          
          source_duration_frames = int((max_source_time + 300) * self.fps)  # Add 5 min buffer
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
        </file>"""
              except Exception as e:
                  logger.error(f"Error processing video file {video_path}: {e}")
                  continue
          
          # Create video tracks for each camera with segmented clips
          video_tracks = ""
          for i in range(len(video_paths)):
              # Generate segmented clips for this camera
              camera_clips = ""
              timeline_position = 0
              
              for seg_index, segment in enumerate(segments):
                  start_time = getattr(segment, 'start_time', 0.0)
                  end_time = getattr(segment, 'end_time', start_time + 1.0)
                  
                  # Convert to frames
                  source_in_frames = int(start_time * self.fps)
                  source_out_frames = int(end_time * self.fps)
                  duration_frames = source_out_frames - source_in_frames
                  
                  if duration_frames <= 0:
                      continue
                  
                  camera_clips += f"""
                <clipitem id="cam{i+1}-segment-{seg_index+1}">
                  <name>Camera_{i+1}_Segment_{seg_index+1}</name>
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
                  <file id="file-{i+1}"/>
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
                  
                  timeline_position += duration_frames
              
              video_tracks += f"""
              <track>
                <enabled>TRUE</enabled>
                <locked>FALSE</locked>{camera_clips}
              </track>"""
          
          # Create audio track with segmented clips (using first camera)
          audio_clips = ""
          timeline_position = 0
          
          for seg_index, segment in enumerate(segments):
              start_time = getattr(segment, 'start_time', 0.0)
              end_time = getattr(segment, 'end_time', start_time + 1.0)
              
              source_in_frames = int(start_time * self.fps)
              source_out_frames = int(end_time * self.fps)
              duration_frames = source_out_frames - source_in_frames
              
              if duration_frames <= 0:
                  continue
              
              audio_clips += f"""
                <clipitem id="audio-segment-{seg_index+1}">
                  <name>Audio_Segment_{seg_index+1}</name>
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
          
          # Calculate total timeline duration
          total_timeline_frames = timeline_position
          
          return f"""<?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE xmeml>
  <xmeml version="4">
    <project>
      <name>{sequence_name}_Multicam_Project</name>
      <children>{file_definitions}
        <sequence id="sequence-1">
          <uuid>{sequence_uuid}</uuid>
          <name>{sequence_name}_Multicam_Timeline</name>
          <duration>{total_timeline_frames}</duration>
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
              </format>{video_tracks}
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

# Enhanced convenience function with video groups support
def export_script_to_xml(script: GeneratedScript, video_paths: Union[str, List[str]], 
                        output_path: str, fps: int = 24, sequence_name: str = "SmartEdit",
                        video_groups: Optional[Dict[str, List[str]]] = None) -> bool:
    """
    Export script to XML with video groups support and better Premiere compatibility
    
    Args:
        script: Generated script with segments
        video_paths: List of video file paths
        output_path: Output XML file path
        fps: Frame rate (default 24)
        sequence_name: Name for the sequence
        video_groups: Dictionary mapping group names to video paths
                     e.g., {"Single": [path1], "Multicam A": [path2, path3]}
    """
    exporter = XMLExporter(fps=fps)
    return exporter.export_script(script, video_paths, output_path, sequence_name, video_groups)

# Example usage
if __name__ == "__main__":
    print("Enhanced XML Export Module - Now with Video Groups Support!")
    print("Key improvements:")
    print("- Added video_groups parameter support")
    print("- Smart multicam handling based on groups")
    print("- Fixed XML structure and nesting")
    print("- Consistent element naming")
    print("- Proper masterclip references")
    print("- Better error handling")
    print("- Corrected file paths and durations")