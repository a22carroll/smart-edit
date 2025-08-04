"""
Smart Edit Core Data Models - Updated for Prompt-Driven Workflow

Centralized data models and type definitions for the Smart Edit system.
Provides a clean interface between all modules with support for user prompt-driven script generation.
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
try:
    from transcription import TranscriptionResult, TranscriptSegment, WordTimestamp, ContentSection
    # Updated import for new script generation
    from script_generation import GeneratedScript, ScriptSegment
    # Note: Old EditScript import removed - no longer used in new workflow
except ImportError as e:
    print(f"Warning: Could not import some modules - {e}")
    # Define minimal fallbacks for development
    class TranscriptionResult:
        pass
    class GeneratedScript:
        pass
    class ScriptSegment:
        pass

class ProjectType(Enum):
    """Type of video project"""
    SINGLE_CAM = "single_camera"
    MULTICAM = "multicamera"
    PODCAST = "podcast"
    INTERVIEW = "interview"
    PRESENTATION = "presentation"
    TUTORIAL = "tutorial"  # Added for educational content
    VLOG = "vlog"         # Added for personal content

class ProcessingStage(Enum):
    """Current stage of processing - Updated for new workflow"""
    CREATED = "created"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    READY_FOR_SCRIPT = "ready_for_script"        # New: After transcription, ready for prompt
    GENERATING_SCRIPT = "generating_script"      # New: AI is generating script from prompt
    SCRIPT_GENERATED = "script_generated"        # New: Script ready for review
    SCRIPT_REVIEWED = "script_reviewed"          # New: User has reviewed/edited script
    READY_FOR_EXPORT = "ready_for_export"        # New: Ready to export
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"

class ExportFormat(Enum):
    """Supported export formats"""
    PREMIERE_XML = "premiere_xml"
    FINAL_CUT_XML = "final_cut_xml"
    DAVINCI_XML = "davinci_xml"
    JSON = "json"
    TEXT_SCRIPT = "text_script"  # New: Readable text format

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
    
    @property
    def size_mb(self) -> float:
        """Get file size in MB"""
        if self.file_size:
            return self.file_size / (1024 * 1024)
        return 0.0

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
    """Project-specific settings and preferences - Updated for new workflow"""
    # Transcription settings
    transcription_model: str = "base"  # Changed: Default to base for faster processing
    transcription_language: str = "auto"
    enable_word_timestamps: bool = True
    
    # Script generation settings - Updated for prompt-driven approach
    default_target_duration_minutes: int = 10    # New: Default target duration
    enable_ai_script_generation: bool = True     # New: Enable/disable AI features
    fallback_compression_ratio: float = 0.7      # New: Fallback if no AI
    
    # Legacy settings (kept for compatibility but not used in new workflow)
    remove_filler_words: bool = True
    min_pause_threshold: float = 2.0
    keep_question_segments: bool = True
    max_speed_increase: float = 1.3
    
    # Export settings
    export_format: ExportFormat = ExportFormat.PREMIERE_XML
    export_fps: int = 30
    export_width: int = 1920
    export_height: int = 1080
    
    # UI settings
    auto_open_script_editor: bool = True
    show_processing_details: bool = True
    remember_user_prompts: bool = True           # New: Save prompt history

@dataclass
class UserPromptHistory:
    """Track user prompt history for better UX"""
    prompts: List[str] = field(default_factory=list)
    last_used_duration: int = 10
    favorite_prompts: List[str] = field(default_factory=list)
    
    def add_prompt(self, prompt: str):
        """Add a prompt to history"""
        if prompt and prompt not in self.prompts:
            self.prompts.insert(0, prompt)  # Add to beginning
            # Keep only last 10 prompts
            if len(self.prompts) > 10:
                self.prompts = self.prompts[:10]
    
    def add_favorite(self, prompt: str):
        """Add a prompt to favorites"""
        if prompt and prompt not in self.favorite_prompts:
            self.favorite_prompts.append(prompt)

@dataclass
class SmartEditProject:
    """Main project container for Smart Edit - Updated for new workflow"""
    name: str
    video_files: List[VideoFile] = field(default_factory=list)
    project_type: ProjectType = ProjectType.SINGLE_CAM
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    progress: ProcessingProgress = field(default_factory=ProcessingProgress)
    
    # Processing results - Updated for new workflow
    transcription_results: List[TranscriptionResult] = field(default_factory=list)  # Changed: Now list for multi-video
    generated_script: Optional[GeneratedScript] = None                              # New: Replaces edit_script
    user_prompt_history: UserPromptHistory = field(default_factory=UserPromptHistory)  # New: Prompt tracking
    
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
        if self.transcription_results:
            return sum(t.metadata.get('total_duration', 0) for t in self.transcription_results)
        return None
    
    @property
    def total_segments(self) -> int:
        """Get total number of transcript segments"""
        if self.transcription_results:
            return sum(len(t.segments) for t in self.transcription_results)
        return 0
    
    @property
    def estimated_script_duration(self) -> Optional[float]:
        """Get estimated duration of generated script"""
        if self.generated_script:
            return getattr(self.generated_script, 'estimated_duration_seconds', None)
        return None
    
    @property
    def script_compression_ratio(self) -> Optional[float]:
        """Get script compression ratio if available"""
        if self.generated_script and hasattr(self.generated_script, 'metadata'):
            return self.generated_script.metadata.get('compression_ratio')
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
                
                # Also remove corresponding transcription if exists
                if i < len(self.transcription_results):
                    self.transcription_results.pop(i)
                
                return True
        return False
    
    def add_transcription_result(self, result: TranscriptionResult):
        """Add a transcription result"""
        self.transcription_results.append(result)
    
    def set_generated_script(self, script: GeneratedScript, user_prompt: str = ""):
        """Set the generated script and update prompt history"""
        self.generated_script = script
        if user_prompt:
            self.user_prompt_history.add_prompt(user_prompt)
    
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
        
        # Validate transcription results match video files
        if self.transcription_results and len(self.transcription_results) != len(self.video_files):
            errors.append("Transcription results don't match video files")
        
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
            "has_transcription": bool(self.transcription_results),
            "has_generated_script": self.generated_script is not None,
            "total_duration": self.total_duration,
            "total_segments": self.total_segments,
            "script_compression_ratio": self.script_compression_ratio,
            "estimated_script_duration": self.estimated_script_duration,
            "output_directory": self.output_directory,
            "prompt_history_count": len(self.user_prompt_history.prompts)
        }
    
    def get_workflow_status(self) -> Dict[str, bool]:
        """Get workflow step completion status"""
        return {
            "videos_loaded": bool(self.video_files),
            "transcription_complete": bool(self.transcription_results),
            "script_generated": self.generated_script is not None,
            "ready_for_export": (self.generated_script is not None and 
                               self.progress.stage in [ProcessingStage.SCRIPT_REVIEWED, 
                                                     ProcessingStage.READY_FOR_EXPORT])
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
    """Options for exporting projects - Updated for new workflow"""
    format: ExportFormat = ExportFormat.PREMIERE_XML
    output_path: Optional[str] = None
    sequence_name: Optional[str] = None
    fps: int = 30
    width: int = 1920
    height: int = 1080
    include_audio: bool = True
    include_transitions: bool = True
    
    # New options for script-based export
    export_full_script_text: bool = True          # Include readable script
    export_timeline_data: bool = True             # Include segment timing
    export_user_prompt: bool = True               # Include original prompt
    export_only_selected_segments: bool = True    # Only export segments marked as 'keep'
    
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

@dataclass
class ScriptGenerationRequest:
    """Request for script generation - New model for prompt-driven workflow"""
    user_prompt: str
    target_duration_minutes: int = 10
    transcription_results: List[TranscriptionResult] = field(default_factory=list)
    project_name: str = "Untitled Project"
    preferred_style: str = "balanced"  # "concise", "balanced", "detailed"
    
    def validate(self) -> List[str]:
        """Validate script generation request"""
        errors = []
        
        if not self.user_prompt or not self.user_prompt.strip():
            errors.append("User prompt cannot be empty")
        
        if self.target_duration_minutes <= 0:
            errors.append("Target duration must be positive")
        
        if not self.transcription_results:
            errors.append("No transcription results provided")
        
        return errors

# Type aliases for cleaner code
VideoFilePath = str
CameraID = str
ProjectName = str
UserPrompt = str

# Constants - Updated
DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.m4v', '.flv', '.webm']
MAX_VIDEO_DURATION = 7200  # 2 hours max (increased)
MIN_VIDEO_DURATION = 5     # 5 seconds min
DEFAULT_TRANSCRIPTION_MODEL = "base"  # Changed from large-v3 for faster processing
MAX_USER_PROMPT_LENGTH = 2000  # Characters

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

def validate_user_prompt(prompt: str) -> List[str]:
    """
    Validate a user prompt for script generation
    
    Args:
        prompt: User's prompt text
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not prompt or not prompt.strip():
        errors.append("Prompt cannot be empty")
        return errors
    
    if len(prompt) > MAX_USER_PROMPT_LENGTH:
        errors.append(f"Prompt too long ({len(prompt)} chars, max {MAX_USER_PROMPT_LENGTH})")
    
    if len(prompt.strip()) < 10:
        errors.append("Prompt too short (minimum 10 characters)")
    
    return errors

# Export the main models for easy importing
__all__ = [
    'SmartEditProject',
    'VideoFile', 
    'ProjectSettings',
    'ProcessingProgress',
    'ProcessingResult',
    'ExportOptions',
    'ScriptGenerationRequest',
    'UserPromptHistory',
    'ProjectType',
    'ProcessingStage',
    'ExportFormat',
    'create_project_from_videos',
    'validate_video_file',
    'validate_user_prompt'
]