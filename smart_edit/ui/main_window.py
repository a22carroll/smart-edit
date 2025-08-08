"""
Smart Edit Main Window - Simplified and Bug-free Version

Main application window for the Smart Edit video editing system.
Exports to EDL format with streamlined code and maintained functionality.
"""

import os
import sys
import threading
import logging
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from transcription import transcribe_video
    from ui.script_editor import show_script_editor
    from edl_export import export_script_to_edl
    EDL_EXPORT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Import error - {e}")
    EDL_EXPORT_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartEditMainWindow:
    """Main application window for Smart Edit"""
    
    # Supported video formats
    VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Smart Edit - AI Video Editor")
        self.root.geometry("1000x700")
        
        # Application state
        self.video_files = []
        self.transcription_results = []
        self.generated_script = None
        self.processing_thread = None
        self.project_name = "Untitled Project"
        self.custom_clip_names = {}  # Store custom clip names
        self.clip_name_entries = []  # Store UI entry widgets
        
        self._setup_ui()
        self.update_status("Ready - Load video files to begin")
    
    def _setup_ui(self):
        """Set up the main user interface"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title
        ttk.Label(main_frame, text="Smart Edit", font=("Arial", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 10))
        
        # Left panel - Controls
        self._setup_left_panel(main_frame)
        
        # Right panel - Results
        self._setup_right_panel(main_frame)
        
        # Status bar
        self.status_var = tk.StringVar()
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, padding="3").grid(
            row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
    
    def _setup_left_panel(self, parent):
        """Setup left control panel"""
        left_frame = ttk.LabelFrame(parent, text="Video Files & Controls", padding="5")
        left_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Project name
        project_frame = ttk.Frame(left_frame)
        project_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        ttk.Label(project_frame, text="Project:").pack(side=tk.LEFT)
        self.project_name_var = tk.StringVar(value=self.project_name)
        ttk.Entry(project_frame, textvariable=self.project_name_var, width=20).pack(
            side=tk.LEFT, padx=(3, 0), fill=tk.X, expand=True)
        self.project_name_var.trace('w', self._on_project_name_change)
        
        # File list
        ttk.Label(left_frame, text="Videos:").grid(row=1, column=0, sticky=tk.W, pady=(0, 2))
        
        listbox_frame = ttk.Frame(left_frame)
        listbox_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        listbox_frame.columnconfigure(0, weight=1)
        
        self.file_listbox = tk.Listbox(listbox_frame, height=4)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        
        # File buttons
        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        ttk.Button(button_frame, text="Add", command=self.add_videos).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(button_frame, text="Remove", command=self.remove_video).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(button_frame, text="Clear", command=self.clear_videos).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="New Project", command=self.new_project).pack(side=tk.RIGHT)
        
        # Custom clip names section
        self._setup_clip_names_section(left_frame)
        
        # Processing controls
        ttk.Separator(left_frame, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=8)
        ttk.Label(left_frame, text="Processing:", font=("Arial", 10, "bold")).grid(row=7, column=0, sticky=tk.W, pady=(0, 5))
        
        self.transcribe_button = ttk.Button(left_frame, text="🎤 Transcribe", command=self.start_transcription)
        self.transcribe_button.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))
        
        self.script_button = ttk.Button(left_frame, text="📝 Script", command=self.open_script_generator, state=tk.DISABLED)
        self.script_button.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Progress bar
        self.progress = ttk.Progressbar(left_frame, mode='indeterminate')
        self.progress.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 8))
        
        # Export controls
        ttk.Separator(left_frame, orient='horizontal').grid(row=11, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=8)
        ttk.Label(left_frame, text="Export:", font=("Arial", 10, "bold")).grid(row=12, column=0, sticky=tk.W, pady=(0, 5))
        
        export_text = "📤 Export EDL" if EDL_EXPORT_AVAILABLE else "📤 Export Text"
        self.export_button = ttk.Button(left_frame, text=export_text, command=self.export_edl, state=tk.DISABLED)
        self.export_button.grid(row=13, column=0, columnspan=2, sticky=(tk.W, tk.E))
    
    def _setup_clip_names_section(self, parent):
        """Setup the custom clip names editing section - simplified approach"""
        # Label for clip names
        ttk.Label(parent, text="Clip Names:").grid(row=4, column=0, sticky=tk.W, pady=(5, 2))
        
        # Frame for clip name entries with scrollbar
        clip_frame = ttk.Frame(parent)
        clip_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        clip_frame.columnconfigure(0, weight=1)
        
        # Scrollable text widget for clip names (simpler than canvas approach)
        self.clip_names_frame = ttk.Frame(clip_frame)
        self.clip_names_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Initially show placeholder
        self._update_clip_names_ui()
    
    def _update_clip_names_ui(self):
        """Update the clip names editing UI based on current video files"""
        # Clear existing entries
        for widget in self.clip_names_frame.winfo_children():
            widget.destroy()
        self.clip_name_entries.clear()
        
        if not self.video_files:
            # Show placeholder text when no videos
            ttk.Label(self.clip_names_frame, text="Add videos to edit clip names", 
                     foreground="gray", font=("Arial", 8)).grid(row=0, column=0, pady=5)
            return
        
        # Create entry for each video file - simplified layout
        for i, video_path in enumerate(self.video_files):
            filename = os.path.basename(video_path)
            
            # Frame for this clip name entry
            entry_frame = ttk.Frame(self.clip_names_frame)
            entry_frame.grid(row=i, column=0, sticky=(tk.W, tk.E), pady=1, padx=2)
            entry_frame.columnconfigure(2, weight=1)
            
            # Simplified display - just number and truncated filename
            display_filename = filename if len(filename) <= 15 else filename[:12] + "..."
            ttk.Label(entry_frame, text=f"{i+1}.", width=2).grid(row=0, column=0, padx=(0, 2))
            ttk.Label(entry_frame, text=display_filename, width=15).grid(row=0, column=1, sticky=tk.W, padx=(0, 5))
            
            # Entry for custom name
            custom_name_var = tk.StringVar()
            # Pre-fill with existing custom name if available
            if i in self.custom_clip_names:
                custom_name_var.set(self.custom_clip_names[i])
            
            entry = ttk.Entry(entry_frame, textvariable=custom_name_var, width=15)
            entry.grid(row=0, column=2, sticky=(tk.W, tk.E), padx=(0, 2))
            
            # Store the variable and index for later retrieval
            self.clip_name_entries.append((i, custom_name_var))
            
            # Bind to update custom names when changed
            custom_name_var.trace('w', lambda *args, idx=i, var=custom_name_var: self._on_clip_name_change(idx, var))
    
    def _on_clip_name_change(self, video_index, name_var):
        """Handle clip name changes"""
        custom_name = name_var.get().strip()
        if custom_name:
            self.custom_clip_names[video_index] = custom_name
        elif video_index in self.custom_clip_names:
            # Remove empty custom names
            del self.custom_clip_names[video_index]
    
    def _setup_right_panel(self, parent):
        """Setup right results panel"""
        right_frame = ttk.LabelFrame(parent, text="Results & Logs", padding="5")
        right_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        right_frame.rowconfigure(2, weight=1)
        
        # Results display
        self.results_text = ScrolledText(right_frame, height=8, width=50, state=tk.DISABLED)
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        
        # Log label
        ttk.Label(right_frame, text="Log:").grid(row=1, column=0, sticky=tk.W, pady=(5, 2))
        
        # Log display
        self.log_text = ScrolledText(right_frame, height=6, width=50, state=tk.DISABLED)
        self.log_text.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    def _on_project_name_change(self, *args):
        """Handle project name changes"""
        self.project_name = self.project_name_var.get() or "Untitled Project"
    
    def _is_video_file(self, file_path):
        """Check if file is a supported video format"""
        return Path(file_path).suffix.lower() in self.VIDEO_EXTENSIONS
    
    def _handle_error(self, operation, error):
        """Centralized error handling"""
        error_msg = f"{operation} failed: {str(error)}"
        self.log_message(f"❌ {error_msg}")
        logger.error(f"{operation} error: {error}")
        messagebox.showerror(f"{operation} Error", error_msg)
    
    def new_project(self):
        """Start a new project"""
        if self.video_files or self.transcription_results or self.generated_script:
            if not messagebox.askyesno("New Project", "This will clear all current work. Continue?"):
                return
        
        self.clear_videos()
        self.project_name = "Untitled Project"
        self.project_name_var.set(self.project_name)
        self.custom_clip_names.clear()
        self.log_message("🆕 Started new project")
    
    def add_videos(self):
        """Add video files to the processing list"""
        filetypes = [("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"), ("All files", "*.*")]
        files = filedialog.askopenfilenames(title="Select Video Files", filetypes=filetypes)
        
        added_count = 0
        invalid_files = []
        
        for file_path in files:
            if file_path in self.video_files:
                continue
                
            # Validate video file
            if not self._is_video_file(file_path):
                invalid_files.append(os.path.basename(file_path))
                continue
            
            self.video_files.append(file_path)
            filename = os.path.basename(file_path)
            self.file_listbox.insert(tk.END, filename)  # Simplified - just filename
            added_count += 1
        
        # Update clip names UI
        self._update_clip_names_ui()
        
        # Show results
        if added_count > 0:
            self.update_status(f"{len(self.video_files)} video(s) loaded")
            self.log_message(f"📁 Added {added_count} video file(s)")
            
            # Auto-generate project name from first video if still default
            if self.project_name == "Untitled Project" and self.video_files:
                first_video = Path(self.video_files[0]).stem
                self.project_name = f"{first_video}_edit"
                self.project_name_var.set(self.project_name)
        
        # Warn about invalid files
        if invalid_files:
            invalid_list = ', '.join(invalid_files[:3])
            if len(invalid_files) > 3:
                invalid_list += f" and {len(invalid_files) - 3} more"
            messagebox.showwarning("Invalid Files", 
                                 f"Skipped non-video files: {invalid_list}")
    
    def remove_video(self):
        """Remove selected video from the list"""
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a video to remove.")
            return
            
        index = selection[0]
        if 0 <= index < len(self.video_files):
            self.file_listbox.delete(index)
            removed_file = self.video_files.pop(index)
            
            # Update custom clip names - shift indices down for files after removed one
            new_custom_names = {}
            for vid_idx, custom_name in self.custom_clip_names.items():
                if vid_idx < index:
                    # Keep indices before removed file
                    new_custom_names[vid_idx] = custom_name
                elif vid_idx > index:
                    # Shift indices after removed file down by 1
                    new_custom_names[vid_idx - 1] = custom_name
                # Skip the removed index
            self.custom_clip_names = new_custom_names
            
            # Update UI
            self._update_clip_names_ui()
            self.log_message(f"🗑️ Removed: {os.path.basename(removed_file)}")
            self.update_status(f"{len(self.video_files)} video(s) loaded")
            
            if not self.video_files:
                self._reset_processing_state()
    
    def clear_videos(self):
        """Clear all videos from the list"""
        self.video_files.clear()
        self.file_listbox.delete(0, tk.END)
        self.custom_clip_names.clear()
        self._update_clip_names_ui()
        self._reset_processing_state()
        self.update_status("Ready - Load video files to begin")
        self.log_message("🗑️ Cleared all video files")
    
    def _reset_processing_state(self):
        """Reset all processing state"""
        self.transcription_results.clear()
        self.generated_script = None
        self.script_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        
        # Clear results display
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state=tk.DISABLED)
    
    def start_transcription(self):
        """Start the video transcription process"""
        if not self.video_files:
            messagebox.showwarning("No Videos", "Please add video files before transcription.")
            return
        
        if self.processing_thread and self.processing_thread.is_alive():
            messagebox.showwarning("Processing", "Transcription is already in progress.")
            return
        
        # Reset state
        self.transcription_results.clear()
        self.generated_script = None
        self.script_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        
        # Start background processing
        self.processing_thread = threading.Thread(target=self._transcribe_videos, daemon=True)
        self.processing_thread.start()
        
        # Update UI
        self.transcribe_button.config(state=tk.DISABLED)
        self.progress.start()
        self.update_status("Transcribing videos...")
        self.log_message("🎤 Starting video transcription...")
    
    def _transcribe_videos(self):
        """Transcribe videos in background thread"""
        try:
            for i, video_path in enumerate(self.video_files):
                video_name = os.path.basename(video_path)
                
                # Update progress
                self.root.after(0, lambda name=video_name, idx=i+1, total=len(self.video_files): 
                              self.log_message(f"🎤 Transcribing {idx}/{total}: {name}"))
                
                # Transcribe video
                result = transcribe_video(video_path)
                self.transcription_results.append(result)
                
                # Update completion
                duration_mins = result.metadata.get('total_duration', 0) / 60
                segment_count = len(result.segments)
                
                self.root.after(0, lambda name=video_name, duration=duration_mins, segments=segment_count:
                              self.log_message(f"✅ Completed: {name} ({duration:.1f}min, {segments} segments)"))
            
            self.root.after(0, self._transcription_complete)
            
        except Exception as e:
            self.root.after(0, lambda: self._handle_error("Transcription", e))
            self.root.after(0, self._transcription_failed)
    
    def _transcription_complete(self):
        """Handle successful transcription completion"""
        self.progress.stop()
        self.transcribe_button.config(state=tk.NORMAL)
        self.script_button.config(state=tk.NORMAL)
        self._update_transcription_results()
        self.update_status("Transcription complete - Ready to create script")
        self.log_message("🎉 Transcription complete! Click 'Script' to continue.")
    
    def _transcription_failed(self):
        """Handle transcription failure"""
        self.progress.stop()
        self.transcribe_button.config(state=tk.NORMAL)
        self.update_status("Transcription failed - Check logs for details")
    
    def _update_transcription_results(self):
        """Update the results display with transcription summary - simplified"""
        if not self.transcription_results:
            return
        
        try:
            # Calculate totals
            total_duration = sum(t.metadata.get('total_duration', 0) for t in self.transcription_results)
            total_segments = sum(len(t.segments) for t in self.transcription_results)
            
            # Build simplified results text
            results_lines = [
                "=== TRANSCRIPTION COMPLETE ===\n",
                f"Project: {self.project_name}",
                f"Videos: {len(self.transcription_results)}",
                f"Duration: {total_duration/60:.1f} minutes", 
                f"Segments: {total_segments}",
                "",
                "📹 Videos:"
            ]
            
            # Add video details
            for i, result in enumerate(self.transcription_results):
                if i >= len(self.video_files):
                    continue
                    
                video_name = os.path.basename(self.video_files[i])
                duration = result.metadata.get('total_duration', 0)
                segments = len(result.segments)
                
                results_lines.append(f"  {i+1}. {video_name} ({duration/60:.1f}min, {segments} segments)")
            
            results_lines.extend([
                "",
                "✅ Ready for script generation!"
            ])
            
            # Update display
            self.results_text.config(state=tk.NORMAL)
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(1.0, "\n".join(results_lines))
            self.results_text.config(state=tk.DISABLED)
            
        except Exception as e:
            self.log_message(f"⚠️ Error updating results: {e}")
    
    def open_script_generator(self):
        """Open the script generator/editor window"""
        if not self.transcription_results:
            messagebox.showwarning("No Transcription", "Please transcribe videos first.")
            return
        
        try:
            self.log_message("📝 Opening script generator...")
            
            final_script = show_script_editor(
                parent=self.root,
                transcriptions=self.transcription_results,
                project_name=self.project_name
            )
            
            if final_script:
                self.generated_script = final_script
                self.log_message("✅ Script generation completed!")
                self._update_script_results()
                self.export_button.config(state=tk.NORMAL)
                self.update_status("Script ready - Ready to export")
            else:
                self.log_message("❌ Script generation cancelled")
                
        except Exception as e:
            self._handle_error("Script generator", e)
    
    def _update_script_results(self):
        """Update results display with script information - simplified"""
        if not self.generated_script:
            return
        
        try:
            segments = getattr(self.generated_script, 'segments', [])
            selected_segments = [s for s in segments if getattr(s, 'keep', True)]
            
            results_lines = [
                "=== SCRIPT GENERATED ===\n",
                f"Title: {getattr(self.generated_script, 'title', 'Untitled')}",
                f"Duration: {getattr(self.generated_script, 'estimated_duration_seconds', 0)/60:.1f} minutes",
                f"Segments: {len(selected_segments)} selected",
                ""
            ]
            
            # User prompt
            user_prompt = getattr(self.generated_script, 'user_prompt', '')
            if user_prompt:
                prompt_preview = user_prompt if len(user_prompt) <= 100 else user_prompt[:97] + "..."
                results_lines.extend([
                    f"Instructions: {prompt_preview}",
                    ""
                ])
            
            # Sample segments
            results_lines.append("📋 Selected segments:")
            for i, segment in enumerate(selected_segments[:5]):
                start_time = getattr(segment, 'start_time', 0)
                content = getattr(segment, 'content', 'No content')
                video_idx = getattr(segment, 'video_index', 0)
                
                video_indicator = f"[V{video_idx + 1}]" if len(self.transcription_results) > 1 else ""
                content_preview = content if len(content) <= 50 else content[:47] + "..."
                results_lines.append(f"  {start_time:.1f}s {video_indicator}: {content_preview}")
            
            if len(selected_segments) > 5:
                results_lines.append(f"  ... and {len(selected_segments) - 5} more")
            
            results_lines.extend([
                "",
                "✅ Ready to export EDL!"
            ])
            
            # Update display
            self.results_text.config(state=tk.NORMAL)
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(1.0, "\n".join(results_lines))
            self.results_text.config(state=tk.DISABLED)
            
        except Exception as e:
            self.log_message(f"⚠️ Error updating results: {e}")
    
    def export_edl(self):
        """Export the generated script to EDL format"""
        if not self.generated_script:
            messagebox.showwarning("No Script", "Please create a script first.")
            return
        
        # Get output path
        if EDL_EXPORT_AVAILABLE:
            filetypes = [("EDL files", "*.edl"), ("All files", "*.*")]
            default_name = f"{self.project_name}.edl"
        else:
            filetypes = [("Text files", "*.txt"), ("All files", "*.*")]
            default_name = f"{self.project_name}.txt"
        
        output_path = filedialog.asksaveasfilename(
            title="Save Export File",
            initialfile=default_name,
            filetypes=filetypes
        )
        
        if not output_path:
            return
        
        try:
            if EDL_EXPORT_AVAILABLE:
                self.log_message("📤 Exporting EDL...")
                success = export_script_to_edl(
                    script=self.generated_script,
                    video_paths=self.video_files,
                    output_path=output_path,
                    sequence_name=os.path.splitext(os.path.basename(output_path))[0],
                    custom_clip_names=self.custom_clip_names
                )
                
                if success:
                    self.log_message(f"✅ EDL exported: {os.path.basename(output_path)}")
                    messagebox.showinfo("Export Complete", f"EDL file exported successfully!\n{output_path}")
                else:
                    self.log_message("❌ EDL export failed")
                    messagebox.showerror("Export Failed", "EDL export failed. Check logs for details.")
            else:
                # Fallback to text export
                self.log_message("📤 Exporting text...")
                self._export_text_representation(output_path)
                self.log_message(f"✅ Text exported: {os.path.basename(output_path)}")
                messagebox.showinfo("Export Complete", f"Text file exported successfully!\n{output_path}")
                
        except Exception as e:
            self._handle_error("Export", e)
    
    def _export_text_representation(self, output_path):
        """Export script as text representation - simplified"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"Smart Edit Project: {self.project_name}\n")
            f.write("=" * 50 + "\n\n")
            
            # Video files
            f.write(f"Videos ({len(self.video_files)}):\n")
            for i, video_path in enumerate(self.video_files):
                f.write(f"  {i+1}. {os.path.basename(video_path)}\n")
            
            # User prompt
            user_prompt = getattr(self.generated_script, 'user_prompt', '')
            if user_prompt:
                f.write(f"\nInstructions:\n{user_prompt}\n\n")
            
            # Timeline segments
            f.write("Timeline:\n" + "-" * 20 + "\n")
            segments = getattr(self.generated_script, 'segments', [])
            selected_segments = [s for s in segments if getattr(s, 'keep', True)]
            
            for i, segment in enumerate(selected_segments):
                start_time = getattr(segment, 'start_time', 0)
                end_time = getattr(segment, 'end_time', 0)
                content = getattr(segment, 'content', 'No content')
                video_idx = getattr(segment, 'video_index', 0)
                
                f.write(f"{i+1}. {start_time:.2f}s-{end_time:.2f}s [Video {video_idx + 1}]: {content}\n")
    
    def log_message(self, message):
        """Add a message to the log display"""
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            logger.info(message)
        except tk.TclError:
            # Widget might be destroyed
            pass
    
    def update_status(self, message):
        """Update the status bar"""
        try:
            self.status_var.set(message)
        except tk.TclError:
            # Widget might be destroyed
            pass
    
    def run(self):
        """Start the application"""
        self.root.mainloop()

def main():
    """Main entry point"""
    try:
        app = SmartEditMainWindow()
        app.run()
    except Exception as e:
        logging.error(f"Application failed to start: {e}")
        messagebox.showerror("Startup Error", f"Failed to start Smart Edit:\n{str(e)}")

if __name__ == "__main__":
    main()