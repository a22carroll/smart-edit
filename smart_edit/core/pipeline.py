"""
Smart Edit Core Pipeline - Updated for EDL Export

Orchestrates the complete video processing workflow from raw videos to final EDL export.
Supports user prompt-driven script generation workflow.
"""

import os
import sys
import time
import logging
import traceback
from typing import List, Dict, Optional, Callable, Any
from pathlib import Path

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import core models - Updated for new workflow
try:
    from core.models import (
        SmartEditProject, VideoFile, ProcessingStage, ProcessingResult,
        ExportOptions, ExportFormat, ProjectSettings, create_project_from_videos
    )
except ImportError:
    # Fallback definitions for development
    from enum import Enum
    from dataclasses import dataclass
    
    class ProcessingStage(Enum):
        CREATED = "created"
        TRANSCRIBING = "transcribing"
        TRANSCRIBED = "transcribed"
        READY_FOR_SCRIPT = "ready_for_script"
        SCRIPT_GENERATED = "script_generated"
        READY_FOR_REVIEW = "ready_for_review"
        READY_FOR_EXPORT = "ready_for_export"
        EXPORTING = "exporting"
        COMPLETED = "completed"
        FAILED = "failed"
    
    @dataclass
    class ProcessingResult:
        success: bool
        stage: ProcessingStage
        message: str
        data: Any = None
        processing_time: float = 0.0
        
        @classmethod
        def success_result(cls, stage, message, data=None, processing_time=0.0):
            return cls(True, stage, message, data, processing_time)
        
        @classmethod
        def error_result(cls, stage, error):
            return cls(False, stage, str(error), None, 0.0)

# Import processing modules - Updated imports
try:
    from transcription import transcribe_video, TranscriptionConfig, TranscriptionResult
    from script_generation import GeneratedScript, generate_script_from_prompt
    from edl_export import export_script_to_edl
except ImportError as e:
    print(f"Warning: Import error - {e}")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartEditPipeline:
    """Main processing pipeline for Smart Edit - EDL Export Version"""
    
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        """
        Initialize the pipeline
        
        Args:
            progress_callback: Optional callback for progress updates (message, percent)
        """
        self.progress_callback = progress_callback
        self.current_project: Optional[Dict] = None  # Simplified project structure
    
    def process_transcription_only(
        self, 
        project_name: str, 
        video_paths: List[str]
    ) -> ProcessingResult:
        """
        Process only transcription step - Updated workflow
        
        Args:
            project_name: Name for the project
            video_paths: List of video file paths
            
        Returns:
            ProcessingResult with transcription data
        """
        logger.info(f"Starting transcription for project: {project_name}")
        
        try:
            # Initialize project data
            self.current_project = {
                "name": project_name,
                "video_paths": video_paths,
                "transcription_results": [],
                "generated_script": None
            }
            
            self._update_progress("Starting transcription...", 10.0, ProcessingStage.TRANSCRIBING)
            start_time = time.time()
            
            # Process each video individually
            transcription_results = []
            total_videos = len(video_paths)
            
            for i, video_path in enumerate(video_paths):
                video_name = os.path.basename(video_path)
                progress = 10.0 + (i / total_videos) * 70.0  # 10% to 80%
                
                self._update_progress(f"Transcribing {i+1}/{total_videos}: {video_name}", 
                                    progress, ProcessingStage.TRANSCRIBING)
                
                # Transcribe individual video
                logger.info(f"Transcribing video {i+1}/{total_videos}: {video_name}")
                
                # Use base model for faster processing (user can change in config)
                config = TranscriptionConfig(
                    model_size="base",  # Faster for development
                    accuracy_mode=True,
                    enable_word_timestamps=True
                )
                
                result = transcribe_video(video_path, config)
                transcription_results.append(result)
                
                duration_mins = result.metadata.get('total_duration', 0) / 60
                logger.info(f"Completed {video_name}: {duration_mins:.1f}min, {len(result.segments)} segments")
            
            # Store results
            self.current_project["transcription_results"] = transcription_results
            
            processing_time = time.time() - start_time
            total_duration = sum(t.metadata.get('total_duration', 0) for t in transcription_results)
            total_segments = sum(len(t.segments) for t in transcription_results)
            
            self._update_progress("Transcription complete", 90.0, ProcessingStage.TRANSCRIBED)
            
            logger.info(f"Transcription completed: {total_segments} segments, "
                       f"{total_duration/60:.1f}min total, {processing_time:.2f}s processing time")
            
            return ProcessingResult.success_result(
                ProcessingStage.TRANSCRIBED,
                f"Transcribed {total_videos} video(s) successfully",
                transcription_results,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            logger.error(traceback.format_exc())
            self._update_progress(f"Transcription failed: {str(e)}", 0.0, ProcessingStage.FAILED)
            return ProcessingResult.error_result(ProcessingStage.TRANSCRIBING, e)
    
    def generate_script_from_prompt(
        self,
        user_prompt: str,
        target_duration_minutes: int = 10,
        transcription_results: Optional[List] = None
    ) -> ProcessingResult:
        """
        Generate script from user prompt - New workflow step
        
        Args:
            user_prompt: User's instructions for the video
            target_duration_minutes: Target duration in minutes
            transcription_results: Optional transcription results (uses current project if None)
            
        Returns:
            ProcessingResult with generated script
        """
        if transcription_results:
            results = transcription_results
        elif self.current_project and self.current_project.get("transcription_results"):
            results = self.current_project["transcription_results"] 
        else:
            return ProcessingResult.error_result(
                ProcessingStage.FAILED,
                ValueError("No transcription results available")
            )
        
        try:
            self._update_progress("Generating script from prompt...", 20.0, ProcessingStage.READY_FOR_SCRIPT)
            start_time = time.time()
            
            logger.info(f"Generating script with prompt: {user_prompt[:100]}...")
            logger.info(f"Target duration: {target_duration_minutes} minutes")
            
            # Import the updated script generation function
            from script_generation import generate_script_from_prompt
            
            # Generate script based on user prompt
            generated_script = generate_script_from_prompt(
                transcriptions=results,
                user_prompt=user_prompt,
                target_duration_minutes=target_duration_minutes
            )
            
            # Store in project
            if self.current_project:
                self.current_project["generated_script"] = generated_script
            
            processing_time = time.time() - start_time
            
            # Get script metrics
            segments_count = len(getattr(generated_script, 'segments', []))
            estimated_duration = getattr(generated_script, 'estimated_duration_seconds', 0) / 60
            
            self._update_progress("Script generated successfully", 80.0, ProcessingStage.SCRIPT_GENERATED)
            
            logger.info(f"Script generation completed: {segments_count} segments, "
                       f"{estimated_duration:.1f}min estimated duration, {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.SCRIPT_GENERATED,
                f"Generated script with {segments_count} segments",
                generated_script,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            logger.error(traceback.format_exc())
            self._update_progress(f"Script generation failed: {str(e)}", 0.0, ProcessingStage.FAILED)
            return ProcessingResult.error_result(ProcessingStage.READY_FOR_SCRIPT, e)
    
    def export_generated_script(
        self,
        output_path: str,
        video_paths: List[str],
        generated_script: Optional[GeneratedScript] = None,
        export_format: str = "edl"
    ) -> ProcessingResult:
        """
        Export generated script to specified format
        
        Args:
            output_path: Output file path
            video_paths: List of video file paths (required for EDL export)
            generated_script: Script to export (uses current project if None)
            export_format: Export format ("edl", "text", "json")
            
        Returns:
            ProcessingResult with export status
        """
        if generated_script:
            script = generated_script
        elif self.current_project and self.current_project.get("generated_script"):
            script = self.current_project["generated_script"]
        else:
            return ProcessingResult.error_result(
                ProcessingStage.FAILED,
                ValueError("No generated script available")
            )
        
        try:
            self._update_progress("Exporting script...", 90.0, ProcessingStage.EXPORTING)
            start_time = time.time()
            
            logger.info(f"Exporting script to: {output_path}")
            logger.info(f"Export format: {export_format}")
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            
            if export_format == "text":
                self._export_text_script(script, output_path)
                
            elif export_format == "json":
                self._export_json_script(script, output_path)
                
            elif export_format == "edl":
                self._export_edl_script(script, output_path, video_paths)
                
            else:
                raise ValueError(f"Unsupported export format: {export_format}")
            
            processing_time = time.time() - start_time
            
            self._update_progress("Export complete", 100.0, ProcessingStage.COMPLETED)
            
            logger.info(f"Export completed: {output_path} in {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.COMPLETED,
                f"Exported script to {output_path}",
                output_path,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            logger.error(traceback.format_exc())
            self._update_progress(f"Export failed: {str(e)}", 0.0, ProcessingStage.FAILED)
            return ProcessingResult.error_result(ProcessingStage.EXPORTING, e)
    
    def _export_edl_script(self, script: GeneratedScript, output_path: str, video_paths: List[str]):
        """Export script as EDL"""
        sequence_name = Path(output_path).stem
        
        success = export_script_to_edl(
            script=script,
            video_paths=video_paths,
            output_path=output_path,
            sequence_name=sequence_name
        )
        
        if not success:
            raise RuntimeError("EDL export failed - check EDL export module logs for details")
    
    def _export_text_script(self, script: GeneratedScript, output_path: str):
        """Export script as readable text"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("Smart Edit Generated Script\n")
            f.write("=" * 50 + "\n\n")
            
            # Script metadata
            f.write(f"Title: {getattr(script, 'title', 'Untitled')}\n")
            f.write(f"Target Duration: {getattr(script, 'target_duration_minutes', 'N/A')} minutes\n")
            f.write(f"Estimated Duration: {getattr(script, 'estimated_duration_seconds', 0)/60:.1f} minutes\n")
            f.write(f"User Prompt: {getattr(script, 'user_prompt', 'None')}\n\n")
            
            # Full script text
            full_text = getattr(script, 'full_text', '')
            if full_text:
                f.write("Generated Script:\n")
                f.write("-" * 20 + "\n")
                f.write(full_text)
                f.write("\n\n")
            
            # Timeline segments
            segments = getattr(script, 'segments', [])
            selected_segments = [s for s in segments if getattr(s, 'keep', True)]
            
            f.write("Timeline Segments:\n")
            f.write("-" * 20 + "\n")
            
            for i, segment in enumerate(selected_segments):
                start_time = getattr(segment, 'start_time', 0)
                end_time = getattr(segment, 'end_time', 0)
                content = getattr(segment, 'content', 'No content')
                video_idx = getattr(segment, 'video_index', 0)
                
                f.write(f"{start_time:.2f}s - {end_time:.2f}s [Video {video_idx + 1}]: {content}\n")
    
    def _export_json_script(self, script: GeneratedScript, output_path: str):
        """Export script as JSON data"""
        import json
        from dataclasses import asdict, is_dataclass
        
        def convert_to_dict(obj):
            if is_dataclass(obj):
                return asdict(obj)
            elif hasattr(obj, '__dict__'):
                return obj.__dict__
            else:
                return str(obj)
        
        try:
            script_dict = convert_to_dict(script)
        except:
            # Fallback to manual conversion
            script_dict = {
                "title": getattr(script, 'title', 'Untitled'),
                "target_duration_minutes": getattr(script, 'target_duration_minutes', 0),
                "estimated_duration_seconds": getattr(script, 'estimated_duration_seconds', 0),
                "user_prompt": getattr(script, 'user_prompt', ''),
                "full_text": getattr(script, 'full_text', ''),
                "segments": [convert_to_dict(s) for s in getattr(script, 'segments', [])],
                "metadata": getattr(script, 'metadata', {})
            }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(script_dict, f, indent=2, ensure_ascii=False, default=str)
    
    def _update_progress(self, message: str, percent: float, stage: ProcessingStage):
        """Update progress tracking"""
        # Call progress callback if provided
        if self.progress_callback:
            self.progress_callback(message, percent)
        
        logger.info(f"Progress: {message} ({percent:.1f}%)")
    
    def get_project_status(self) -> Dict[str, Any]:
        """Get current project status"""
        if not self.current_project:
            return {"error": "No project loaded"}
        
        return {
            "project_name": self.current_project.get("name", "Unknown"),
            "video_count": len(self.current_project.get("video_paths", [])),
            "has_transcription": bool(self.current_project.get("transcription_results")),
            "has_script": bool(self.current_project.get("generated_script"))
        }

# Convenience functions for the new workflow
def quick_transcribe_videos(
    project_name: str,
    video_paths: List[str],
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> ProcessingResult:
    """
    Quick transcription of videos (Step 1 of new workflow)
    
    Args:
        project_name: Name for the project
        video_paths: List of video file paths
        progress_callback: Optional progress callback
        
    Returns:
        ProcessingResult with transcription data
    """
    pipeline = SmartEditPipeline(progress_callback)
    return pipeline.process_transcription_only(project_name, video_paths)

def quick_generate_script(
    transcription_results: List,
    user_prompt: str,
    target_duration_minutes: int = 10,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> ProcessingResult:
    """
    Quick script generation from prompt (Step 2 of new workflow)
    
    Args:
        transcription_results: Results from transcription step  
        user_prompt: User's instructions for the video
        target_duration_minutes: Target duration in minutes
        progress_callback: Optional progress callback
        
    Returns:
        ProcessingResult with generated script
    """
    pipeline = SmartEditPipeline(progress_callback)  
    return pipeline.generate_script_from_prompt(
        user_prompt, target_duration_minutes, transcription_results
    )

def quick_export_script(
    generated_script: GeneratedScript,
    video_paths: List[str],
    output_path: str,
    export_format: str = "edl",
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> ProcessingResult:
    """
    Quick export of generated script (Step 3 of new workflow)
    
    Args:
        generated_script: Script to export
        video_paths: List of video file paths (required for EDL export)
        output_path: Output file path
        export_format: Export format ("edl", "text", "json")
        progress_callback: Optional progress callback
        
    Returns:
        ProcessingResult with export status
    """
    pipeline = SmartEditPipeline(progress_callback)
    return pipeline.export_generated_script(output_path, video_paths, generated_script, export_format)

# Example usage
if __name__ == "__main__":
    # Example of new workflow
    def progress_update(message: str, percent: float):
        print(f"[{percent:5.1f}%] {message}")
    
    # Step 1: Transcribe
    print("Step 1: Transcribing videos...")
    result1 = quick_transcribe_videos(
        "Test Project",
        ["video1.mp4", "video2.mp4"],
        progress_update
    )
    
    if result1.success:
        print("✅ Transcription completed")
        
        # Step 2: Generate script (would normally get prompt from UI)
        print("Step 2: Generating script...")
        result2 = quick_generate_script(
            result1.data,
            "Create a 10-minute educational video focusing on key concepts",
            10,
            progress_update
        )
        
        if result2.success:
            print("✅ Script generated")
            
            # Step 3: Export to EDL
            print("Step 3: Exporting to EDL...")
            # Fixed: Pass video paths to export function
            video_paths = ["video1.mp4", "video2.mp4"]  # Would come from transcription step
            result3 = quick_export_script(
                result2.data,
                video_paths,
                "output.edl",
                "edl",
                progress_update
            )
            
            if result3.success:
                print("✅ EDL export completed")
            else:
                print(f"❌ Export failed: {result3.message}")
        else:
            print(f"❌ Script generation failed: {result2.message}")
    else:
        print(f"❌ Transcription failed: {result1.message}")