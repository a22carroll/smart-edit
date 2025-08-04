"""
Smart Edit Core Pipeline

Orchestrates the complete video processing workflow from raw videos to final XML export.
Provides high-level interface for the entire Smart Edit system.
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

# Import core models
from core.models import (
    SmartEditProject, VideoFile, ProcessingStage, ProcessingResult,
    ExportOptions, ExportFormat, ProjectSettings, create_project_from_videos
)

# Import processing modules
from transcription import transcribe_video, TranscriptionConfig
from script_generation import generate_script, ScriptGenerationConfig
from angle_assignment import assign_camera_angles, AngleAssignmentConfig
from xml_export import export_single_cam_xml, export_multicam_xml

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartEditPipeline:
    """Main processing pipeline for Smart Edit"""
    
    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        """
        Initialize the pipeline
        
        Args:
            progress_callback: Optional callback for progress updates (message, percent)
        """
        self.progress_callback = progress_callback
        self.current_project: Optional[SmartEditProject] = None
    
    def create_project(
        self, 
        project_name: str, 
        video_paths: List[str],
        settings: Optional[ProjectSettings] = None
    ) -> SmartEditProject:
        """
        Create a new Smart Edit project
        
        Args:
            project_name: Name for the project
            video_paths: List of video file paths
            settings: Optional project settings
            
        Returns:
            SmartEditProject instance
        """
        logger.info(f"Creating project: {project_name}")
        
        project = create_project_from_videos(project_name, video_paths, settings)
        
        # Validate project
        errors = project.validate()
        if errors:
            raise ValueError(f"Project validation failed: {', '.join(errors)}")
        
        self.current_project = project
        self._update_progress("Project created", 0.0, ProcessingStage.CREATED)
        
        logger.info(f"Project created: {project.get_status_summary()}")
        return project
    
    def process_project(self, project: Optional[SmartEditProject] = None) -> ProcessingResult:
        """
        Process a complete project through the pipeline
        
        Args:
            project: Project to process (uses current project if None)
            
        Returns:
            ProcessingResult with final status
        """
        if project:
            self.current_project = project
        
        if not self.current_project:
            return ProcessingResult.error_result(
                ProcessingStage.FAILED, 
                ValueError("No project to process")
            )
        
        project = self.current_project
        start_time = time.time()
        
        try:
            logger.info(f"Starting pipeline processing for project: {project.name}")
            
            # Step 1: Transcription
            transcription_result = self._process_transcription(project)
            if not transcription_result.success:
                return transcription_result
            
            # Step 2: Script Generation
            script_result = self._process_script_generation(project)
            if not script_result.success:
                return script_result
            
            # Step 3: Camera Assignment (if multicam)
            if project.is_multicam:
                angle_result = self._process_angle_assignment(project)
                if not angle_result.success:
                    return angle_result
            
            # Mark as ready for review
            self._update_progress("Processing complete - Ready for review", 100.0, ProcessingStage.READY_FOR_REVIEW)
            
            processing_time = time.time() - start_time
            logger.info(f"Pipeline processing completed in {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.READY_FOR_REVIEW,
                "Project processed successfully",
                project,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
            logger.error(traceback.format_exc())
            
            self._update_progress(f"Processing failed: {str(e)}", 0.0, ProcessingStage.FAILED)
            project.progress.error_message = str(e)
            
            return ProcessingResult.error_result(ProcessingStage.FAILED, e)
    
    def _process_transcription(self, project: SmartEditProject) -> ProcessingResult:
        """Process transcription step"""
        try:
            self._update_progress("Starting transcription...", 10.0, ProcessingStage.TRANSCRIBING)
            start_time = time.time()
            
            # Configure transcription
            config = TranscriptionConfig(
                model_size=project.settings.transcription_model,
                language=project.settings.transcription_language,
                enable_word_timestamps=project.settings.enable_word_timestamps,
                accuracy_mode=True
            )
            
            # Get video paths
            if project.is_multicam:
                video_paths = [vf.path for vf in project.video_files]
                logger.info(f"Processing multicam with {len(video_paths)} videos")
            else:
                video_paths = project.video_files[0].path
                logger.info(f"Processing single video: {video_paths}")
            
            logger.info(f"Transcribing {len(project.video_files)} video(s)")
            
            # Perform transcription
            transcription_result = transcribe_video(video_paths, config)
            project.transcription_result = transcription_result
            
            processing_time = time.time() - start_time
            
            self._update_progress("Transcription complete", 30.0, ProcessingStage.TRANSCRIBED)
            
            logger.info(f"Transcription completed: {len(transcription_result.segments)} segments in {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.TRANSCRIBED,
                f"Transcribed {len(transcription_result.segments)} segments",
                transcription_result,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ProcessingResult.error_result(ProcessingStage.TRANSCRIBING, e)
    
    def _process_script_generation(self, project: SmartEditProject) -> ProcessingResult:
        """Process script generation step"""
        try:
            self._update_progress("Generating edit script...", 50.0, ProcessingStage.GENERATING_SCRIPT)
            start_time = time.time()
            
            if not project.transcription_result:
                raise ValueError("No transcription result available")
            
            # Configure script generation
            config = ScriptGenerationConfig(
                target_compression=project.settings.target_compression,
                remove_filler_words=project.settings.remove_filler_words,
                min_pause_threshold=project.settings.min_pause_threshold,
                keep_question_segments=project.settings.keep_question_segments,
                max_speed_increase=project.settings.max_speed_increase
            )
            
            logger.info("Generating edit script with AI analysis")
            
            # Generate script
            edit_script = generate_script(project.transcription_result, config)
            project.edit_script = edit_script
            
            processing_time = time.time() - start_time
            
            self._update_progress("Edit script generated", 70.0, ProcessingStage.SCRIPT_GENERATED)
            
            logger.info(f"Script generation completed: {edit_script.compression_ratio:.1%} compression in {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.SCRIPT_GENERATED,
                f"Generated script with {edit_script.compression_ratio:.1%} compression",
                edit_script,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            return ProcessingResult.error_result(ProcessingStage.GENERATING_SCRIPT, e)
    
    def _process_angle_assignment(self, project: SmartEditProject) -> ProcessingResult:
        """Process camera angle assignment step"""
        try:
            self._update_progress("Assigning camera angles...", 85.0, ProcessingStage.ASSIGNING_ANGLES)
            start_time = time.time()
            
            if not project.edit_script:
                raise ValueError("No edit script available")
            
            # Configure angle assignment
            from angle_assignment import AngleAssignmentConfig
            config = AngleAssignmentConfig(
                max_segments_per_camera=project.settings.max_segments_per_camera,
                prefer_speaker_switches=project.settings.prefer_speaker_switches,
                prefer_content_switches=project.settings.prefer_content_switches
            )
            
            # Get camera IDs
            camera_ids = []
            for vf in project.video_files:
                if vf.camera_id:
                    camera_ids.append(vf.camera_id)
            
            if not camera_ids:
                raise ValueError("No valid camera IDs found for angle assignment")
            
            logger.info(f"Assigning angles for {len(camera_ids)} cameras")
            
            # Assign angles
            project.edit_script = assign_camera_angles(
                project.edit_script, 
                camera_ids, 
                strategy="smart",
                config=config
            )
            
            processing_time = time.time() - start_time
            
            self._update_progress("Camera angles assigned", 90.0, ProcessingStage.READY_FOR_REVIEW)
            
            logger.info(f"Angle assignment completed in {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.READY_FOR_REVIEW,
                f"Assigned angles for {len(camera_ids)} cameras",
                project.edit_script,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Angle assignment failed: {e}")
            return ProcessingResult.error_result(ProcessingStage.ASSIGNING_ANGLES, e)
    
    def export_project(
        self, 
        export_options: ExportOptions,
        project: Optional[SmartEditProject] = None
    ) -> ProcessingResult:
        """
        Export project to specified format
        
        Args:
            export_options: Export configuration
            project: Project to export (uses current project if None)
            
        Returns:
            ProcessingResult with export status
        """
        if project:
            self.current_project = project
        
        if not self.current_project:
            return ProcessingResult.error_result(
                ProcessingStage.FAILED,
                ValueError("No project to export")
            )
        
        project = self.current_project
        
        if not project.edit_script:
            return ProcessingResult.error_result(
                ProcessingStage.FAILED,
                ValueError("No edit script available for export")
            )
        
        try:
            self._update_progress("Exporting project...", 95.0, ProcessingStage.EXPORTING)
            start_time = time.time()
            
            # Validate export options
            errors = export_options.validate()
            if errors:
                raise ValueError(f"Export validation failed: {', '.join(errors)}")
            
            # Generate output path if not specified
            if not export_options.output_path:
                output_dir = project.output_directory
                if not output_dir and project.video_files:
                    output_dir = os.path.dirname(project.video_files[0].path)
                
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    format_ext = {"premiere_xml": ".xml", "json": ".json"}.get(export_options.format.value, ".xml")
                    export_options.output_path = os.path.join(output_dir, f"{project.name}_edit{format_ext}")
                else:
                    raise ValueError("Cannot determine output directory")
            
            # Set sequence name if not specified
            if not export_options.sequence_name:
                export_options.sequence_name = f"{project.name}_Timeline"
            
            # Export based on format and project type
            success = False
            
            if export_options.format == ExportFormat.PREMIERE_XML:
                if project.is_multicam:
                    camera_mapping = project.get_camera_mapping()
                    success = export_multicam_xml(
                        project.edit_script,
                        camera_mapping,
                        export_options.output_path,
                        fps=export_options.fps,
                        sequence_name=export_options.sequence_name
                    )
                else:
                    success = export_single_cam_xml(
                        project.edit_script,
                        project.video_files[0].path,
                        export_options.output_path,
                        fps=export_options.fps,
                        sequence_name=export_options.sequence_name
                    )
            elif export_options.format == ExportFormat.JSON:
                # Export as JSON for other tools
                self._export_json(project, export_options.output_path)
                success = True
            else:
                raise ValueError(f"Unsupported export format: {export_options.format.value}")
            
            if not success:
                raise RuntimeError("Export operation returned False")
            
            processing_time = time.time() - start_time
            
            self._update_progress("Export complete", 100.0, ProcessingStage.COMPLETED)
            project.progress.end_time = time.time()
            
            logger.info(f"Export completed: {export_options.output_path} in {processing_time:.2f}s")
            
            return ProcessingResult.success_result(
                ProcessingStage.COMPLETED,
                f"Exported to {export_options.output_path}",
                export_options.output_path,
                processing_time
            )
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            self._update_progress(f"Export failed: {str(e)}", 0.0, ProcessingStage.FAILED)
            return ProcessingResult.error_result(ProcessingStage.EXPORTING, e)
    
    def _export_json(self, project: SmartEditProject, output_path: str):
        """Export project as JSON"""
        import json
        from dataclasses import asdict
        
        # Convert project to JSON-serializable format
        export_data = {
            "project_name": project.name,
            "project_type": project.project_type.value,
            "video_files": [asdict(vf) for vf in project.video_files],
            "settings": asdict(project.settings),
            "transcription_summary": {
                "total_duration": project.total_duration,
                "segment_count": len(project.transcription_result.segments) if project.transcription_result else 0,
                "language": project.transcription_result.metadata.get('language_detected') if project.transcription_result else None
            } if project.transcription_result else None,
            "edit_script_summary": {
                "compression_ratio": project.edit_script.compression_ratio,
                "segments_kept": project.edit_script.metadata.get('segments_kept', 0),
                "segments_removed": project.edit_script.metadata.get('segments_removed', 0),
                "estimated_duration": project.edit_script.estimated_final_duration
            } if project.edit_script else None,
            "export_timestamp": time.time()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    def _update_progress(self, message: str, percent: float, stage: ProcessingStage):
        """Update progress tracking"""
        if self.current_project:
            self.current_project.progress.current_step = message
            self.current_project.progress.progress_percent = percent
            self.current_project.progress.stage = stage
            
            if stage == ProcessingStage.TRANSCRIBING and not self.current_project.progress.start_time:
                self.current_project.progress.start_time = time.time()
        
        # Call progress callback if provided
        if self.progress_callback:
            self.progress_callback(message, percent)
        
        logger.info(f"Progress: {message} ({percent:.1f}%)")
    
    def get_project_status(self, project: Optional[SmartEditProject] = None) -> Dict[str, Any]:
        """Get current project status"""
        if project:
            target_project = project
        else:
            target_project = self.current_project
        
        if not target_project:
            return {"error": "No project loaded"}
        
        return target_project.get_status_summary()

# Convenience functions for common workflows
def quick_process_videos(
    project_name: str,
    video_paths: List[str],
    output_path: Optional[str] = None,
    settings: Optional[ProjectSettings] = None,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> ProcessingResult:
    """
    Quick processing of videos through the complete pipeline
    
    Args:
        project_name: Name for the project
        video_paths: List of video file paths
        output_path: Optional output path for XML
        settings: Optional project settings
        progress_callback: Optional progress callback
        
    Returns:
        ProcessingResult with final status
    """
    pipeline = SmartEditPipeline(progress_callback)
    
    try:
        # Create project
        project = pipeline.create_project(project_name, video_paths, settings)
        
        # Process through pipeline
        result = pipeline.process_project(project)
        if not result.success:
            return result
        
        # Export if output path specified
        if output_path:
            export_options = ExportOptions(
                format=ExportFormat.PREMIERE_XML,
                output_path=output_path,
                sequence_name=f"{project_name}_Timeline"
            )
            
            export_result = pipeline.export_project(export_options)
            return export_result
        
        return result
        
    except Exception as e:
        logger.error(f"Quick processing failed: {e}")
        return ProcessingResult.error_result(ProcessingStage.FAILED, e)

def process_single_video(
    video_path: str,
    output_path: Optional[str] = None,
    compression_ratio: float = 0.7
) -> ProcessingResult:
    """
    Process a single video with default settings
    
    Args:
        video_path: Path to video file
        output_path: Optional output XML path
        compression_ratio: Target compression ratio
        
    Returns:
        ProcessingResult with final status
    """
    project_name = Path(video_path).stem
    settings = ProjectSettings(target_compression=compression_ratio)
    
    return quick_process_videos(
        project_name,
        [video_path],
        output_path,
        settings
    )

# Example usage
if __name__ == "__main__":
    # Example of processing a single video
    def progress_update(message: str, percent: float):
        print(f"[{percent:5.1f}%] {message}")
    
    result = process_single_video(
        "example_video.mp4",
        "example_output.xml",
        compression_ratio=0.8
    )
    
    if result.success:
        print(f"✅ Processing completed: {result.message}")
    else:
        print(f"❌ Processing failed: {result.message}")