"""
Smart Edit Script Generation Module - Fixed and Simplified

Takes transcriptions + user prompt → Creates readable script + timeline data
User-driven instead of automatic analysis.
"""

import json
import logging
import time
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
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
    logger.warning("OpenAI not available. Script generation will use fallback mode.")
    OpenAI = None
    OPENAI_AVAILABLE = False

# Import from transcription module
try:
    from .transcription import TranscriptionResult, TranscriptSegment
except ImportError:
    # Fallback for direct execution
    from transcription import TranscriptionResult, TranscriptSegment

@dataclass
class ScriptSegment:
    """A segment in the final script"""
    start_time: float
    end_time: float
    content: str
    video_index: int  # Which video file this came from (0, 1, 2...)
    original_segment_id: int  # Reference to original transcript segment
    keep: bool = True  # Whether to include in final edit
    reason: str = ""  # Why this segment was selected/modified

@dataclass 
class GeneratedScript:
    """Complete generated script with readable text and timeline data"""
    full_text: str  # The complete readable script for UI display
    segments: List[ScriptSegment]  # Timeline segments with timing data
    title: str  # Generated title for the video
    target_duration_minutes: int  # Target duration requested
    estimated_duration_seconds: float  # Estimated final duration
    original_duration_seconds: float  # Total original duration
    user_prompt: str  # Original user instructions
    metadata: Dict[str, Any]  # Additional information

class ScriptGenerationConfig:
    """Simplified configuration for script generation"""
    def __init__(self, **kwargs):
        # OpenAI settings
        self.openai_api_key = kwargs.get('openai_api_key') or os.getenv('OPENAI_API_KEY')
        self.model = kwargs.get('model') or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.temperature = float(kwargs.get('temperature') or os.getenv('OPENAI_TEMPERATURE', '0.3'))
        self.max_tokens = int(kwargs.get('max_tokens') or os.getenv('OPENAI_MAX_TOKENS', '8000'))
        
        # Default settings
        self.fallback_keep_ratio = float(kwargs.get('fallback_keep_ratio', '0.8'))  # Keep 80% if no AI

class SmartScriptGenerator:
    """User prompt-driven script generation"""
    
    def __init__(self, config: Optional[ScriptGenerationConfig] = None):
        self.config = config or ScriptGenerationConfig()
        self.client = None
        self.ai_enabled = self._setup_openai()
    
    def _setup_openai(self) -> bool:
        """Initialize OpenAI client"""
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI library not installed. Install with: pip install openai")
            return False
            
        if not self.config.openai_api_key:
            logger.warning("No OpenAI API key found. Set OPENAI_API_KEY environment variable.")
            return False
        
        try:
            self.client = OpenAI(api_key=self.config.openai_api_key)
            # Test the client with a simple call
            logger.info(f"OpenAI client initialized successfully with model: {self.config.model}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return False
    
    def _select_important_segments_intelligently(self, all_segments: List[Dict], max_segments: int = 50) -> List[Dict]:
        """
        Intelligently select the most important segments for AI processing
        Provides much better coverage than just taking first/middle/last
        """
        if len(all_segments) <= max_segments:
            return all_segments
        
        total_segments = len(all_segments)
        logger.warning(f"Too many segments ({total_segments}), intelligently selecting {max_segments} most important")
        
        # Strategy: Distribute segments evenly across the video timeline
        # This ensures we get good coverage of the entire content
        
        selected_segments = []
        
        # Calculate step size to distribute evenly
        step_size = total_segments / max_segments
        
        # Select segments at regular intervals
        for i in range(max_segments):
            segment_index = int(i * step_size)
            
            # Ensure we don't go out of bounds
            if segment_index < len(all_segments):
                selected_segments.append(all_segments[segment_index])
        
        # Always include the very first and very last segments (intro/conclusion)
        if len(all_segments) > 2 and max_segments > 2:
            # Replace first selected with actual first segment
            selected_segments[0] = all_segments[0]
            # Replace last selected with actual last segment
            selected_segments[-1] = all_segments[-1]
        
        # Prioritize segments with important content types
        selected_segments = self._boost_important_content_types(selected_segments, all_segments, max_segments)
        
        logger.info(f"Selected {len(selected_segments)} segments evenly distributed across {total_segments} total segments")
        logger.info(f"Coverage: Every ~{step_size:.1f} segments, spanning full video timeline")
        
        return selected_segments

    def _boost_important_content_types(self, current_selection: List[Dict], all_segments: List[Dict], max_segments: int) -> List[Dict]:
        """
        Replace less important segments with more important ones based on content type
        """
        # Define importance levels
        critical_types = ['main_point', 'topic_introduction', 'conclusion']
        important_types = ['transition', 'supporting'] 
        filler_types = ['greeting', 'filler']
        
        # Find critical segments not in current selection
        selected_indices = set()
        for seg in current_selection:
            # Get original index from all_segments
            for i, orig_seg in enumerate(all_segments):
                if (seg.get('text', '') == orig_seg.get('text', '') and 
                    seg.get('start', 0) == orig_seg.get('start', 0)):
                    selected_indices.add(i)
                    break
        
        # Find critical segments we're missing
        missing_critical = []
        for i, seg in enumerate(all_segments):
            if (i not in selected_indices and 
                seg.get('content_type', 'unknown') in critical_types):
                missing_critical.append((i, seg))
        
        # Find filler segments in current selection to replace
        replaceable_indices = []
        for j, seg in enumerate(current_selection):
            if seg.get('content_type', 'unknown') in filler_types:
                replaceable_indices.append(j)
        
        # Replace filler with critical content
        replacements_made = 0
        max_replacements = min(len(missing_critical), len(replaceable_indices), max_segments // 4)
        
        for i in range(max_replacements):
            replace_idx = replaceable_indices[i]
            _, new_segment = missing_critical[i]
            current_selection[replace_idx] = new_segment
            replacements_made += 1
        
        if replacements_made > 0:
            logger.info(f"Boosted {replacements_made} important segments (replaced filler content)")
        
        return current_selection

    def generate_script_from_prompt(self, 
                                   transcriptions: List[TranscriptionResult], 
                                   user_prompt: str,
                                   target_duration_minutes: int = 10) -> GeneratedScript:
        """
        Generate script based on user prompt
        
        Args:
            transcriptions: List of transcription results (one per video file)
            user_prompt: User's instructions for what the video should be about
            target_duration_minutes: Target duration in minutes
        
        Returns:
            GeneratedScript with full text and timeline data
        """
        start_time = time.time()
        logger.info(f"🤖 Generating script from user prompt...")
        logger.info(f"📝 User prompt: {user_prompt[:100]}{'...' if len(user_prompt) > 100 else ''}")
        logger.info(f"🎬 Processing {len(transcriptions)} video(s)")
        
        # Validate inputs
        if not transcriptions:
            raise ValueError("No transcriptions provided")
        if not user_prompt.strip():
            raise ValueError("User prompt cannot be empty")
        if target_duration_minutes <= 0:
            raise ValueError("Target duration must be positive")
        
        # Use AI if available, otherwise fallback
        if self.ai_enabled:
            try:
                script = self._generate_with_ai(transcriptions, user_prompt, target_duration_minutes)
                script.metadata["ai_used"] = True
            except Exception as e:
                logger.error(f"AI generation failed: {e}")
                logger.info("Falling back to rule-based generation")
                script = self._generate_fallback(transcriptions, user_prompt, target_duration_minutes)
                script.metadata["ai_used"] = False
        else:
            script = self._generate_fallback(transcriptions, user_prompt, target_duration_minutes)
            script.metadata["ai_used"] = False
        
        # Add timing metadata
        processing_time = time.time() - start_time
        script.metadata.update({
            "generation_time_seconds": round(processing_time, 2),
            "model_used": self.config.model if self.ai_enabled else "fallback",
            "total_original_segments": sum(len(t.segments) for t in transcriptions),
            "segments_in_script": len(script.segments)
        })
        
        logger.info(f"✅ Script generated in {processing_time:.2f}s")
        logger.info(f"📊 {len(script.segments)} segments selected from {script.metadata['total_original_segments']} total")
        
        return script
    
    def _generate_with_ai(self, transcriptions: List[TranscriptionResult], 
                         user_prompt: str, target_duration: int) -> GeneratedScript:
        """Generate script using AI"""
        
        # Prepare transcript data for AI (limit to avoid token limits)
        all_segments = []
        for video_idx, transcription in enumerate(transcriptions):
            for seg_idx, segment in enumerate(transcription.segments):
                all_segments.append({
                    "video": video_idx,
                    "segment_id": seg_idx,
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                    "duration": round(segment.end - segment.start, 2),
                    "content_type": getattr(segment, 'content_type', 'unknown')
                })
        
        # Limit segments to avoid API token limits with smarter selection
        if len(all_segments) > 50:
            all_segments = self._select_important_segments_intelligently(all_segments, 50) 
        
        # Create AI prompt
        ai_prompt = self._create_ai_prompt(all_segments, user_prompt, target_duration)
        
        # Make API call
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert video editor and scriptwriter. Create engaging, well-structured video scripts based on transcript data and user requirements. Always return valid JSON."
                    },
                    {
                        "role": "user", 
                        "content": ai_prompt
                    }
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
            
            # Parse response
            response_text = response.choices[0].message.content.strip()
            
            # Handle potential JSON formatting issues
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()
            
            ai_result = json.loads(response_text)
            
            # Convert AI response to our format
            return self._convert_ai_response(ai_result, transcriptions, user_prompt, target_duration)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise Exception(f"AI returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"AI API call failed: {e}")
            raise Exception(f"AI generation failed: {e}")
    
    def _create_ai_prompt(self, segments: List[Dict], user_prompt: str, target_duration: int) -> str:
        """Create the prompt for AI script generation"""
    
        total_duration = sum(seg["duration"] for seg in segments)
        target_seconds = target_duration * 60
        
        # Add duration info to each segment for AI clarity
        for seg in segments:
            seg['duration_seconds'] = round(seg.get('duration', seg.get('end', 0) - seg.get('start', 0)), 1)

        return f"""
Create a {target_duration}-minute video script based ONLY on the transcript segments below.

USER INSTRUCTIONS:
"{user_prompt}"

TARGET DURATION: {target_duration} minutes ({target_seconds} seconds)
AVAILABLE CONTENT: {total_duration:.1f} minutes across {len(segments)} segments

DURATION REQUIREMENTS:
- You must select segments that total {target_seconds} seconds (±30 seconds acceptable)
- Each segment shows its duration_seconds - use this to calculate your running total
- Focus on TOTAL DURATION of selected content, not segment count
- Keep adding segments until you reach {target_seconds} seconds total

TRANSCRIPT SEGMENTS:
{json.dumps(segments, indent=2)}

Return JSON with this structure:
{{
    "title": "Title based on actual content",
    "script_text": "Clean narrative script using ONLY actual segment content",
    "selected_segments": [
        {{
            "video": 0,
            "segment_id": 0,
            "start_time": 0.0,
            "end_time": 15.5,
            "content": "EXACT text from the original segment (minimal editing only)",
            "reason": "Why this segment was selected"
        }}
    ]
}}

CRITICAL CONTENT RULES:
1. Use ONLY words that exist in the transcript segments
2. Do NOT create new sentences or invented connections
3. Do NOT make speakers reference each other unless they actually did
4. Do NOT add smooth transitions if they don't exist in the source
5. Keep original phrasing and meaning intact
6. Remove interviewer questions and production notes only
7. NEVER fabricate content, quotes, or connections

SEGMENT SELECTION RULES:
8. Select segments that total approximately {target_seconds} seconds
9. Calculate running duration total as you select segments
10. Include content from all speakers mentioned in user instructions
11. Structure: intro segments → mission/importance → community impact → conclusion
12. Use actual start_time/end_time from segments (no fake timestamps)

SCRIPT FORMAT:
13. Use actual timestamps from selected segments
14. Present content in chronological order of selected segments
15. Minimal editing - preserve authentic voice and meaning
16. Remove only questions and production artifacts
17. If segments don't flow perfectly, that's acceptable - don't invent content

VALIDATION CHECKLIST:
- Total duration of selected_segments = {target_seconds}s (±30s) ✓
- Every sentence traces back to actual segment content ✓  
- No fabricated connections between speakers ✓
- Using real timestamps, not artificial ones ✓
- Preserved authentic voice and meaning ✓

Return only valid JSON. Do not create content that doesn't exist in the source material.
"""

    def _convert_ai_response(self, ai_result: Dict, transcriptions: List[TranscriptionResult], 
                           user_prompt: str, target_duration: int) -> GeneratedScript:
        """Convert AI response to GeneratedScript format"""
        
        # Validate AI response structure
        required_keys = ["title", "script_text", "selected_segments"]
        for key in required_keys:
            if key not in ai_result:
                raise ValueError(f"AI response missing required key: {key}")
        
        # Convert selected segments
        script_segments = []
        estimated_duration = 0.0
        
        for selected in ai_result.get("selected_segments", []):
            try:
                segment = ScriptSegment(
                    start_time=float(selected["start_time"]),
                    end_time=float(selected["end_time"]),
                    content=selected["content"].strip(),
                    video_index=int(selected["video"]),
                    original_segment_id=int(selected["segment_id"]),
                    keep=True,
                    reason=selected.get("reason", "Selected by AI")
                )
                script_segments.append(segment)
                estimated_duration += segment.end_time - segment.start_time
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid segment in AI response: {e}")
                continue
        
        # Calculate original duration
        original_duration = sum(t.metadata.get('total_duration', 0) for t in transcriptions)
        
        return GeneratedScript(
            full_text=ai_result["script_text"],
            segments=script_segments,
            title=ai_result["title"],
            target_duration_minutes=target_duration,
            estimated_duration_seconds=estimated_duration,
            original_duration_seconds=original_duration,
            user_prompt=user_prompt,
            metadata={
                "ai_model": self.config.model,
                "video_count": len(transcriptions),
                "compression_ratio": estimated_duration / original_duration if original_duration > 0 else 0.0
            }
        )
    
    def _generate_fallback(self, transcriptions: List[TranscriptionResult], 
                          user_prompt: str, target_duration: int) -> GeneratedScript:
        """Fallback script generation when AI is not available"""
        
        logger.info("Using fallback script generation (no AI)")
        
        # Collect all segments
        all_segments = []
        script_text_parts = [f"# Video Script\n\n**User Request:** {user_prompt}\n\n"]
        
        total_duration = 0.0
        for video_idx, transcription in enumerate(transcriptions):
            total_duration += transcription.metadata.get('total_duration', 0)
            
            if len(transcriptions) > 1:
                script_text_parts.append(f"\n## Video {video_idx + 1}\n")
            
            for seg_idx, segment in enumerate(transcription.segments):
                # Simple selection: keep segments that seem important
                keep_segment = self._should_keep_segment_fallback(segment)
                
                if keep_segment:
                    script_segment = ScriptSegment(
                        start_time=segment.start,
                        end_time=segment.end,
                        content=segment.text.strip(),
                        video_index=video_idx,
                        original_segment_id=seg_idx,
                        keep=True,
                        reason="Fallback selection"
                    )
                    all_segments.append(script_segment)
                    
                    # Add to script text with timestamp
                    minutes = int(segment.start // 60)
                    seconds = int(segment.start % 60)
                    script_text_parts.append(f"**[{minutes}:{seconds:02d}]** {segment.text.strip()}\n")
        
        # Ensure we don't have too many segments for target duration
        target_seconds = target_duration * 60
        if all_segments:
            current_duration = sum(seg.end_time - seg.start_time for seg in all_segments)
            if current_duration > target_seconds * 1.2:  # 20% over target
                # Keep only the first segments to fit roughly in target
                keep_ratio = (target_seconds * 1.1) / current_duration
                keep_count = max(1, int(len(all_segments) * keep_ratio))
                all_segments = all_segments[:keep_count]
                logger.info(f"Reduced segments to {keep_count} to fit target duration")
        
        full_script_text = "".join(script_text_parts)
        estimated_duration = sum(seg.end_time - seg.start_time for seg in all_segments)
        
        return GeneratedScript(
            full_text=full_script_text,
            segments=all_segments,
            title="Video Script (Auto-Generated)",
            target_duration_minutes=target_duration,
            estimated_duration_seconds=estimated_duration,
            original_duration_seconds=total_duration,
            user_prompt=user_prompt,
            metadata={
                "video_count": len(transcriptions),
                "compression_ratio": estimated_duration / total_duration if total_duration > 0 else 0.0,
                "fallback_used": True
            }
        )
    
    def _should_keep_segment_fallback(self, segment: TranscriptSegment) -> bool:
        """Simple logic for keeping segments when AI is not available"""
        
        # Keep segments that seem important
        text = segment.text.lower().strip()
        
        # Skip very short segments
        if len(text) < 10:
            return False
        
        # Skip segments that are mostly filler
        filler_ratio = sum(1 for word in ['um', 'uh', 'like', 'you know', 'so', 'well'] if word in text) / max(1, len(text.split()))
        if filler_ratio > 0.3:
            return False
        
        # Keep segments with questions
        if text.endswith('?'):
            return True
        
        # Keep segments that seem like main content
        important_words = ['important', 'key', 'main', 'first', 'second', 'next', 'finally', 'conclusion']
        if any(word in text for word in important_words):
            return True
        
        # Keep segments of reasonable length
        if 5 <= len(text.split()) <= 50:
            return True
        
        # Default: keep most segments (fallback is permissive)
        return len(text.split()) > 3
    
    def save_script(self, script: GeneratedScript, output_path: str):
        """Save generated script to JSON file"""
        try:
            script_dict = asdict(script)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(script_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Script saved to: {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to save script to {output_path}: {e}")
            raise

# Convenience functions for easy use
def generate_script_from_prompt(transcriptions: List[TranscriptionResult], 
                               user_prompt: str,
                               target_duration_minutes: int = 10,
                               config: Optional[ScriptGenerationConfig] = None) -> GeneratedScript:
    """
    Simple interface for prompt-driven script generation
    
    Args:
        transcriptions: List of transcription results (one per video)
        user_prompt: User's instructions for what the video should be about
        target_duration_minutes: Target duration in minutes
        config: Optional configuration settings
    
    Returns:
        GeneratedScript with full text and timeline data
    """
    generator = SmartScriptGenerator(config)
    return generator.generate_script_from_prompt(transcriptions, user_prompt, target_duration_minutes)

# Legacy compatibility function
def generate_script(transcription: TranscriptionResult, 
                   target_compression: float = 0.7,
                   user_prompt: str = "Create an engaging video") -> GeneratedScript:
    """
    Legacy compatibility function - converts old interface to new
    """
    logger.warning("Using legacy generate_script function. Consider switching to generate_script_from_prompt")
    
    # Convert target_compression to target_duration
    original_duration_minutes = transcription.metadata.get('total_duration', 600) / 60
    target_duration = max(1, int(original_duration_minutes * target_compression))
    
    return generate_script_from_prompt([transcription], user_prompt, target_duration)

# Example usage and testing
if __name__ == "__main__":
    print("Smart Edit Script Generation - Fixed Version")
    print("=" * 50)
    
    # Test configuration
    config = ScriptGenerationConfig()
    generator = SmartScriptGenerator(config)
    
    print(f"AI enabled: {generator.ai_enabled}")
    print(f"Model: {config.model}")
    print(f"API key configured: {'Yes' if config.openai_api_key else 'No'}")
    
    print("\nUsage:")
    print("script = generate_script_from_prompt(transcriptions, 'Your prompt here', 10)")
    print("print(script.full_text)  # Show the readable script")
    print("print(len(script.segments))  # Show number of timeline segments")