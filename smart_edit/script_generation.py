"""
Smart Edit Script Generation Module

Analyzes transcription data and generates intelligent edit scripts using AI.
Creates reviewable edit decisions that users can modify before final export.
"""

import json
import logging
import time
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

try:
    import openai
    from openai import OpenAI
except ImportError:
    openai = None
    OpenAI = None

# Import from transcription module
from transcription import TranscriptionResult, TranscriptSegment

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EditAction(Enum):
    """Types of edit actions"""
    KEEP = "keep"
    REMOVE = "remove"
    SPEED_UP = "speed_up"
    SLOW_DOWN = "slow_down"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"

class ConfidenceLevel(Enum):
    """AI confidence levels"""
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
    speed_factor: Optional[float] = None  # For speed adjustments (1.0 = normal, 1.5 = 50% faster)
    fade_duration: Optional[float] = None  # For fade effects in seconds

@dataclass
class TransitionPoint:
    """How to connect two kept segments"""
    from_segment_id: int
    to_segment_id: int
    transition_type: str  # "cut", "fade", "cross_fade"
    duration: float  # Transition duration in seconds
    reason: str

@dataclass
class PacingAdjustment:
    """Pacing modification for content flow"""
    segment_id: int
    original_duration: float
    suggested_duration: float
    speed_factor: float
    reason: str

@dataclass
class EditScript:
    """Complete edit script with all decisions"""
    cuts: List[CutDecision]
    transitions: List[TransitionPoint]
    pacing_adjustments: List[PacingAdjustment]
    estimated_final_duration: float
    original_duration: float
    compression_ratio: float  # Final duration / Original duration
    metadata: Dict[str, Any]

class ScriptGenerationConfig:
    """Configuration for script generation"""
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4",
        target_compression: float = 0.7,  # Target 70% of original length
        remove_filler_words: bool = True,
        remove_long_pauses: bool = True,
        min_pause_threshold: float = 2.0,  # Remove pauses longer than 2 seconds
        keep_question_segments: bool = True,
        prioritize_main_points: bool = True,
        max_speed_increase: float = 1.3,  # Maximum 30% speed increase
        enable_transitions: bool = True,
        confidence_threshold: float = 0.7  # Minimum confidence for auto-decisions
    ):
        self.openai_api_key = openai_api_key
        self.model = model
        self.target_compression = target_compression
        self.remove_filler_words = remove_filler_words
        self.remove_long_pauses = remove_long_pauses
        self.min_pause_threshold = min_pause_threshold
        self.keep_question_segments = keep_question_segments
        self.prioritize_main_points = prioritize_main_points
        self.max_speed_increase = max_speed_increase
        self.enable_transitions = enable_transitions
        self.confidence_threshold = confidence_threshold

class SmartScriptGenerator:
    """AI-powered script generation for video editing"""
    
    def __init__(self, config: Optional[ScriptGenerationConfig] = None):
        self.config = config or ScriptGenerationConfig()
        self._setup_openai()
    
    def _setup_openai(self):
        """Initialize OpenAI client"""
        if not openai or not OpenAI:
            logger.warning("OpenAI not installed. AI features will be limited.")
            self.ai_enabled = False
            self.client = None
            return
        
        if self.config.openai_api_key:
            try:
                self.client = OpenAI(api_key=self.config.openai_api_key)
                self.ai_enabled = True
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
                self.ai_enabled = False
                self.client = None
        else:
            logger.warning("No OpenAI API key provided. Using rule-based generation only.")
            self.ai_enabled = False
            self.client = None
    
    def generate_script(self, transcription: TranscriptionResult) -> EditScript:
        """
        Generate complete edit script from transcription
        
        Args:
            transcription: Output from transcription module
            
        Returns:
            EditScript with all edit decisions
        """
        start_time = time.time()
        logger.info(f"Generating edit script for {len(transcription.segments)} segments")
        
        # Step 1: Analyze content with AI (if available)
        content_analysis = self._analyze_content(transcription)
        
        # Step 2: Generate cut decisions
        cut_decisions = self._generate_cut_decisions(transcription, content_analysis)
        
        # Step 3: Create transitions between kept segments
        transitions = self._generate_transitions(cut_decisions, transcription)
        
        # Step 4: Suggest pacing adjustments
        pacing_adjustments = self._generate_pacing_adjustments(cut_decisions, transcription)
        
        # Step 5: Calculate final metrics
        final_duration, compression_ratio = self._calculate_duration_metrics(
            cut_decisions, transcription.metadata['total_duration']
        )
        
        processing_time = time.time() - start_time
        metadata = {
            "generation_time": round(processing_time, 2),
            "ai_enabled": self.ai_enabled,
            "model_used": self.config.model if self.ai_enabled else "rule_based",
            "segments_analyzed": len(transcription.segments),
            "segments_kept": len([c for c in cut_decisions if c.action == EditAction.KEEP]),
            "segments_removed": len([c for c in cut_decisions if c.action == EditAction.REMOVE]),
            "high_confidence_decisions": len([c for c in cut_decisions if c.confidence == ConfidenceLevel.HIGH])
        }
        
        edit_script = EditScript(
            cuts=cut_decisions,
            transitions=transitions,
            pacing_adjustments=pacing_adjustments,
            estimated_final_duration=final_duration,
            original_duration=transcription.metadata['total_duration'],
            compression_ratio=compression_ratio,
            metadata=metadata
        )
        
        logger.info(f"Edit script generated: {compression_ratio:.1%} compression in {processing_time:.2f}s")
        return edit_script
    
    def _analyze_content(self, transcription: TranscriptionResult) -> Dict[str, Any]:
        """Analyze content to understand structure and importance"""
        if not self.ai_enabled or not self.client:
            return self._rule_based_content_analysis(transcription)
        
        try:
            # Prepare content for AI analysis
            full_text = transcription.full_text
            segment_summaries = []
            
            for i, segment in enumerate(transcription.segments):
                segment_summaries.append({
                    "id": i,
                    "text": segment.text,
                    "duration": segment.end - segment.start,
                    "content_type": segment.content_type,
                    "contains_filler": segment.contains_filler,
                    "speech_rate": segment.speech_rate
                })
            
            prompt = self._create_content_analysis_prompt(full_text, segment_summaries)
            
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "You are an expert video editor analyzing content for intelligent editing."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            analysis = json.loads(response.choices[0].message.content)
            logger.info("AI content analysis completed")
            return analysis
            
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}. Falling back to rule-based analysis.")
            return self._rule_based_content_analysis(transcription)
    
    def _rule_based_content_analysis(self, transcription: TranscriptionResult) -> Dict[str, Any]:
        """Fallback content analysis using rules"""
        important_segments = []
        filler_segments = []
        transition_segments = []
        
        for i, segment in enumerate(transcription.segments):
            if segment.content_type in ["main_point", "topic_introduction"]:
                important_segments.append(i)
            elif segment.contains_filler or segment.content_type == "supporting":
                filler_segments.append(i)
            elif segment.content_type == "transition":
                transition_segments.append(i)
        
        return {
            "key_segments": important_segments,
            "removable_segments": filler_segments,
            "transition_segments": transition_segments,
            "overall_quality": "medium",
            "main_topics": ["general_content"],
            "pacing_issues": []
        }
    
    def _create_content_analysis_prompt(self, full_text: str, segments: List[Dict]) -> str:
        """Create prompt for AI content analysis"""
        return f"""
Analyze this video transcript for intelligent editing. The video has {len(segments)} segments.

Full transcript:
{full_text[:2000]}...

Segment details:
{json.dumps(segments[:10], indent=2)}...

Please analyze and return a JSON response with:
{{
    "key_segments": [list of segment IDs that are most important to keep],
    "removable_segments": [list of segment IDs that can be safely removed],
    "transition_segments": [list of segment IDs that are transitions],
    "overall_quality": "high/medium/low",
    "main_topics": [list of main topics discussed],
    "pacing_issues": [list of segment IDs with pacing problems],
    "summary": "brief summary of content and editing strategy"
}}

Focus on identifying:
1. Core valuable content that must be kept
2. Filler content, repetition, or low-value segments
3. Natural transition points
4. Overall content flow and pacing
"""
    
    def _generate_cut_decisions(self, transcription: TranscriptionResult, analysis: Dict) -> List[CutDecision]:
        """Generate cut decisions for each segment"""
        decisions = []
        
        for i, segment in enumerate(transcription.segments):
            decision = self._analyze_segment(segment, i, analysis, transcription.natural_breaks)
            decisions.append(decision)
        
        # Apply global rules and optimizations
        decisions = self._optimize_decisions(decisions, transcription)
        
        # Validate decisions
        decisions = self._validate_decisions(decisions, transcription)
        
        return decisions
    
    def _validate_decisions(self, decisions: List[CutDecision], 
                           transcription: TranscriptionResult) -> List[CutDecision]:
        """Validate and fix any problematic decisions"""
        
        # Ensure we have at least some content to keep
        keep_count = len([d for d in decisions if d.action == EditAction.KEEP])
        if keep_count == 0:
            logger.warning("No segments marked for keeping. Forcing first segment to be kept.")
            if decisions:
                decisions[0].action = EditAction.KEEP
                decisions[0].reason = "Forced keep - no other content selected"
                decisions[0].confidence = ConfidenceLevel.LOW
        
        # Validate timing consistency
        for i, decision in enumerate(decisions):
            if decision.start_time >= decision.end_time:
                logger.warning(f"Invalid timing in segment {i}: start >= end")
                decision.end_time = decision.start_time + 0.1  # Minimum duration
        
        return decisions
    
    def _analyze_segment(self, segment: TranscriptSegment, segment_id: int, 
                        analysis: Dict, natural_breaks: List[float]) -> CutDecision:
        """Analyze individual segment and make edit decision"""
        
        # Default decision
        action = EditAction.KEEP
        reason = "Default keep"
        confidence = ConfidenceLevel.MEDIUM
        speed_factor = 1.0
        
        # Rule-based decision making
        
        # Remove segments with excessive filler words
        if (self.config.remove_filler_words and segment.contains_filler and 
            segment.content_type not in ["main_point", "topic_introduction"]):
            action = EditAction.REMOVE
            reason = "Contains filler words"
            confidence = ConfidenceLevel.HIGH
        
        # Remove long pauses
        elif (self.config.remove_long_pauses and 
              segment.pause_after > self.config.min_pause_threshold):
            action = EditAction.REMOVE
            reason = f"Long pause ({segment.pause_after:.1f}s)"
            confidence = ConfidenceLevel.HIGH
        
        # Keep important content
        elif segment.content_type in ["main_point", "topic_introduction", "conclusion"]:
            action = EditAction.KEEP
            reason = f"Important content ({segment.content_type})"
            confidence = ConfidenceLevel.HIGH
        
        # Keep questions
        elif self.config.keep_question_segments and segment.text.strip().endswith('?'):
            action = EditAction.KEEP
            reason = "Question - likely important"
            confidence = ConfidenceLevel.HIGH
        
        # Speed up slow sections
        elif segment.speech_rate == "slow" and segment.content_type != "conclusion":
            action = EditAction.SPEED_UP
            speed_factor = min(1.2, self.config.max_speed_increase)
            reason = "Slow speech rate"
            confidence = ConfidenceLevel.MEDIUM
        
        # AI-based decisions (if available)
        if segment_id in analysis.get("key_segments", []):
            action = EditAction.KEEP
            reason = "AI identified as key content"
            confidence = ConfidenceLevel.HIGH
        elif segment_id in analysis.get("removable_segments", []):
            action = EditAction.REMOVE
            reason = "AI identified as removable"
            confidence = ConfidenceLevel.MEDIUM
        
        return CutDecision(
            segment_id=segment_id,
            start_time=segment.start,
            end_time=segment.end,
            original_text=segment.text,
            action=action,
            reason=reason,
            confidence=confidence,
            speed_factor=speed_factor if action in [EditAction.SPEED_UP, EditAction.SLOW_DOWN] else None
        )
    
    def _optimize_decisions(self, decisions: List[CutDecision], 
                          transcription: TranscriptionResult) -> List[CutDecision]:
        """Apply global optimizations to decisions"""
        
        # Ensure we don't remove too much content
        keep_ratio = len([d for d in decisions if d.action == EditAction.KEEP]) / len(decisions)
        
        if keep_ratio < 0.3:  # If keeping less than 30%, be more conservative
            logger.warning("Very aggressive cutting detected. Making decisions more conservative.")
            for decision in decisions:
                if (decision.action == EditAction.REMOVE and 
                    decision.confidence != ConfidenceLevel.HIGH):
                    decision.action = EditAction.KEEP
                    decision.reason += " (conservative adjustment)"
                    decision.confidence = ConfidenceLevel.LOW
        
        # Ensure we have smooth transitions
        decisions = self._ensure_smooth_transitions(decisions)
        
        return decisions
    
    def _ensure_smooth_transitions(self, decisions: List[CutDecision]) -> List[CutDecision]:
        """Ensure we don't create jarring cuts"""
        
        for i in range(len(decisions) - 1):
            current = decisions[i]
            next_decision = decisions[i + 1]
            
            # If we're cutting from one kept segment to another, 
            # ensure there's not a jarring content jump
            if (current.action == EditAction.KEEP and 
                next_decision.action == EditAction.KEEP):
                
                # Add fade out/in for content type changes
                if (current.original_text.strip().endswith('.') and 
                    len(next_decision.original_text) > 0 and
                    next_decision.original_text[0].isupper()):
                    # Create new decisions for fades instead of modifying action
                    current.fade_duration = 0.3
                    next_decision.fade_duration = 0.3
        
        return decisions
    
    def _generate_transitions(self, decisions: List[CutDecision], 
                            transcription: TranscriptionResult) -> List[TransitionPoint]:
        """Generate transition points between kept segments"""
        if not self.config.enable_transitions:
            return []
        
        transitions = []
        kept_segments = [d for d in decisions if d.action in [EditAction.KEEP, EditAction.SPEED_UP, EditAction.SLOW_DOWN]]
        
        for i in range(len(kept_segments) - 1):
            current = kept_segments[i]
            next_segment = kept_segments[i + 1]
            
            # Determine transition type based on content
            time_gap = next_segment.start_time - current.end_time
            if time_gap > 1.0:
                transition_type = "fade"
                duration = 0.5
                reason = "Large time gap between segments"
            elif current.original_text.strip().endswith('.'):
                transition_type = "cut"
                duration = 0.0
                reason = "Natural sentence boundary"
            else:
                transition_type = "cross_fade"
                duration = 0.3
                reason = "Smooth content transition"
            
            transitions.append(TransitionPoint(
                from_segment_id=current.segment_id,
                to_segment_id=next_segment.segment_id,
                transition_type=transition_type,
                duration=duration,
                reason=reason
            ))
        
        return transitions
    
    def _generate_pacing_adjustments(self, decisions: List[CutDecision], 
                                   transcription: TranscriptionResult) -> List[PacingAdjustment]:
        """Generate pacing adjustment suggestions"""
        adjustments = []
        
        for decision in decisions:
            if decision.action in [EditAction.SPEED_UP, EditAction.SLOW_DOWN]:
                original_duration = decision.end_time - decision.start_time
                speed_factor = decision.speed_factor or 1.0
                new_duration = original_duration / speed_factor
                
                adjustments.append(PacingAdjustment(
                    segment_id=decision.segment_id,
                    original_duration=original_duration,
                    suggested_duration=new_duration,
                    speed_factor=speed_factor,
                    reason=decision.reason
                ))
        
        return adjustments
    
    def _calculate_duration_metrics(self, decisions: List[CutDecision], 
                                  original_duration: float) -> Tuple[float, float]:
        """Calculate final duration and compression ratio"""
        final_duration = 0.0
        
        for decision in decisions:
            if decision.action == EditAction.REMOVE:
                continue
            
            segment_duration = decision.end_time - decision.start_time
            
            if decision.action in [EditAction.SPEED_UP, EditAction.SLOW_DOWN]:
                speed_factor = decision.speed_factor or 1.0
                segment_duration = segment_duration / speed_factor
            
            final_duration += segment_duration
        
        compression_ratio = final_duration / original_duration if original_duration > 0 else 0
        
        return final_duration, compression_ratio
    
    def save_script(self, script: EditScript, output_path: str):
        """Save edit script to JSON file"""
        # Convert dataclasses to dictionaries for JSON serialization
        script_dict = {
            "cuts": [asdict(cut) for cut in script.cuts],
            "transitions": [asdict(transition) for transition in script.transitions],
            "pacing_adjustments": [asdict(adjustment) for adjustment in script.pacing_adjustments],
            "estimated_final_duration": script.estimated_final_duration,
            "original_duration": script.original_duration,
            "compression_ratio": script.compression_ratio,
            "metadata": script.metadata
        }
        
        # Convert enums to strings for JSON serialization
        for cut in script_dict["cuts"]:
            if hasattr(cut["action"], 'value'):
                cut["action"] = cut["action"].value
            elif isinstance(cut["action"], EditAction):
                cut["action"] = cut["action"].value
            
            if hasattr(cut["confidence"], 'value'):
                cut["confidence"] = cut["confidence"].value
            elif isinstance(cut["confidence"], ConfidenceLevel):
                cut["confidence"] = cut["confidence"].value
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(script_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Edit script saved to: {output_path}")

# Convenience function
def generate_script(transcription: TranscriptionResult, 
                   config: Optional[ScriptGenerationConfig] = None) -> EditScript:
    """
    Simple interface for script generation
    
    Args:
        transcription: Output from transcription module
        config: Optional configuration
        
    Returns:
        EditScript with all edit decisions
    """
    generator = SmartScriptGenerator(config)
    return generator.generate_script(transcription)

# Example usage
if __name__ == "__main__":
    # Example configuration
    config = ScriptGenerationConfig(
        target_compression=0.75,  # Keep 75% of content
        remove_filler_words=True,
        min_pause_threshold=1.5,
        max_speed_increase=1.25
    )
    
    # This would typically come from transcription module
    # result = transcribe_video("video.mp4")
    # script = generate_script(result, config)
    
    print("Script generation module ready!")
    print(f"AI enabled: {SmartScriptGenerator().ai_enabled}")