"""
Smart Edit Transcription Module

Handles video transcription with high accuracy focus, optimized for script generation.
Supports single and multi-camera setups with timecode synchronization.
"""

import os
import time
import tempfile
import subprocess
import logging
from typing import List, Dict, Union, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
import json

import whisper
import torch

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float
    confidence: float

@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str
    confidence: float
    sentence_boundary: bool
    pause_after: float
    speech_rate: str
    contains_filler: bool
    content_type: str
    words: List[WordTimestamp]

@dataclass
class ContentSection:
    start: float
    end: float
    section_type: str
    title: Optional[str] = None

@dataclass
class TranscriptionResult:
    segments: List[TranscriptSegment]
    natural_breaks: List[float]
    speaker_changes: List[float]
    content_sections: List[ContentSection]
    metadata: Dict[str, Any]
    full_text: str

class TranscriptionConfig:
    def __init__(
        self,
        accuracy_mode: bool = True,
        language: str = "auto",
        enable_speaker_detection: bool = True,
        enable_word_timestamps: bool = True,
        model_size: str = "base",
        device: str = "auto",
        filler_words: Optional[List[str]] = None
    ):
        self.accuracy_mode = accuracy_mode
        self.language = language
        self.enable_speaker_detection = enable_speaker_detection
        self.enable_word_timestamps = enable_word_timestamps
        self.model_size = model_size
        self.device = self._get_device(device)
        self.filler_words = filler_words or ["um", "uh", "like", "you know", "so", "well"]

    def _get_device(self, device: str) -> str:
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        return device

class SmartTranscriber:
    def __init__(self, config: Optional[TranscriptionConfig] = None):
        self.config = config or TranscriptionConfig()
        self.model = None
        self._validate_dependencies()
        self._load_model()
    
    def _validate_dependencies(self):
        """Validate FFmpeg is available"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "FFmpeg not found. Install with:\n"
                "Windows: Download from https://ffmpeg.org\n"
                "Mac: brew install ffmpeg\n"
                "Linux: sudo apt install ffmpeg"
            )
    
    def _load_model(self):
        """Load Whisper model"""
        try:
            logger.info(f"Loading Whisper {self.config.model_size} on {self.config.device}")
            self.model = whisper.load_model(self.config.model_size, device=self.config.device)
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def transcribe_video(self, video_paths: Union[str, List[str]]) -> TranscriptionResult:
        """Main transcription method"""
        start_time = time.time()
        
        if isinstance(video_paths, str):
            video_paths = [video_paths]
        
        self._validate_files(video_paths)
        
        all_segments = []
        total_duration = 0
        
        for i, video_path in enumerate(video_paths):
            logger.info(f"Processing {i+1}/{len(video_paths)}: {Path(video_path).name}")
            
            raw_result = self._transcribe_audio(video_path)
            segments = self._process_segments(raw_result, i)
            all_segments.extend(segments)
            
            if raw_result.get('segments'):
                video_duration = max(seg['end'] for seg in raw_result['segments'])
                total_duration = max(total_duration, video_duration)
        
        all_segments.sort(key=lambda x: x.start)
        
        # Generate analysis
        natural_breaks = self._find_natural_breaks(all_segments)
        speaker_changes = self._find_speaker_changes(all_segments)
        content_sections = self._analyze_content_sections(all_segments)
        full_text = " ".join(seg.text for seg in all_segments)
        
        processing_time = time.time() - start_time
        metadata = {
            "total_duration": total_duration,
            "video_count": len(video_paths),
            "language_detected": raw_result.get('language', 'unknown'),
            "speaker_count": len(set(seg.speaker for seg in all_segments)),
            "processing_time": round(processing_time, 2),
            "model_used": f"whisper-{self.config.model_size}",
            "device_used": self.config.device,
            "segment_count": len(all_segments)
        }
        
        return TranscriptionResult(
            segments=all_segments,
            natural_breaks=natural_breaks,
            speaker_changes=speaker_changes,
            content_sections=content_sections,
            metadata=metadata,
            full_text=full_text
        )
    
    def _validate_files(self, video_paths: List[str]):
        """Validate video files exist"""
        for path in video_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Video file not found: {path}")
            
            file_size = os.path.getsize(path)
            if file_size == 0:
                raise ValueError(f"Video file is empty: {path}")
            
            logger.info(f"Video: {Path(path).name} ({file_size / (1024*1024):.1f}MB)")
    
    def _extract_audio(self, video_path: str) -> str:
        """Extract audio to temporary WAV file"""
        temp_dir = tempfile.gettempdir()
        video_name = Path(video_path).stem
        audio_path = os.path.join(temp_dir, f"{video_name}_audio_{int(time.time())}.wav")
        
        logger.info(f"Extracting audio from: {Path(video_path).name}")
        
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1',
            audio_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                raise RuntimeError("Audio extraction failed")
            
            audio_size = os.path.getsize(audio_path)
            logger.info(f"Audio extracted: {audio_size / (1024*1024):.1f}MB")
            return audio_path
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg failed: {e.stderr}")
    
    def _transcribe_audio(self, video_path: str) -> Dict:
        """Extract audio and transcribe"""
        audio_path = None
        try:
            audio_path = self._extract_audio(video_path)
            
            options = {
                "language": None if self.config.language == "auto" else self.config.language,
                "task": "transcribe",
                "word_timestamps": self.config.enable_word_timestamps,
                "fp16": self.config.device == "cuda"
            }
            
            logger.info(f"Transcribing: {Path(audio_path).name}")
            return self.model.transcribe(audio_path, **options)
            
        finally:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.info(f"Cleaned up: {Path(audio_path).name}")
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")
    
    def _process_segments(self, raw_result: Dict, video_index: int) -> List[TranscriptSegment]:
        """Process raw segments into enhanced segments"""
        segments = []
        raw_segments = raw_result.get('segments', [])
        
        for i, segment in enumerate(raw_segments):
            text = segment.get('text', '').strip()
            
            # Extract word timestamps
            words = []
            if self.config.enable_word_timestamps and 'words' in segment:
                words = [
                    WordTimestamp(
                        word=w.get('word', '').strip(),
                        start=w.get('start', 0.0),
                        end=w.get('end', 0.0),
                        confidence=w.get('probability', 0.0)
                    )
                    for w in segment.get('words', [])
                ]
            
            # Analyze segment
            contains_filler = any(filler in text.lower() for filler in self.config.filler_words)
            speech_rate = self._analyze_speech_rate(segment)
            content_type = self._classify_content_type(text, i, len(raw_segments))
            sentence_boundary = text.strip().endswith(('.', '!', '?', ':'))
            pause_after = self._calculate_pause_after(segment, raw_segments, i)
            speaker = f"Speaker_{video_index + 1}"
            
            processed_segment = TranscriptSegment(
                start=segment.get('start', 0.0),
                end=segment.get('end', 0.0),
                text=text,
                speaker=speaker,
                confidence=segment.get('avg_logprob', 0.0),
                sentence_boundary=sentence_boundary,
                pause_after=pause_after,
                speech_rate=speech_rate,
                contains_filler=contains_filler,
                content_type=content_type,
                words=words
            )
            
            segments.append(processed_segment)
        
        return segments
    
    def _analyze_speech_rate(self, segment: Dict) -> str:
        """Analyze speech rate"""
        duration = segment.get('end', 0) - segment.get('start', 0)
        if duration <= 0:
            return "normal"
        
        word_count = len(segment.get('text', '').split())
        words_per_second = word_count / duration
        
        if words_per_second < 1.5:
            return "slow"
        elif words_per_second > 3.0:
            return "fast"
        return "normal"
    
    def _classify_content_type(self, text: str, index: int, total: int) -> str:
        """Classify content type"""
        text_lower = text.lower()
        
        # Introduction
        if index < 3:
            if any(word in text_lower for word in ["hello", "hi", "welcome", "today"]):
                return "greeting"
            if any(word in text_lower for word in ["discuss", "talk about", "cover"]):
                return "topic_introduction"
        
        # Conclusion
        if index >= total - 3:
            if any(word in text_lower for word in ["conclusion", "summary", "thank you"]):
                return "conclusion"
        
        # Transitions
        if any(word in text_lower for word in ["next", "now", "moving on", "however", "but"]):
            return "transition"
        
        # Main points
        if text.strip().endswith('?') or any(word in text_lower for word in ["important", "key", "main"]):
            return "main_point"
        
        return "supporting"
    
    def _calculate_pause_after(self, current: Dict, all_segments: List[Dict], index: int) -> float:
        """Calculate pause after segment"""
        if index >= len(all_segments) - 1:
            return 0.0
        
        next_segment = all_segments[index + 1]
        return max(0.0, next_segment.get('start', 0.0) - current.get('end', 0.0))
    
    def _find_natural_breaks(self, segments: List[TranscriptSegment]) -> List[float]:
        """Find natural break points"""
        breaks = []
        for segment in segments:
            if segment.sentence_boundary and segment.pause_after > 0.5:
                breaks.append(segment.end)
            if segment.content_type in ["transition", "topic_introduction"]:
                breaks.append(segment.start)
        return sorted(set(breaks))
    
    def _find_speaker_changes(self, segments: List[TranscriptSegment]) -> List[float]:
        """Find speaker changes"""
        changes = []
        current_speaker = None
        for segment in segments:
            if current_speaker and segment.speaker != current_speaker:
                changes.append(segment.start)
            current_speaker = segment.speaker
        return changes
    
    def _analyze_content_sections(self, segments: List[TranscriptSegment]) -> List[ContentSection]:
        """Group segments into content sections"""
        if not segments:
            return []
        
        sections = []
        current_type = segments[0].content_type
        section_start = segments[0].start
        
        for i, segment in enumerate(segments[1:], 1):
            if segment.content_type != current_type:
                sections.append(ContentSection(
                    start=section_start,
                    end=segments[i-1].end,
                    section_type=current_type
                ))
                current_type = segment.content_type
                section_start = segment.start
        
        # Add final section
        sections.append(ContentSection(
            start=section_start,
            end=segments[-1].end,
            section_type=current_type
        ))
        
        return sections
    
    def save_result(self, result: TranscriptionResult, output_path: str):
        """Save transcription result to JSON"""
        output_data = {
            "segments": [asdict(segment) for segment in result.segments],
            "natural_breaks": result.natural_breaks,
            "speaker_changes": result.speaker_changes,
            "content_sections": [asdict(section) for section in result.content_sections],
            "metadata": result.metadata,
            "full_text": result.full_text
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Transcription saved to: {output_path}")

# Convenience function
def transcribe_video(
    video_paths: Union[str, List[str]], 
    config: Optional[TranscriptionConfig] = None
) -> TranscriptionResult:
    """Simple transcription interface"""
    transcriber = SmartTranscriber(config)
    return transcriber.transcribe_video(video_paths)

# Example usage
if __name__ == "__main__":
    config = TranscriptionConfig(
        accuracy_mode=True,
        model_size="base",
        enable_word_timestamps=True
    )
    
    result = transcribe_video("path/to/video.mp4", config)
    print(f"Transcribed {len(result.segments)} segments in {result.metadata['processing_time']}s")