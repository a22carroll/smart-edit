"""
Smart Edit Script Generation Module

Analyzes transcription data and generates intelligent edit scripts using AI.
Creates reviewable edit decisions that users can modify before final export.
"""

import json
import logging
import time
import os
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    logger.warning("OpenAI not available. AI features will be limited.")
    OpenAI = None
    OPENAI_AVAILABLE = False

# Import from transcription module
from transcription import TranscriptionResult, TranscriptSegment

class EditAction(Enum):
    KEEP = "keep"
    REMOVE = "remove"
    SPEED_UP = "speed_up"
    SLOW_DOWN = "slow_down"

class ConfidenceLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class CutDecision:
    """Individual edit decision for a segment"""
    segment_id: int
    start_time: float
    end_time: float
    original_text: str
    action: EditAction
    reason: str
    confidence: ConfidenceLevel
    speed_factor: Optional[float] = None

@dataclass
class TransitionPoint:
    """How to connect two kept segments"""
    from_segment_id: int
    to_segment_id: int
    transition_type: str
    duration: float
    reason: str

@dataclass
class EditScript:
    """Complete edit script with all decisions"""
    cuts: List[CutDecision]
    transitions: List[TransitionPoint]
    estimated_final_duration: float
    original_duration: float
    compression_ratio: float
    metadata: Dict[str, Any]

class ScriptGenerationConfig:
    """Configuration for script generation"""
    def __init__(self, **kwargs):
        # Load from environment with defaults
        self.openai_api_key = kwargs.get('openai_api_key') or os.getenv('OPENAI_API_KEY')
        self.model = kwargs.get('model') or os.getenv('OPENAI_MODEL', 'gpt-4')
        self.target_compression = float(kwargs.get('target_compression') or os.getenv('DEFAULT_COMPRESSION_RATIO', '0.7'))
        self.remove_filler_words = self._get_bool(kwargs, 'remove_filler_words', 'REMOVE_FILLER_WORDS', True)
        self.min_pause_threshold = float(kwargs.get('min_pause_threshold') or os.getenv('MIN_PAUSE_THRESHOLD', '2.0'))
        self.keep_question_segments = self._get_bool(kwargs, 'keep_question_segments', 'KEEP_QUESTION_SEGMENTS', True)
        self.max_speed_increase = float(kwargs.get('max_speed_increase') or os.getenv('DEFAULT_SPEED_INCREASE', '1.3'))
        self.max_tokens = int(kwargs.get('max_tokens') or os.getenv('OPENAI_MAX_TOKENS', '2000'))
        self.temperature = float(kwargs.get('temperature') or os.getenv('OPENAI_TEMPERATURE', '0.3'))
    
    def _get_bool(self, kwargs: dict, key: str, env_key: str, default: bool) -> bool:
        """Helper to get boolean values from kwargs or environment"""
        if key in kwargs:
            return kwargs[key]
        env_val = os.getenv(env_key)
        return env_val.lower() == 'true' if env_val else default

class SmartScriptGenerator:
    """AI-powered script generation for video editing"""
    
    def __init__(self, config: Optional[ScriptGenerationConfig] = None):
        self.config = config or ScriptGenerationConfig()
        self.client = None
        self.ai_enabled = self._setup_openai()
    
    def _setup_openai(self) -> bool:
        """Initialize OpenAI client"""
        if not OPENAI_AVAILABLE or not self.config.openai_api_key:
            logger.warning("OpenAI not available or no API key. Using rule-based generation only.")
            return False
        
        try:
            self.client = OpenAI(api_key=self.config.openai_api_key)
            logger.info(f"OpenAI client initialized with model: {self.config.model}")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client: {e}")
            return False
    
    def generate_script(self, transcription: TranscriptionResult) -> EditScript:
        """Generate complete edit script from transcription"""
        start_time = time.time()
        logger.info(f"Generating edit script for {len(transcription.segments)} segments")
        
        # Analyze content and generate decisions
        content_analysis = self._analyze_content(transcription) if self.ai_enabled else {}
        cut_decisions = self._generate_cut_decisions(transcription, content_analysis)
        transitions = self._generate_transitions(cut_decisions)
        
        # Calculate metrics
        final_duration = self._calculate_final_duration(cut_decisions)
        original_duration = transcription.metadata['total_duration']
        compression_ratio = final_duration / original_duration if original_duration > 0 else 0.0
        
        processing_time = time.time() - start_time
        metadata = {
            "generation_time": round(processing_time, 2),
            "ai_enabled": self.ai_enabled,
            "model_used": self.config.model if self.ai_enabled else "rule_based",
            "segments_analyzed": len(transcription.segments),
            "segments_kept": len([c for c in cut_decisions if c.action == EditAction.KEEP]),
            "segments_removed": len([c for c in cut_decisions if c.action == EditAction.REMOVE])
        }
        
        edit_script = EditScript(
            cuts=cut_decisions,
            transitions=transitions,
            estimated_final_duration=final_duration,
            original_duration=original_duration,
            compression_ratio=compression_ratio,
            metadata=metadata
        )
        
        logger.info(f"Edit script generated: {compression_ratio:.1%} compression in {processing_time:.2f}s")
        return edit_script
    
    def _analyze_content(self, transcription: TranscriptionResult) -> Dict[str, Any]:
        """AI analysis of content importance"""
        try:
            # Prepare segment summaries
            segments = [
                {
                    "id": i,
                    "text": seg.text,
                    "duration": seg.end - seg.start,
                    "content_type": seg.content_type,
                    "contains_filler": seg.contains_filler
                }
                for i, seg in enumerate(transcription.segments[:20])  # Limit for API
            ]
            
            prompt = f"""
Analyze this video transcript for intelligent editing. Return JSON only.

Segments: {json.dumps(segments, indent=2)}

Return:
{{
    "key_segments": [list of segment IDs that are most important],
    "removable_segments": [list of segment IDs that can be safely removed],
    "summary": "brief editing strategy"
}}

Focus on identifying core valuable content vs filler/repetition.
"""
            
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "You are an expert video editor. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}. Using rule-based analysis.")
            return {}
    
    def _generate_cut_decisions(self, transcription: TranscriptionResult, 
                               analysis: Dict) -> List[CutDecision]:
        """Generate edit decisions for each segment"""
        decisions = []
        ai_key_segments = set(analysis.get("key_segments", []))
        ai_removable = set(analysis.get("removable_segments", []))
        
        for i, segment in enumerate(transcription.segments):
            decision = self._analyze_segment(segment, i, ai_key_segments, ai_removable)
            decisions.append(decision)
        
        # Ensure we keep at least some content
        keep_count = len([d for d in decisions if d.action == EditAction.KEEP])
        if keep_count == 0 and decisions:
            decisions[0].action = EditAction.KEEP
            decisions[0].reason = "Forced keep - no other content selected"
            decisions[0].confidence = ConfidenceLevel.LOW
        
        return decisions
    
    def _analyze_segment(self, segment: TranscriptSegment, segment_id: int,
                        ai_key: set, ai_removable: set) -> CutDecision:
        """Analyze individual segment and make edit decision"""
        
        action = EditAction.KEEP
        reason = "Default keep"
        confidence = ConfidenceLevel.MEDIUM
        speed_factor = None
        
        # AI decisions take priority
        if segment_id in ai_key:
            action = EditAction.KEEP
            reason = "AI identified as key content"
            confidence = ConfidenceLevel.HIGH
        elif segment_id in ai_removable:
            action = EditAction.REMOVE
            reason = "AI identified as removable"
            confidence = ConfidenceLevel.MEDIUM
        
        # Rule-based decisions
        elif (self.config.remove_filler_words and segment.contains_filler and 
              segment.content_type not in ["main_point", "topic_introduction"]):
            action = EditAction.REMOVE
            reason = "Contains filler words"
            confidence = ConfidenceLevel.HIGH
        
        elif segment.pause_after > self.config.min_pause_threshold:
            action = EditAction.REMOVE
            reason = f"Long pause ({segment.pause_after:.1f}s)"
            confidence = ConfidenceLevel.HIGH
        
        elif segment.content_type in ["main_point", "topic_introduction", "conclusion"]:
            action = EditAction.KEEP
            reason = f"Important content ({segment.content_type})"
            confidence = ConfidenceLevel.HIGH
        
        elif self.config.keep_question_segments and segment.text.strip().endswith('?'):
            action = EditAction.KEEP
            reason = "Question - likely important"
            confidence = ConfidenceLevel.HIGH
        
        elif segment.speech_rate == "slow" and segment.content_type != "conclusion":
            action = EditAction.SPEED_UP
            speed_factor = min(1.2, self.config.max_speed_increase)
            reason = "Slow speech rate"
            confidence = ConfidenceLevel.MEDIUM
        
        return CutDecision(
            segment_id=segment_id,
            start_time=segment.start,
            end_time=segment.end,
            original_text=segment.text,
            action=action,
            reason=reason,
            confidence=confidence,
            speed_factor=speed_factor
        )
    
    def _generate_transitions(self, decisions: List[CutDecision]) -> List[TransitionPoint]:
        """Generate transitions between kept segments"""
        transitions = []
        kept_segments = [d for d in decisions if d.action in [EditAction.KEEP, EditAction.SPEED_UP]]
        
        for i in range(len(kept_segments) - 1):
            current = kept_segments[i]
            next_segment = kept_segments[i + 1]
            
            time_gap = next_segment.start_time - current.end_time
            
            if time_gap > 1.0:
                transition_type, duration = "fade", 0.5
                reason = "Large time gap between segments"
            elif current.original_text.strip().endswith('.'):
                transition_type, duration = "cut", 0.0
                reason = "Natural sentence boundary"
            else:
                transition_type, duration = "cross_fade", 0.3
                reason = "Smooth content transition"
            
            transitions.append(TransitionPoint(
                from_segment_id=current.segment_id,
                to_segment_id=next_segment.segment_id,
                transition_type=transition_type,
                duration=duration,
                reason=reason
            ))
        
        return transitions
    
    def _calculate_final_duration(self, decisions: List[CutDecision]) -> float:
        """Calculate estimated final duration"""
        final_duration = 0.0
        
        for decision in decisions:
            if decision.action == EditAction.REMOVE:
                continue
            
            segment_duration = decision.end_time - decision.start_time
            
            if decision.speed_factor:
                segment_duration = segment_duration / decision.speed_factor
            
            final_duration += segment_duration
        
        return final_duration
    
    def save_script(self, script: EditScript, output_path: str):
        """Save edit script to JSON file"""
        script_dict = asdict(script)
        
        # Convert enums to strings for JSON serialization
        for cut in script_dict["cuts"]:
            cut["action"] = cut["action"].value
            cut["confidence"] = cut["confidence"].value
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(script_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Edit script saved to: {output_path}")

# Convenience function
def generate_script(transcription: TranscriptionResult, 
                   config: Optional[ScriptGenerationConfig] = None) -> EditScript:
    """Simple interface for script generation"""
    generator = SmartScriptGenerator(config)
    return generator.generate_script(transcription)

# Example usage
if __name__ == "__main__":
    config = ScriptGenerationConfig()
    generator = SmartScriptGenerator(config)
    
    print("Script generation module ready!")
    print(f"AI enabled: {generator.ai_enabled}")
    print(f"Model: {config.model}")
    print(f"Target compression: {config.target_compression}")
    print(f"API key configured: {'Yes' if config.openai_api_key else 'No'}")