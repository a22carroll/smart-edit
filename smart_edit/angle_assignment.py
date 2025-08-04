"""
Smart Edit Camera Angle Assignment Module

Assigns camera angles to edit decisions for multicam workflows.
Simple rule-based logic that creates natural-looking camera switches.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

# Import from script generation module
from script_generation import EditScript, CutDecision, EditAction

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AngleAssignmentConfig:
    """Configuration for camera angle assignment"""
    max_segments_per_camera: int = 3  # Switch after this many segments
    prefer_speaker_switches: bool = True  # Switch cameras on speaker changes
    prefer_content_switches: bool = True  # Switch on important content types
    avoid_ping_pong: bool = True  # Avoid rapid back-and-forth switching
    default_strategy: str = "smart"  # "smart", "round_robin", "speaker_based"

class CameraAngleAssigner:
    """Assigns camera angles to edit decisions"""
    
    def __init__(self, config: Optional[AngleAssignmentConfig] = None):
        self.config = config or AngleAssignmentConfig()
    
    def assign_angles(
        self, 
        edit_script: EditScript, 
        camera_ids: List[str],
        strategy: Optional[str] = None
    ) -> EditScript:
        """
        Assign camera angles to kept segments in edit script
        
        Args:
            edit_script: Edit script with cut decisions
            camera_ids: List of camera identifiers (e.g., ["Camera_1", "Camera_2"])
            strategy: Override default strategy ("smart", "round_robin", "speaker_based")
            
        Returns:
            EditScript with camera_id assigned to each kept cut
        """
        if not camera_ids:
            logger.warning("No camera IDs provided, skipping angle assignment")
            return edit_script
        
        if len(camera_ids) == 1:
            logger.info("Single camera detected, assigning all cuts to camera")
            return self._assign_single_camera(edit_script, camera_ids[0])
        
        strategy = strategy or self.config.default_strategy
        logger.info(f"Assigning camera angles using '{strategy}' strategy for {len(camera_ids)} cameras")
        
        if strategy == "round_robin":
            return self._assign_round_robin(edit_script, camera_ids)
        elif strategy == "speaker_based":
            return self._assign_speaker_based(edit_script, camera_ids)
        else:  # "smart" strategy
            return self._assign_smart(edit_script, camera_ids)
    
    def _assign_single_camera(self, edit_script: EditScript, camera_id: str) -> EditScript:
        """Assign single camera to all kept cuts"""
        for cut in edit_script.cuts:
            if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]:
                # Add camera_id attribute if it doesn't exist
                if not hasattr(cut, 'camera_id'):
                    cut.camera_id = camera_id
                else:
                    cut.camera_id = camera_id
        return edit_script
    
    def _assign_round_robin(self, edit_script: EditScript, camera_ids: List[str]) -> EditScript:
        """Simple round-robin assignment"""
        camera_index = 0
        
        for cut in edit_script.cuts:
            if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]:
                # Add camera_id attribute if it doesn't exist
                if not hasattr(cut, 'camera_id'):
                    cut.camera_id = camera_ids[camera_index]
                else:
                    cut.camera_id = camera_ids[camera_index]
                camera_index = (camera_index + 1) % len(camera_ids)
        
        logger.info("Applied round-robin camera assignment")
        return edit_script
    
    def _assign_speaker_based(self, edit_script: EditScript, camera_ids: List[str]) -> EditScript:
        """Assign cameras based on speaker changes"""
        camera_index = 0
        last_speaker = None
        
        for cut in edit_script.cuts:
            if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]:
                # Switch camera when speaker changes
                current_speaker = getattr(cut, 'speaker', 'unknown')
                if current_speaker != last_speaker and last_speaker is not None:
                    camera_index = (camera_index + 1) % len(camera_ids)
                
                # Add camera_id attribute if it doesn't exist
                if not hasattr(cut, 'camera_id'):
                    cut.camera_id = camera_ids[camera_index]
                else:
                    cut.camera_id = camera_ids[camera_index]
                last_speaker = current_speaker
        
        logger.info("Applied speaker-based camera assignment")
        return edit_script
    
    def _assign_smart(self, edit_script: EditScript, camera_ids: List[str]) -> EditScript:
        """Smart assignment combining multiple factors"""
        camera_index = 0
        segments_on_camera = 0
        last_speaker = None
        last_switch_position = -999  # Track last switch to avoid ping-pong
        
        kept_cuts = [cut for cut in edit_script.cuts if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]]
        
        for i, cut in enumerate(kept_cuts):
            should_switch = False
            switch_reason = ""
            
            # Get current segment info
            current_speaker = getattr(cut, 'speaker', 'unknown')
            content_type = getattr(cut, 'content_type', 'supporting')
            
            # Reason 1: Speaker change (highest priority)
            if (self.config.prefer_speaker_switches and 
                current_speaker != last_speaker and 
                last_speaker is not None):
                should_switch = True
                switch_reason = "speaker_change"
            
            # Reason 2: Important content types
            elif (self.config.prefer_content_switches and 
                  content_type in ["topic_introduction", "conclusion", "main_point"] and
                  segments_on_camera > 0):
                should_switch = True
                switch_reason = "content_importance"
            
            # Reason 3: Too many segments on same camera
            elif segments_on_camera >= self.config.max_segments_per_camera:
                should_switch = True
                switch_reason = "max_segments_reached"
            
            # Reason 4: Add variety (but not too often)
            elif (segments_on_camera >= 2 and 
                  i > len(kept_cuts) * 0.3 and  # Not in the first 30%
                  (i - last_switch_position) >= 2):  # At least 2 segments since last switch
                should_switch = True
                switch_reason = "variety"
            
            # Apply ping-pong avoidance
            if (should_switch and 
                self.config.avoid_ping_pong and 
                (i - last_switch_position) < 2 and
                switch_reason not in ["speaker_change"]):  # Always allow speaker switches
                should_switch = False
                switch_reason = "ping_pong_avoided"
            
            # Execute camera switch
            if should_switch:
                camera_index = (camera_index + 1) % len(camera_ids)
                segments_on_camera = 0
                last_switch_position = i
                logger.debug(f"Camera switch at segment {i}: {switch_reason}")
            
            # Assign camera to cut (add attribute if it doesn't exist)
            if not hasattr(cut, 'camera_id'):
                cut.camera_id = camera_ids[camera_index]
            else:
                cut.camera_id = camera_ids[camera_index]
            segments_on_camera += 1
            last_speaker = current_speaker
        
        # Log assignment summary
        camera_usage = {}
        for cut in kept_cuts:
            camera_id = getattr(cut, 'camera_id', 'unknown')
            camera_usage[camera_id] = camera_usage.get(camera_id, 0) + 1
        
        logger.info(f"Smart camera assignment completed. Usage: {camera_usage}")
        return edit_script
    
    def analyze_assignment(self, edit_script: EditScript) -> Dict[str, any]:
        """Analyze the current camera assignment"""
        kept_cuts = [cut for cut in edit_script.cuts if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]]
        
        if not kept_cuts:
            return {"error": "No kept cuts found"}
        
        # Count camera usage
        camera_usage = {}
        switches = 0
        last_camera = None
        
        for cut in kept_cuts:
            camera_id = getattr(cut, 'camera_id', None)
            if camera_id:
                camera_usage[camera_id] = camera_usage.get(camera_id, 0) + 1
                if last_camera and camera_id != last_camera:
                    switches += 1
                last_camera = camera_id
        
        # Calculate balance
        if camera_usage:
            total_segments = sum(camera_usage.values())
            if total_segments > 0 and len(camera_usage) > 1:
                balance_score = 1.0 - (max(camera_usage.values()) - min(camera_usage.values())) / total_segments
            else:
                balance_score = 1.0  # Perfect balance for single camera or no segments
        else:
            balance_score = 0.0
        
        return {
            "total_kept_segments": len(kept_cuts),
            "camera_usage": camera_usage,
            "total_switches": switches,
            "average_segments_per_switch": len(kept_cuts) / (switches + 1) if len(kept_cuts) > 0 else 0,
            "balance_score": round(balance_score, 2),  # 1.0 = perfect balance, 0.0 = all on one camera
            "cameras_used": len(camera_usage)
        }

# Convenience functions
def assign_camera_angles(
    edit_script: EditScript, 
    camera_ids: List[str],
    strategy: str = "smart",
    config: Optional[AngleAssignmentConfig] = None
) -> EditScript:
    """
    Simple interface for camera angle assignment
    
    Args:
        edit_script: Edit script with cut decisions
        camera_ids: List of camera identifiers
        strategy: Assignment strategy ("smart", "round_robin", "speaker_based")
        config: Optional configuration
        
    Returns:
        EditScript with camera angles assigned
    """
    assigner = CameraAngleAssigner(config)
    return assigner.assign_angles(edit_script, camera_ids, strategy)

def analyze_camera_assignment(edit_script: EditScript) -> Dict[str, any]:
    """
    Analyze camera assignment in edit script
    
    Args:
        edit_script: Edit script with camera assignments
        
    Returns:
        Dictionary with assignment analysis
    """
    assigner = CameraAngleAssigner()
    return assigner.analyze_assignment(edit_script)

# Example usage
if __name__ == "__main__":
    # This would typically be used with real edit scripts
    print("Camera Angle Assignment module ready!")
    print("Available strategies:")
    print("- smart: Combines speaker changes, content importance, and variety")
    print("- round_robin: Simple alternating between cameras")  
    print("- speaker_based: Switch cameras only on speaker changes")
    
    # Example configuration
    config = AngleAssignmentConfig(
        max_segments_per_camera=4,
        prefer_speaker_switches=True,
        avoid_ping_pong=True
    )
    
    print(f"\nDefault configuration: max_segments={config.max_segments_per_camera}")