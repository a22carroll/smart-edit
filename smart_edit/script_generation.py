"""
Smart Edit Script Generation - Ultra Simple Version

Just text in → AI cleans it → text out → map to segments
Focused on reliability over complexity.
"""

import json
import logging
import time
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    logger.warning("OpenAI not available - will use fallback mode")
    OpenAI = None
    OPENAI_AVAILABLE = False

# Simple fallback classes if transcription module missing
try:
    from .transcription import TranscriptionResult, TranscriptSegment
except ImportError:
    try:
        from transcription import TranscriptionResult, TranscriptSegment
    except ImportError:
        @dataclass
        class TranscriptSegment:
            start: float
            end: float
            text: str
            speaker: str = "Speaker_1"
        
        @dataclass 
        class TranscriptionResult:
            segments: List[TranscriptSegment]
            metadata: Dict[str, Any]
            full_text: str = ""

@dataclass
class ScriptSegment:
    start_time: float
    end_time: float  
    content: str
    video_index: int
    original_segment_id: int
    keep: bool = True
    reason: str = "Selected"

@dataclass
class GeneratedScript:
    full_text: str
    segments: List[ScriptSegment]
    title: str
    target_duration_minutes: int
    estimated_duration_seconds: float
    original_duration_seconds: float
    user_prompt: str
    metadata: Dict[str, Any]

class SmartScriptGenerator:
    """Ultra-simple script generator"""
    
    def __init__(self, openai_api_key: str = None, model: str = "gpt-4o-mini"):
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.model = model
        self.client = None
        self.ai_ready = self._setup_ai()
    
    def _setup_ai(self) -> bool:
        """Setup AI client"""
        if not OPENAI_AVAILABLE or not self.api_key:
            return False
        try:
            self.client = OpenAI(api_key=self.api_key)
            return True
        except Exception as e:
            logger.error(f"AI setup failed: {e}")
            return False
    
    def generate_script(self, transcriptions: List[TranscriptionResult], 
                       user_prompt: str, target_minutes: int = 10) -> GeneratedScript:
        """Main generation function"""
        
        logger.info(f"Generating {target_minutes}min script: '{user_prompt[:50]}...'")
        
        # Step 1: Get all text
        full_text = self._get_text(transcriptions)
        if len(full_text) < 20:
            raise ValueError("Not enough text to work with")
        
        # Step 2: Generate script 
        if self.ai_ready:
            try:
                title, script_text = self._ai_generate(full_text, user_prompt, target_minutes)
                logger.info("✅ AI generation successful")
            except Exception as e:
                logger.error(f"AI failed: {e}")
                title, script_text = self._fallback_generate(full_text, user_prompt)
        else:
            title, script_text = self._fallback_generate(full_text, user_prompt)
        
        # Step 3: Map to segments
        segments = self._map_to_segments(script_text, transcriptions, target_minutes)
        
        # Step 4: Calculate stats
        original_duration = sum(self._get_duration(t) for t in transcriptions)
        estimated_duration = sum(s.end_time - s.start_time for s in segments)
        
        return GeneratedScript(
            full_text=script_text,
            segments=segments,
            title=title,
            target_duration_minutes=target_minutes,
            estimated_duration_seconds=estimated_duration,
            original_duration_seconds=original_duration,
            user_prompt=user_prompt,
            metadata={
                "ai_used": self.ai_ready,
                "segment_count": len(segments),
                "compression_ratio": estimated_duration / max(original_duration, 1)
            }
        )
    
    def _get_text(self, transcriptions: List[TranscriptionResult]) -> str:
        """Extract clean text from transcriptions"""
        texts = []
        
        for i, trans in enumerate(transcriptions):
            # Try full_text first, then combine segments
            if hasattr(trans, 'full_text') and trans.full_text:
                text = trans.full_text.strip()
            else:
                text = " ".join(seg.text.strip() for seg in trans.segments if seg.text.strip())
            
            if text:
                if len(transcriptions) > 1:
                    texts.append(f"[Video {i+1}] {text}")
                else:
                    texts.append(text)
        
        full_text = "\n\n".join(texts)
        
        # Limit length (roughly 2500 words to stay under token limits)
        words = full_text.split()
        if len(words) > 2500:
            logger.warning(f"Text too long ({len(words)} words), cutting to 2500")
            full_text = " ".join(words[:2500])
        
        return full_text
    
    def _ai_generate(self, text: str, prompt: str, minutes: int) -> tuple[str, str]:
        """Generate using AI"""
        
        ai_prompt = f"""Clean up this video transcript based on the user's request. DO NOT CREATE NEW CONTENT.

USER REQUEST: {prompt}

ORIGINAL TRANSCRIPT:
{text}

STRICT RULES:
- Use ONLY words and sentences that exist in the transcript
- DO NOT add scene directions, transitions, or stage directions
- DO NOT invent quotes or paraphrase beyond minor cleanup
- DO NOT add speaker introductions that aren't in the original
- DO NOT create organized segments if they don't exist
- Just clean up filler words and organize the existing content
- If speakers didn't actually interact, don't make them interact

Your job is to EDIT the existing content, not CREATE new content.

Format:
TITLE: [brief title based on actual content]
SCRIPT: [cleaned version of actual transcript content only]"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a video editor. Clean up transcripts into engaging scripts."},
                {"role": "user", "content": ai_prompt}
            ],
            temperature=0.3,
            max_tokens=3000
        )
        
        result = response.choices[0].message.content.strip()
        return self._parse_response(result)
    
    def _parse_response(self, response: str) -> tuple[str, str]:
        """Parse AI response into title and script"""
        
        lines = response.split('\n')
        title = "Generated Script"
        script_lines = []
        
        found_script = False
        for line in lines:
            line = line.strip()
            if line.upper().startswith('TITLE:'):
                title = line[6:].strip()
            elif line.upper().startswith('SCRIPT:'):
                found_script = True
            elif found_script or (not any(x in line.upper() for x in ['TITLE:', 'SCRIPT:'])):
                if line:
                    script_lines.append(line)
        
        script = '\n'.join(script_lines).strip()
        if not script:
            script = response  # Fallback to full response
        
        return title[:100], script
    
    def _fallback_generate(self, text: str, prompt: str) -> tuple[str, str]:
        """Simple fallback when AI not available"""
        
        logger.info("Using fallback generation")
        
        # Basic cleanup
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('[Video'):
                # Remove excessive filler
                words = line.split()
                clean_words = [w for w in words if w.lower() not in ['um', 'uh'] * 5]
                if clean_words:
                    clean_lines.append(' '.join(clean_words))
        
        script = '\n\n'.join(clean_lines)
        title = "Video Script"
        
        return title, script
    
    def _map_to_segments(self, script: str, transcriptions: List[TranscriptionResult], 
                        target_minutes: int) -> List[ScriptSegment]:
        """Map script back to original segments"""
        
        # Get all original segments
        all_segs = []
        for vid_idx, trans in enumerate(transcriptions):
            for seg_idx, seg in enumerate(trans.segments):
                all_segs.append((vid_idx, seg_idx, seg))
        
        if not all_segs:
            return []
        
        # Calculate how many segments we need
        target_seconds = target_minutes * 60
        total_duration = sum(seg.end - seg.start for _, _, seg in all_segs)
        
        if total_duration > 0:
            keep_ratio = min(1.0, target_seconds / total_duration)
            target_count = max(1, int(len(all_segs) * keep_ratio))
        else:
            target_count = len(all_segs) // 2
        
        # Select segments evenly distributed
        selected = []
        if target_count >= len(all_segs):
            selected = all_segs
        else:
            step = len(all_segs) / target_count
            for i in range(target_count):
                idx = min(int(i * step), len(all_segs) - 1)
                selected.append(all_segs[idx])
        
        # Split script into chunks
        script_parts = self._split_script(script, len(selected))
        
        # Create script segments
        segments = []
        for i, (vid_idx, seg_idx, orig_seg) in enumerate(selected):
            content = script_parts[i] if i < len(script_parts) else orig_seg.text
            
            segments.append(ScriptSegment(
                start_time=orig_seg.start,
                end_time=orig_seg.end,
                content=content,
                video_index=vid_idx,
                original_segment_id=seg_idx,
                keep=True,
                reason="Mapped from script"
            ))
        
        return segments
    
    def _split_script(self, script: str, num_parts: int) -> List[str]:
        """Split script into roughly equal parts"""
        if num_parts <= 1:
            return [script]
        
        # Split by sentences first
        sentences = []
        for chunk in script.split('.'):
            chunk = chunk.strip()
            if chunk:
                sentences.append(chunk + '.')
        
        if len(sentences) <= num_parts:
            return sentences
        
        # Group sentences into parts
        sentences_per_part = len(sentences) // num_parts
        parts = []
        
        for i in range(num_parts):
            start_idx = i * sentences_per_part
            if i == num_parts - 1:  # Last part gets remaining sentences
                end_idx = len(sentences)
            else:
                end_idx = (i + 1) * sentences_per_part
            
            part = ' '.join(sentences[start_idx:end_idx])
            parts.append(part)
        
        return parts
    
    def _get_duration(self, transcription: TranscriptionResult) -> float:
        """Get duration from transcription"""
        if hasattr(transcription, 'metadata') and transcription.metadata:
            return transcription.metadata.get('total_duration', 0)
        
        if transcription.segments:
            return max(seg.end for seg in transcription.segments)
        
        return 0
    
    def save_script(self, script: GeneratedScript, path: str):
        """Save script to JSON file"""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(asdict(script), f, indent=2, ensure_ascii=False)
            logger.info(f"Saved script to {path}")
        except Exception as e:
            logger.error(f"Save failed: {e}")
            raise

# Simple interface function
def generate_script_from_prompt(transcriptions: List[TranscriptionResult], 
                               user_prompt: str,
                               target_duration_minutes: int = 10) -> GeneratedScript:
    """
    Ultra-simple interface: transcriptions + prompt → script
    """
    generator = SmartScriptGenerator()
    return generator.generate_script(transcriptions, user_prompt, target_duration_minutes)

if __name__ == "__main__":
    print("Smart Edit Script Generation - Ultra Simple")
    print("Usage: script = generate_script_from_prompt(transcriptions, 'Make a tutorial', 10)")