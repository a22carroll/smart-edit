"""
Smart Edit Core Data Models

Centralized data models and type definitions for the Smart Edit system.
Provides a clean interface between all modules.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from pathlib import Path
from enum import Enum

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import existing models from modules
from transcription import TranscriptionResult, TranscriptSegment, WordTimestamp, ContentSection
from script_generation import EditScript, CutDecision, TransitionPoint, EditAction, ConfidenceLevel

class ProjectType(Enum):
    """Type of video project"""
    SINGLE_CAM = "single_camera"
    MULTICAM = "multicamera"
    PODCAST = "podcast"
    INTERVIEW = "interview"
    PRESENTATION = "presentation"

class ProcessingStage(Enum):
    """Current stage of processing"""
    CREATED = "created"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    GENERATING_SCRIPT = "generating_script"
    SCRIPT_GENERATED = "script_generated"
    ASSIGNING_ANGLES = "assigning_angles"
    READY_FOR_REVIEW = "ready_for_review"
    REVIEWED = "reviewed"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"

class ExportFormat(Enum):
    """Supported export formats"""
    PREMIERE_XML = "premiere_xml"
    FINAL_CUT_XML = "final_cut_xml"
    DAVINCI_XML = "davinci_xml"
    JSON = "json"

@dataclass
class VideoFile:
    """Represents a video file in the project"""
    path: str
    camera_id: Optional[str] = None
    duration: Optional[float] = None
    fps: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    
    def __post_init__(self):
        """Auto-populate basic file info"""
        if not self.camera_id:
            # Generate camera ID from filename or index
            self.camera_id = Path(self.path).stem
        
        if os.path.exists(self.path):
            self.file_size = os.path.getsize(self.path)
    
    @property
    def filename(self) -> str:
        """Get just the filename"""
        return os.path.basename(self.path)
    
    @property
    def exists(self) -> bool:
        """Check if file exists"""
        return os.path.exists(self.path)

@dataclass
class ProcessingProgress:
    """Track processing progress and status"""
    stage: ProcessingStage = ProcessingStage.CREATED
    progress_percent: float = 0.0
    current_step: str = ""
    steps_completed: int = 0
    total_steps: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_message: Optional[str] = None
    
    @property
    def is_complete(self) -> bool:
        """Check if processing is complete"""
        return self.stage == ProcessingStage.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Check if processing failed"""
        return self.stage == ProcessingStage.FAILED
    
    @property
    def processing_time(self) -> Optional[float]:
        """Get total processing time if available"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

@dataclass
class ProjectSettings:
    """Project-specific settings and preferences"""
    # Transcription settings
    transcription_model: str = "large-v3"
    transcription_language: str = "auto"
    enable_word_timestamps: bool = True
    
    # Script generation settings
    target_compression: float = 0.7
    remove_filler_words: bool = True
    min_pause_threshold: float = 2.0
    keep_question_segments: bool = True
    max_speed_increase: float = 1.3
    
    # Camera assignment settings
    max_segments_per_camera: int = 3
    prefer_speaker_switches: bool = True
    prefer_content_switches: bool = True
    
    # Export settings
    export_format: ExportFormat = ExportFormat.PREMIERE_XML
    export_fps: int = 30
    export_width: int = 1920
    export_height: int = 1080
    
    # UI settings
    auto_open_script_editor: bool = True
    show_processing_details: bool = True

@dataclass
class SmartEditProject:
    """Main project container for Smart Edit"""
    name: str
    video_files: List[VideoFile] = field(default_factory=list)
    project_type: ProjectType = ProjectType.SINGLE_CAM
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    progress: ProcessingProgress = field(default_factory=ProcessingProgress)
    
    # Processing results
    transcription_result: Optional[TranscriptionResult] = None
    edit_script: Optional[EditScript] = None
    
    # Metadata
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    output_directory: Optional[str] = None
    
    def __post_init__(self):
        """Auto-configure project after creation"""
        if not self.created_date:
            from datetime import datetime
            self.created_date = datetime.now().isoformat()
        
        # Auto-detect project type
        if len(self.video_files) > 1:
            self.project_type = ProjectType.MULTICAM
        
        # Set output directory if not specified
        if not self.output_directory and self.video_files:
            first_video_dir = os.path.dirname(self.video_files[0].path)
            self.output_directory = os.path.join(first_video_dir, f"{self.name}_output")
    
    @property
    def is_multicam(self) -> bool:
        """Check if this is a multicam project"""
        return len(self.video_files) > 1 or self.project_type == ProjectType.MULTICAM
    
    @property
    def total_duration(self) -> Optional[float]:
        """Get total project duration if available"""
        if self.transcription_result:
            return self.transcription_result.metadata.get('total_duration')
        return None
    
    @property
    def compression_ratio(self) -> Optional[float]:
        """Get compression ratio if available"""
        if self.edit_script:
            return self.edit_script.compression_ratio
        return None
    
    def add_video_file(self, file_path: str, camera_id: Optional[str] = None) -> VideoFile:
        """Add a video file to the project"""
        video_file = VideoFile(path=file_path, camera_id=camera_id)
        self.video_files.append(video_file)
        
        # Update project type if needed
        if len(self.video_files) > 1 and self.project_type == ProjectType.SINGLE_CAM:
            self.project_type = ProjectType.MULTICAM
        
        return video_file
    
    def remove_video_file(self, file_path: str) -> bool:
        """Remove a video file from the project"""
        for i, video_file in enumerate(self.video_files):
            if video_file.path == file_path:
                self.video_files.pop(i)
                return True
        return False
    
    def get_camera_mapping(self) -> Dict[str, str]:
        """Get mapping of camera IDs to file paths"""
        mapping = {}
        for vf in self.video_files:
            if vf.camera_id and vf.path:
                mapping[vf.camera_id] = vf.path
        return mapping
    
    def validate(self) -> List[str]:
        """Validate project configuration"""
        errors = []
        
        if not self.video_files:
            errors.append("No video files added to project")
        
        for video_file in self.video_files:
            if not video_file.exists:
                errors.append(f"Video file not found: {video_file.path}")
        
        if not self.name or not self.name.strip():
            errors.append("Project name cannot be empty")
        
        return errors
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of project status"""
        return {
            "name": self.name,
            "type": self.project_type.value,
            "video_count": len(self.video_files),
            "stage": self.progress.stage.value,
            "progress_percent": self.progress.progress_percent,
            "is_complete": self.progress.is_complete,
            "has_transcription": self.transcription_result is not None,
            "has_edit_script": self.edit_script is not None,
            "total_duration": self.total_duration,
            "compression_ratio": self.compression_ratio,
            "output_directory": self.output_directory
        }

@dataclass
class ProcessingResult:
    """Result of a processing operation"""
    success: bool
    stage: ProcessingStage
    message: str = ""
    data: Optional[Any] = None
    error: Optional[Exception] = None
    processing_time: Optional[float] = None
    
    @classmethod
    def success_result(cls, stage: ProcessingStage, message: str = "", data: Any = None, processing_time: float = None):
        """Create a successful result"""
        return cls(
            success=True,
            stage=stage,
            message=message,
            data=data,
            processing_time=processing_time
        )
    
    @classmethod
    def error_result(cls, stage: ProcessingStage, error: Exception, message: str = ""):
        """Create an error result"""
        return cls(
            success=False,
            stage=stage,
            message=message or str(error),
            error=error
        )

@dataclass
class ExportOptions:
    """Options for exporting projects"""
    format: ExportFormat = ExportFormat.PREMIERE_XML
    output_path: Optional[str] = None
    sequence_name: Optional[str] = None
    fps: int = 30
    width: int = 1920
    height: int = 1080
    include_audio: bool = True
    include_transitions: bool = True
    
    def validate(self) -> List[str]:
        """Validate export options"""
        errors = []
        
        if self.fps <= 0:
            errors.append("FPS must be positive")
        
        if self.width <= 0 or self.height <= 0:
            errors.append("Width and height must be positive")
        
        if self.output_path:
            output_dir = os.path.dirname(self.output_path)
            if output_dir and not os.path.exists(output_dir):
                errors.append("Output directory does not exist")
        
        return errors

# Type aliases for cleaner code
VideoFilePath = str
CameraID = str
ProjectName = str

# Constants
DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.m4v']
MAX_VIDEO_DURATION = 3600  # 1 hour max
MIN_VIDEO_DURATION = 5     # 5 seconds min

def create_project_from_videos(
    project_name: str, 
    video_paths: List[str],
    settings: Optional[ProjectSettings] = None
) -> SmartEditProject:
    """
    Create a new project from video files
    
    Args:
        project_name: Name for the project
        video_paths: List of video file paths
        settings: Optional project settings
        
    Returns:
        SmartEditProject instance
    """
    project = SmartEditProject(
        name=project_name,
        settings=settings or ProjectSettings()
    )
    
    for i, video_path in enumerate(video_paths):
        camera_id = f"Camera_{i+1}" if len(video_paths) > 1 else "Main_Camera"
        project.add_video_file(video_path, camera_id)
    
    return project

def validate_video_file(file_path: str) -> List[str]:
    """
    Validate a video file
    
    Args:
        file_path: Path to video file
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not os.path.exists(file_path):
        errors.append(f"File does not exist: {file_path}")
        return errors
    
    file_ext = Path(file_path).suffix.lower()
    if file_ext not in SUPPORTED_VIDEO_FORMATS:
        errors.append(f"Unsupported video format: {file_ext}")
    
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        errors.append("Video file is empty")
    elif file_size < 1024:  # Less than 1KB
        errors.append("Video file is too small")
    
    return errors

# Export the main models for easy importing
__all__ = [
    'SmartEditProject',
    'VideoFile', 
    'ProjectSettings',
    'ProcessingProgress',
    'ProcessingResult',
    'ExportOptions',
    'ProjectType',
    'ProcessingStage',
    'ExportFormat',
    'create_project_from_videos',
    'validate_video_file'
]