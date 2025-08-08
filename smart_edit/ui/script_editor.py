"""
Smart Edit Script Editor Window - Cleaned Version

Interactive editor for reviewing and modifying AI-generated scripts.
Takes user prompt, generates script, displays full text for editing.
Simplified for single video workflow with EDL export.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import List, Optional, Dict, Any
import copy
import threading

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from script_generation import GeneratedScript, ScriptSegment, generate_script_from_prompt
    from transcription import TranscriptionResult
except ImportError:
    try:
        # Fallback for direct execution
        from script_generation import GeneratedScript, ScriptSegment, generate_script_from_prompt
        from transcription import TranscriptionResult
    except ImportError:
        # Define minimal classes for development
        print("Warning: Could not import script_generation modules")
        
        class GeneratedScript:
            def __init__(self):
                self.full_text = ""
                self.segments = []
                self.title = "Test Script"
                self.target_duration_minutes = 10
                self.estimated_duration_seconds = 600
                self.user_prompt = ""
                self.metadata = {}
        
        class ScriptSegment:
            def __init__(self):
                self.start_time = 0.0
                self.end_time = 10.0
                self.content = "Test content"
                self.video_index = 0
                self.keep = True
        
        class TranscriptionResult:
            def __init__(self):
                self.segments = []
                self.metadata = {'total_duration': 600}
        
        def generate_script_from_prompt(*args, **kwargs):
            raise NotImplementedError("Script generation not available in development mode")

class PromptScriptEditorWindow:
    """Interactive prompt-driven script editor"""
    
    def __init__(self, parent, transcriptions: List[TranscriptionResult], project_name: str = "Video Project"):
        self.parent = parent
        self.transcriptions = transcriptions
        self.project_name = project_name
        
        # Calculate total duration
        self.total_duration = sum(t.metadata.get('total_duration', 0) for t in transcriptions)
        
        # State variables
        self.generated_script: Optional[GeneratedScript] = None
        self.modified_script: Optional[GeneratedScript] = None
        self.is_generating = False
        self.script_modified = False
        self.generation_thread = None  # Track background thread
        self.window_closed = False  # Track window state
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Smart Edit - Script Generator & Editor")
        self.window.geometry("1000x700")
        self.window.transient(parent)
        self.window.grab_set()
        
        # Handle window closing
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        # Setup UI
        self._setup_ui()
        self._update_project_info()
    
    def _setup_ui(self):
        """Set up the script editor interface"""
        # Main container with notebook (tabs)
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Prompt & Generation
        self.prompt_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.prompt_frame, text="1. Script Generation")
        self._setup_prompt_tab()
        
        # Tab 2: Script Editor
        self.editor_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.editor_frame, text="2. Script Editor")
        self._setup_editor_tab()
        
        # Tab 3: Timeline Review
        self.timeline_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.timeline_frame, text="3. Timeline Review")
        self._setup_timeline_tab()
        
        # Initially disable editor tabs
        self.notebook.tab(1, state="disabled")
        self.notebook.tab(2, state="disabled")
        
        # Bottom button frame
        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        self.export_btn = ttk.Button(button_frame, text="Export Script", command=self.export_script, state="disabled")
        self.export_btn.pack(side=tk.RIGHT, padx=(0, 10))
    
    def _setup_prompt_tab(self):
        """Setup the prompt input and generation tab"""
        # Project info frame
        info_frame = ttk.LabelFrame(self.prompt_frame, text="Project Information", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        self.info_label = ttk.Label(info_frame, text="", font=("Arial", 10))
        self.info_label.pack(anchor=tk.W)
        
        # Prompt input frame
        prompt_frame = ttk.LabelFrame(self.prompt_frame, text="Video Instructions", padding="10")
        prompt_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Instructions
        instructions = ttk.Label(prompt_frame, 
            text="Describe what you want your video to be about. Be specific about:\n"
                 "• The main topic or message\n"
                 "• Target audience\n"
                 "• Key points to emphasize\n"
                 "• Content to remove or minimize\n"
                 "• Overall tone and style",
            font=("Arial", 9), foreground="gray")
        instructions.pack(anchor=tk.W, pady=(0, 10))
        
        # Prompt text area
        prompt_input_frame = ttk.Frame(prompt_frame)
        prompt_input_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(prompt_input_frame, text="Your Instructions:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        
        self.prompt_text = scrolledtext.ScrolledText(prompt_input_frame, height=8, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # Placeholder text
        placeholder = ("Example: 'Create a 10-minute educational video about Python programming. "
                      "Focus on practical examples and remove any long pauses or tangents. "
                      "Keep the tone conversational but professional. Emphasize the key concepts "
                      "and provide clear step-by-step explanations.'")
        
        self.prompt_text.insert(1.0, placeholder)
        self.prompt_text.bind("<FocusIn>", self._clear_placeholder)
        self.prompt_text.bind("<FocusOut>", self._restore_placeholder)
        self.prompt_text.config(foreground="gray")
        
        # Generation settings frame
        settings_frame = ttk.Frame(prompt_frame)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Target duration
        duration_frame = ttk.Frame(settings_frame)
        duration_frame.pack(side=tk.LEFT)
        
        ttk.Label(duration_frame, text="Target Duration:").pack(side=tk.LEFT)
        self.duration_var = tk.IntVar(value=10)
        duration_spin = ttk.Spinbox(duration_frame, from_=1, to=60, textvariable=self.duration_var, width=5)
        duration_spin.pack(side=tk.LEFT, padx=(5, 2))
        ttk.Label(duration_frame, text="minutes").pack(side=tk.LEFT)
        
        # Generation button
        self.generate_btn = ttk.Button(settings_frame, text="🤖 Generate Script", 
                                     command=self.generate_script, style="Accent.TButton")
        self.generate_btn.pack(side=tk.RIGHT)
        
        # Progress frame (initially hidden)
        self.progress_frame = ttk.Frame(prompt_frame)
        
        self.progress_label = ttk.Label(self.progress_frame, text="Generating script...")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
    
    def _setup_editor_tab(self):
        """Setup the script editing tab"""
        # Header frame
        header_frame = ttk.Frame(self.editor_frame)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.script_title_label = ttk.Label(header_frame, text="", font=("Arial", 14, "bold"))
        self.script_title_label.pack(side=tk.LEFT)
        
        self.script_stats_label = ttk.Label(header_frame, text="", font=("Arial", 10))
        self.script_stats_label.pack(side=tk.RIGHT)
        
        # Main content frame with paned window
        content_paned = ttk.PanedWindow(self.editor_frame, orient=tk.HORIZONTAL)
        content_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Left panel - Full script text
        left_frame = ttk.LabelFrame(content_paned, text="Generated Script", padding="5")
        content_paned.add(left_frame, weight=3)
        
        # Script text editor
        self.script_text = scrolledtext.ScrolledText(left_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.script_text.pack(fill=tk.BOTH, expand=True)
        self.script_text.bind("<KeyPress>", self._on_script_modified)
        
        # Right panel - Segment controls
        right_frame = ttk.LabelFrame(content_paned, text="Timeline Segments", padding="5")
        content_paned.add(right_frame, weight=1)
        
        # Segment list with checkboxes
        segments_container = ttk.Frame(right_frame)
        segments_container.pack(fill=tk.BOTH, expand=True)
        
        # Segments treeview
        self.segments_tree = ttk.Treeview(segments_container, 
                                        columns=("time", "content"), 
                                        show="tree headings")
        
        # Configure columns - removed "video" column since no multicam
        self.segments_tree.heading("#0", text="✓")
        self.segments_tree.heading("time", text="Time")
        self.segments_tree.heading("content", text="Content")
        
        self.segments_tree.column("#0", width=30, minwidth=30)
        self.segments_tree.column("time", width=80, minwidth=60)
        self.segments_tree.column("content", width=250, minwidth=200)
        
        # Scrollbars for segments
        segments_scroll = ttk.Scrollbar(segments_container, orient=tk.VERTICAL, command=self.segments_tree.yview)
        self.segments_tree.configure(yscrollcommand=segments_scroll.set)
        
        self.segments_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        segments_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind segment events
        self.segments_tree.bind("<Button-1>", self._on_segment_click)
        
        # Segment controls
        segment_controls = ttk.Frame(right_frame)
        segment_controls.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(segment_controls, text="Select All", command=self._select_all_segments).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(segment_controls, text="Deselect All", command=self._deselect_all_segments).pack(side=tk.LEFT)
        
        # Regenerate button
        regen_frame = ttk.Frame(self.editor_frame)
        regen_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(regen_frame, text="🔄 Regenerate Script", command=self.regenerate_script).pack(side=tk.LEFT)
        ttk.Label(regen_frame, text="Tip: Edit your prompt above and regenerate for different results", 
                 font=("Arial", 9), foreground="gray").pack(side=tk.RIGHT)
    
    def _setup_timeline_tab(self):
        """Setup the timeline review tab"""
        # Timeline preview
        timeline_frame = ttk.LabelFrame(self.timeline_frame, text="Final Timeline Preview", padding="10")
        timeline_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.timeline_text = scrolledtext.ScrolledText(timeline_frame, font=("Consolas", 9), state=tk.DISABLED)
        self.timeline_text.pack(fill=tk.BOTH, expand=True)
        
        # Export options - Updated for EDL
        export_frame = ttk.LabelFrame(self.timeline_frame, text="Export Options", padding="10")
        export_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.export_format_var = tk.StringVar(value="edl")
        
        ttk.Radiobutton(export_frame, text="EDL (Edit Decision List)", 
                       variable=self.export_format_var, value="edl").pack(side=tk.LEFT)
        ttk.Radiobutton(export_frame, text="Text Script", 
                       variable=self.export_format_var, value="text").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Radiobutton(export_frame, text="JSON Data", 
                       variable=self.export_format_var, value="json").pack(side=tk.LEFT, padx=(20, 0))
    
    def _update_project_info(self):
        """Update project information display"""
        duration_mins = int(self.total_duration // 60)
        duration_secs = int(self.total_duration % 60)
        
        info_text = (f"Project: {self.project_name}\n"
                    f"Videos: {len(self.transcriptions)}\n"
                    f"Total Duration: {duration_mins}:{duration_secs:02d}\n"
                    f"Transcription: Complete")
        
        self.info_label.config(text=info_text)
    
    def _clear_placeholder(self, event):
        """Clear placeholder text on focus"""
        if self.prompt_text.get(1.0, tk.END).strip() == self._get_placeholder_text():
            self.prompt_text.delete(1.0, tk.END)
            self.prompt_text.config(foreground="black")
    
    def _restore_placeholder(self, event):
        """Restore placeholder if empty"""
        if not self.prompt_text.get(1.0, tk.END).strip():
            self.prompt_text.insert(1.0, self._get_placeholder_text())
            self.prompt_text.config(foreground="gray")
    
    def _get_placeholder_text(self):
        """Get the placeholder text"""
        return ("Example: 'Create a 10-minute educational video about Python programming. "
               "Focus on practical examples and remove any long pauses or tangents. "
               "Keep the tone conversational but professional. Emphasize the key concepts "
               "and provide clear step-by-step explanations.'")
    
    def _on_script_modified(self, event):
        """Handle script text modifications"""
        if not self.script_modified:
            self.script_modified = True
            self._update_script_stats()
    
    def _on_segment_click(self, event):
        """Handle segment tree clicks (toggle checkboxes)"""
        item = self.segments_tree.identify_row(event.y)
        if item and self.segments_tree.identify_column(event.x) == "#0":
            # Toggle checkbox
            current_text = self.segments_tree.item(item, "text")
            if current_text == "✓":
                self.segments_tree.item(item, text="")
            else:
                self.segments_tree.item(item, text="✓")
            
            self._update_timeline_preview()
    
    def generate_script(self):
        """Generate script from user prompt"""
        prompt = self.prompt_text.get(1.0, tk.END).strip()
        
        # Validate prompt
        if not prompt or prompt == self._get_placeholder_text():
            messagebox.showwarning("Missing Prompt", 
                                  "Please enter instructions for your video script.")
            return
        
        target_duration = self.duration_var.get()
        
        # Show progress
        self.progress_frame.pack(fill=tk.X, padx=10, pady=10)
        self.progress_bar.start()
        self.generate_btn.config(state="disabled")
        self.is_generating = True
        
        # Generate in background thread
        def generate_thread():
            try:
                # Check if window still exists
                if self.window_closed:
                    return
                    
                script = generate_script_from_prompt(
                    transcriptions=self.transcriptions,
                    user_prompt=prompt,
                    target_duration_minutes=target_duration
                )
                
                # Update UI in main thread (only if window still exists)
                if not self.window_closed:
                    self.window.after(0, self._on_script_generated, script)
                
            except Exception as e:
                # Handle errors (only if window still exists)
                if not self.window_closed:
                    self.window.after(0, self._on_script_error, str(e))
        
        self.generation_thread = threading.Thread(target=generate_thread, daemon=True)
        self.generation_thread.start()
    
    def _on_script_generated(self, script: GeneratedScript):
        """Handle successful script generation"""
        self.generated_script = script
        self.modified_script = copy.deepcopy(script)
        self.script_modified = False
        
        # Hide progress
        self.progress_frame.pack_forget()
        self.progress_bar.stop()
        self.generate_btn.config(state="normal")
        self.is_generating = False
        
        # Enable editor tabs
        self.notebook.tab(1, state="normal")
        self.notebook.tab(2, state="normal")
        self.export_btn.config(state="normal")
        
        # Switch to editor tab
        self.notebook.select(1)
        
        # Populate editor
        self._populate_script_editor()
        self._populate_segments()
        self._update_timeline_preview()
        
        messagebox.showinfo("Script Generated", 
                           f"Script generated successfully!\n"
                           f"• {len(script.segments)} segments selected\n"
                           f"• Estimated duration: {script.estimated_duration_seconds/60:.1f} minutes")
    
    def _on_script_error(self, error_message: str):
        """Handle script generation error"""
        # Hide progress
        self.progress_frame.pack_forget()
        self.progress_bar.stop()
        self.generate_btn.config(state="normal")
        self.is_generating = False
        
        messagebox.showerror("Generation Failed", 
                            f"Failed to generate script:\n{error_message}\n\n"
                            f"Please check your prompt and try again.")
    
    def _populate_script_editor(self):
        """Populate the script editor with generated content"""
        if not self.generated_script:
            return
        
        # Validate script structure
        try:
            title = getattr(self.generated_script, 'title', 'Untitled Script')
            full_text = getattr(self.generated_script, 'full_text', 'No script content available')
            
            # Update title and stats
            self.script_title_label.config(text=title)
            self._update_script_stats()
            
            # Set script text
            self.script_text.delete(1.0, tk.END)
            self.script_text.insert(1.0, full_text)
            
        except Exception as e:
            messagebox.showerror("Display Error", f"Error displaying script: {e}")
            self.script_text.delete(1.0, tk.END)
            self.script_text.insert(1.0, "Error loading script content")
    
    def _update_script_stats(self):
        """Update script statistics"""
        if not self.generated_script:
            return
        
        duration_text = f"Target: {self.generated_script.target_duration_minutes}min"
        estimate_text = f"Estimated: {self.generated_script.estimated_duration_seconds/60:.1f}min"
        segments_text = f"Segments: {len(self.generated_script.segments)}"
        
        status_text = ""
        if self.script_modified:
            status_text = " (Modified)"
        
        stats_text = f"{duration_text} | {estimate_text} | {segments_text}{status_text}"
        self.script_stats_label.config(text=stats_text)
    
    def _populate_segments(self):
        """Populate the segments tree"""
        if not self.generated_script or not hasattr(self.generated_script, 'segments'):
            return
        
        # Clear existing items
        for item in self.segments_tree.get_children():
            self.segments_tree.delete(item)
        
        # Validate segments
        segments = getattr(self.generated_script, 'segments', [])
        if not segments:
            # Add placeholder item
            self.segments_tree.insert("", tk.END, 
                                    text="",
                                    values=("0.0s", "No segments available"),
                                    tags=("placeholder",))
            return
        
        # Add segments - removed video column handling
        for i, segment in enumerate(segments):
            try:
                # Format time with error handling
                start_time = getattr(segment, 'start_time', 0.0)
                time_str = f"{start_time:.1f}s"
                
                # Content preview with error handling
                content = getattr(segment, 'content', 'No content')
                content_preview = content[:60] + "..." if len(content) > 60 else content
                
                # Insert with checkbox
                keep = getattr(segment, 'keep', True)
                checkbox_text = "✓" if keep else ""
                
                self.segments_tree.insert("", tk.END, 
                                        text=checkbox_text,
                                        values=(time_str, content_preview),
                                        tags=(f"segment_{i}",))
                
            except Exception as e:
                # Add error item
                self.segments_tree.insert("", tk.END, 
                                        text="",
                                        values=("ERR", f"Error loading segment {i}: {e}"),
                                        tags=(f"error_{i}",))
    
    def _select_all_segments(self):
        """Select all segments"""
        for item in self.segments_tree.get_children():
            self.segments_tree.item(item, text="✓")
        self._update_timeline_preview()
    
    def _deselect_all_segments(self):
        """Deselect all segments"""
        for item in self.segments_tree.get_children():
            self.segments_tree.item(item, text="")
        self._update_timeline_preview()
    
    def _update_timeline_preview(self):
        """Update the timeline preview"""
        if not self.generated_script:
            return
        
        timeline_lines = []
        timeline_lines.append("=== FINAL TIMELINE PREVIEW ===\n")
        timeline_lines.append(f"Project: {self.generated_script.title}")
        timeline_lines.append("")
        
        # Get selected segments
        selected_segments = []
        for i, item in enumerate(self.segments_tree.get_children()):
            if self.segments_tree.item(item, "text") == "✓":
                if i < len(self.generated_script.segments):
                    selected_segments.append(self.generated_script.segments[i])
        
        if not selected_segments:
            timeline_lines.append("No segments selected for final timeline.")
        else:
            current_time = 0.0
            
            for i, segment in enumerate(selected_segments):
                duration = segment.end_time - segment.start_time
                
                # Timeline entry - removed video indicator since no multicam
                timeline_lines.append(
                    f"{current_time:6.1f}s - {current_time + duration:6.1f}s: "
                    f"{segment.content[:70]}{'...' if len(segment.content) > 70 else ''}"
                )
                
                current_time += duration
            
            timeline_lines.append("")
            timeline_lines.append(f"Total Duration: {current_time:.1f} seconds ({current_time/60:.1f} minutes)")
            timeline_lines.append(f"Selected Segments: {len(selected_segments)} of {len(self.generated_script.segments)}")
        
        # Update timeline display
        self.timeline_text.config(state=tk.NORMAL)
        self.timeline_text.delete(1.0, tk.END)
        self.timeline_text.insert(1.0, "\n".join(timeline_lines))
        self.timeline_text.config(state=tk.DISABLED)
    
    def regenerate_script(self):
        """Regenerate script with current prompt"""
        if self.is_generating:
            return
        
        if messagebox.askyesno("Regenerate Script", 
                              "This will create a new script and lose any edits. Continue?"):
            self.generate_script()
    
    def export_script(self):
        """Export the final script"""
        if not self.generated_script:
            messagebox.showwarning("No Script", "Please generate a script first.")
            return
        
        # Update script with current text and selected segments
        current_text = self.script_text.get(1.0, tk.END)
        self.modified_script.full_text = current_text
        
        # Update segment selections
        for i, item in enumerate(self.segments_tree.get_children()):
            if i < len(self.modified_script.segments):
                self.modified_script.segments[i].keep = (self.segments_tree.item(item, "text") == "✓")
        
        # Store the result
        self.final_script = self.modified_script
        
        messagebox.showinfo("Export Ready", 
                           "Script is ready for export. You can now close this window.")
        
        self.window.destroy()
    
    def _on_window_close(self):
        """Handle window closing"""
        self.window_closed = True
        
        if self.is_generating:
            if messagebox.askyesno("Cancel Generation", 
                                  "Script generation is in progress. Cancel anyway?"):
                self.window.destroy()
        else:
            self.window.destroy()
    
    def cancel(self):
        """Cancel script generation"""
        self._on_window_close()

# Convenience function for easy integration
def show_script_editor(parent, transcriptions: List[TranscriptionResult], 
                      project_name: str = "Video Project") -> Optional[GeneratedScript]:
    """
    Show the script editor window and return the final script
    
    Args:
        parent: Parent window
        transcriptions: List of transcription results
        project_name: Name of the project
    
    Returns:
        GeneratedScript if completed, None if cancelled
    """
    editor = PromptScriptEditorWindow(parent, transcriptions, project_name)
    parent.wait_window(editor.window)
    
    return getattr(editor, 'final_script', None)

# Test function
if __name__ == "__main__":
    # Mock data for testing
    class MockTranscriptionResult:
        def __init__(self, duration):
            self.segments = []
            self.metadata = {'total_duration': duration}
    
    root = tk.Tk()
    root.withdraw()
    
    # Test with single video
    transcriptions = [MockTranscriptionResult(600)]  # 10 minutes
    
    result = show_script_editor(root, transcriptions, "Test Project")
    
    if result:
        print(f"Script generated: {result.title}")
        print(f"Segments: {len(result.segments)}")
    else:
        print("Cancelled")
    
    root.mainloop()