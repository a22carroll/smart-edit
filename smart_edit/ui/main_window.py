"""
Smart Edit Main Window

Main application window for the Smart Edit video editing system.
Provides the primary interface for loading videos, processing, and reviewing results.
"""

import os
import sys
import threading
import logging
from pathlib import Path
from typing import Optional, List

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from transcription import transcribe_video, TranscriptionConfig
from script_generation import generate_script, ScriptGenerationConfig  
from angle_assignment import assign_camera_angles
from xml_export import export_single_cam_xml, export_multicam_xml
from ui.script_editor import ScriptEditorWindow

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SmartEditMainWindow:
    """Main application window for Smart Edit"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Smart Edit - AI Video Editor")
        self.root.geometry("1200x800")
        
        # Application state
        self.video_files = []
        self.transcription_result = None
        self.edit_script = None
        self.processing_thread = None
        
        # Create UI
        self._setup_ui()
        self._setup_menu()
        
        # Status
        self.update_status("Ready - Load video files to begin")
    
    def _setup_ui(self):
        """Set up the main user interface"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Smart Edit", font=("Arial", 24, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Left panel - File selection and controls
        left_frame = ttk.LabelFrame(main_frame, text="Video Files & Controls", padding="10")
        left_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # File selection
        ttk.Label(left_frame, text="Selected Videos:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.file_listbox = tk.Listbox(left_frame, height=6, width=40)
        self.file_listbox.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # File buttons
        file_button_frame = ttk.Frame(left_frame)
        file_button_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        
        ttk.Button(file_button_frame, text="Add Video(s)", command=self.add_videos).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(file_button_frame, text="Remove", command=self.remove_video).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(file_button_frame, text="Clear All", command=self.clear_videos).pack(side=tk.LEFT)
        
        # Processing controls
        ttk.Separator(left_frame, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        ttk.Label(left_frame, text="Processing:", font=("Arial", 12, "bold")).grid(row=4, column=0, sticky=tk.W, pady=(0, 10))
        
        self.process_button = ttk.Button(left_frame, text="🎬 Start Processing", command=self.start_processing)
        self.process_button.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Progress bar
        self.progress = ttk.Progressbar(left_frame, mode='indeterminate')
        self.progress.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Export controls
        ttk.Separator(left_frame, orient='horizontal').grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        ttk.Label(left_frame, text="Export:", font=("Arial", 12, "bold")).grid(row=8, column=0, sticky=tk.W, pady=(0, 10))
        
        self.review_button = ttk.Button(left_frame, text="📝 Review & Edit", command=self.open_script_editor, state=tk.DISABLED)
        self.review_button.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.export_button = ttk.Button(left_frame, text="📤 Export XML", command=self.export_xml, state=tk.DISABLED)
        self.export_button.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Right panel - Results and logs
        right_frame = ttk.LabelFrame(main_frame, text="Results & Logs", padding="10")
        right_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        # Results summary
        self.results_text = ScrolledText(right_frame, height=12, width=60, state=tk.DISABLED)
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Log output
        ttk.Label(right_frame, text="Processing Log:").grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        
        self.log_text = ScrolledText(right_frame, height=8, width=60, state=tk.DISABLED)
        self.log_text.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, padding="5")
        status_bar.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
    
    def _setup_menu(self):
        """Set up the application menu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Add Videos...", command=self.add_videos)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Settings...", command=self.show_settings)
        tools_menu.add_command(label="View Logs...", command=self.show_logs)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
    
    def add_videos(self):
        """Add video files to the processing list"""
        filetypes = [
            ("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv"),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=filetypes
        )
        
        for file_path in files:
            if file_path not in self.video_files:
                self.video_files.append(file_path)
                self.file_listbox.insert(tk.END, os.path.basename(file_path))
        
        self.update_status(f"{len(self.video_files)} video(s) loaded")
        self.log_message(f"Added {len(files)} video file(s)")
    
    def remove_video(self):
        """Remove selected video from the list"""
        selection = self.file_listbox.curselection()
        if selection:
            index = selection[0]
            self.file_listbox.delete(index)
            removed_file = self.video_files.pop(index)
            self.log_message(f"Removed: {os.path.basename(removed_file)}")
            self.update_status(f"{len(self.video_files)} video(s) loaded")
    
    def clear_videos(self):
        """Clear all videos from the list"""
        self.video_files.clear()
        self.file_listbox.delete(0, tk.END)
        self.transcription_result = None
        self.edit_script = None
        self.review_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        self.update_status("Ready - Load video files to begin")
        self.log_message("Cleared all video files")
    
    def start_processing(self):
        """Start the video processing pipeline"""
        if not self.video_files:
            messagebox.showwarning("No Videos", "Please add video files before processing.")
            return
        
        if self.processing_thread and self.processing_thread.is_alive():
            messagebox.showwarning("Processing", "Processing is already in progress.")
            return
        
        # Reset state
        self.transcription_result = None
        self.edit_script = None
        self.review_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        
        # Start processing in background thread
        self.processing_thread = threading.Thread(target=self._process_videos, daemon=True)
        self.processing_thread.start()
        
        # Update UI
        self.process_button.config(state=tk.DISABLED)
        self.progress.start()
        self.update_status("Processing videos...")
        self.log_message("Started video processing...")
    
    def _process_videos(self):
        """Process videos in background thread"""
        try:
            # Step 1: Transcription
            self.root.after(0, lambda: self.log_message("🎤 Starting transcription..."))
            
            if len(self.video_files) == 1:
                self.transcription_result = transcribe_video(self.video_files[0])
            else:
                self.transcription_result = transcribe_video(self.video_files)
            
            self.root.after(0, lambda: self.log_message(f"✅ Transcription complete: {len(self.transcription_result.segments)} segments"))
            
            # Step 2: Script Generation
            self.root.after(0, lambda: self.log_message("🤖 Generating edit script..."))
            
            self.edit_script = generate_script(self.transcription_result)
            
            self.root.after(0, lambda: self.log_message(f"✅ Edit script complete: {self.edit_script.compression_ratio:.1%} compression"))
            
            # Step 3: Camera Assignment (if multicam)
            if len(self.video_files) > 1:
                self.root.after(0, lambda: self.log_message("🎥 Assigning camera angles..."))
                
                camera_ids = [f"Camera_{i+1}" for i in range(len(self.video_files))]
                self.edit_script = assign_camera_angles(self.edit_script, camera_ids)
                
                self.root.after(0, lambda: self.log_message("✅ Camera angles assigned"))
            
            # Update UI on main thread
            self.root.after(0, self._processing_complete)
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.root.after(0, lambda: self.log_message(f"❌ {error_msg}"))
            self.root.after(0, lambda: messagebox.showerror("Processing Error", error_msg))
            self.root.after(0, self._processing_failed)
    
    def _processing_complete(self):
        """Handle successful processing completion"""
        self.progress.stop()
        self.process_button.config(state=tk.NORMAL)
        self.review_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        
        # Show results summary
        self._update_results_display()
        
        self.update_status("Processing complete - Ready to review and export")
        self.log_message("🎉 All processing complete!")
    
    def _processing_failed(self):
        """Handle processing failure"""
        self.progress.stop()
        self.process_button.config(state=tk.NORMAL)
        self.update_status("Processing failed - Check logs for details")
    
    def _update_results_display(self):
        """Update the results display with processing summary"""
        if not self.transcription_result or not self.edit_script:
            return
        
        # Build results summary
        results = []
        results.append("=== PROCESSING RESULTS ===\n")
        
        # Transcription summary
        results.append("📝 TRANSCRIPTION:")
        results.append(f"  • Duration: {self.transcription_result.metadata['total_duration']:.1f} seconds")
        results.append(f"  • Segments: {len(self.transcription_result.segments)}")
        results.append(f"  • Language: {self.transcription_result.metadata['language_detected']}")
        results.append(f"  • Processing time: {self.transcription_result.metadata.get('processing_time', 'N/A')}s")
        results.append("")
        
        # Script generation summary
        results.append("🤖 EDIT DECISIONS:")
        results.append(f"  • Compression ratio: {self.edit_script.compression_ratio:.1%}")
        results.append(f"  • Original duration: {self.edit_script.original_duration:.1f}s")
        results.append(f"  • Final duration: {self.edit_script.estimated_final_duration:.1f}s")
        results.append(f"  • Segments kept: {self.edit_script.metadata['segments_kept']}")
        results.append(f"  • Segments removed: {self.edit_script.metadata['segments_removed']}")
        results.append("")
        
        # Camera assignment (if multicam)
        if len(self.video_files) > 1:
            results.append("🎥 CAMERA ASSIGNMENT:")
            results.append(f"  • Cameras: {len(self.video_files)}")
            results.append(f"  • Multicam workflow ready")
            results.append("")
        
        # Sample cuts
        results.append("📋 SAMPLE EDIT DECISIONS:")
        sample_cuts = [cut for cut in self.edit_script.cuts if cut.action.value in ["keep", "speed_up"]][:5]
        for i, cut in enumerate(sample_cuts):
            action_emoji = "✅" if cut.action.value == "keep" else "⚡"
            results.append(f"  {action_emoji} {cut.start_time:.1f}s-{cut.end_time:.1f}s: {cut.original_text[:50]}...")
        
        if len(self.edit_script.cuts) > 5:
            results.append(f"  ... and {len(self.edit_script.cuts) - 5} more")
        
        # Display results
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(1.0, "\n".join(results))
        self.results_text.config(state=tk.DISABLED)
    
    def open_script_editor(self):
        """Open the script editor window"""
        if not self.edit_script:
            messagebox.showwarning("No Script", "No edit script available. Please process videos first.")
            return
        
        try:
            # Create script editor window
            editor_window = ScriptEditorWindow(self.root, self.edit_script, self.transcription_result)
            
            # Wait for editor to close and get updated script
            self.root.wait_window(editor_window.window)
            
            # Check if script was modified
            if hasattr(editor_window, 'modified_script'):
                self.edit_script = editor_window.modified_script
                self.log_message("📝 Edit script updated from review")
                self._update_results_display()
        except Exception as e:
            self.log_message(f"❌ Error opening script editor: {e}")
            messagebox.showerror("Editor Error", f"Failed to open script editor: {e}")
    
    def export_xml(self):
        """Export the edit script to XML"""
        if not self.edit_script:
            messagebox.showwarning("No Script", "No edit script available. Please process videos first.")
            return
        
        # Choose output file
        output_path = filedialog.asksaveasfilename(
            title="Save Premiere Pro XML",
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        
        if not output_path:
            return
        
        try:
            # Export based on number of cameras
            if len(self.video_files) == 1:
                success = export_single_cam_xml(self.edit_script, self.video_files[0], output_path)
            else:
                # Create camera mapping
                camera_paths = {f"Camera_{i+1}": path for i, path in enumerate(self.video_files)}
                success = export_multicam_xml(self.edit_script, camera_paths, output_path)
            
            if success:
                self.log_message(f"✅ XML exported: {output_path}")
                messagebox.showinfo("Export Complete", f"XML exported successfully to:\n{output_path}")
            else:
                self.log_message("❌ XML export failed")
                messagebox.showerror("Export Failed", "Failed to export XML. Check logs for details.")
                
        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            self.log_message(f"❌ {error_msg}")
            messagebox.showerror("Export Error", error_msg)
    
    def show_settings(self):
        """Show settings dialog"""
        messagebox.showinfo("Settings", "Settings dialog not yet implemented.\nConfiguration is currently handled via .env file.")
    
    def show_logs(self):
        """Show detailed logs dialog"""
        log_window = tk.Toplevel(self.root)
        log_window.title("Detailed Logs")
        log_window.geometry("800x600")
        
        log_text = ScrolledText(log_window, state=tk.DISABLED)
        log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Copy current log content
        current_log = self.log_text.get(1.0, tk.END)
        log_text.config(state=tk.NORMAL)
        log_text.insert(1.0, current_log)
        log_text.config(state=tk.DISABLED)
    
    def show_about(self):
        """Show about dialog"""
        about_text = """Smart Edit - AI Video Editor

An intelligent video editing system that uses AI to automatically generate edit decisions from raw footage.

Features:
• High-accuracy transcription with Whisper
• AI-powered content analysis with GPT-4
• Intelligent cut decisions and pacing
• Multi-camera angle assignment
• Premiere Pro XML export

Built with Python, OpenAI APIs, and FFmpeg.
"""
        messagebox.showinfo("About Smart Edit", about_text)
    
    def log_message(self, message):
        """Add a message to the log display"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Also log to console
        logger.info(message)
    
    def update_status(self, message):
        """Update the status bar"""
        self.status_var.set(message)
    
    def run(self):
        """Start the application"""
        self.root.mainloop()

def main():
    """Main entry point"""
    app = SmartEditMainWindow()
    app.run()

if __name__ == "__main__":
    main()