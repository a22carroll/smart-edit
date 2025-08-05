"""
Smart Edit Main Window - Updated for Prompt-Driven Workflow

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

try:
    from transcription import transcribe_video, TranscriptionConfig
    from script_generation import GeneratedScript, generate_script_from_prompt
    from ui.script_editor import show_script_editor
    from xml_export import export_script_to_xml  # Fixed import
    XML_EXPORT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Import error - {e}")
    XML_EXPORT_AVAILABLE = False
    # Define minimal fallbacks for development
    class TranscriptionConfig:
        pass
    class GeneratedScript:
        pass

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
        self.video_groups = {}  # Track which group each video belongs to
        self.selected_video_index = -1  # Track currently selected video
        self.transcription_results = []
        self.generated_script = None
        self.processing_thread = None
        self.project_name = "Untitled Project"
        
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
        
        # Project name
        project_frame = ttk.Frame(left_frame)
        project_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(project_frame, text="Project Name:").pack(side=tk.LEFT)
        self.project_name_var = tk.StringVar(value=self.project_name)
        project_entry = ttk.Entry(project_frame, textvariable=self.project_name_var, width=25)
        project_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        project_entry.bind("<KeyRelease>", self._on_project_name_change)
        
        # File selection
        ttk.Label(left_frame, text="Selected Videos:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        
        # File listbox with multicam grouping
        listbox_frame = ttk.Frame(left_frame)
        listbox_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        listbox_frame.columnconfigure(0, weight=1)
        listbox_frame.columnconfigure(1, weight=0)
        listbox_frame.columnconfigure(2, weight=0)
        
        # Video files list
        self.file_listbox = tk.Listbox(listbox_frame, height=6)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.file_listbox.bind('<<ListboxSelect>>', self._on_file_select)
        self.file_listbox.bind('<Button-1>', self._on_file_click)  # Additional click handler
        
        # Multicam group dropdown for selected file  
        group_frame = ttk.Frame(listbox_frame)
        group_frame.grid(row=0, column=1, sticky=(tk.N, tk.S), padx=(5, 0))
        
        ttk.Label(group_frame, text="Group:", font=("Arial", 8)).pack()
        self.group_var = tk.StringVar(value="Single")
        self.group_combo = ttk.Combobox(group_frame, textvariable=self.group_var, 
                                       values=["Single", "Multicam A", "Multicam B", "Multicam C"], 
                                       width=12, state="readonly")  # Increased width
        self.group_combo.pack(pady=(2, 0))
        self.group_combo.bind('<<ComboboxSelected>>', self._on_group_change)
        
        listbox_scroll = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        listbox_scroll.grid(row=0, column=2, sticky=(tk.N, tk.S))
        self.file_listbox.configure(yscrollcommand=listbox_scroll.set)
        
        # Store multicam groupings
        self.video_groups = {}  # {video_path: group_name}
        
        # Video type indicator
        self.video_type_label = ttk.Label(left_frame, text="No videos loaded", font=("Arial", 9))
        self.video_type_label.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        # File buttons
        file_button_frame = ttk.Frame(left_frame)
        file_button_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        
        ttk.Button(file_button_frame, text="Add Video(s)", command=self.add_videos).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(file_button_frame, text="Remove", command=self.remove_video).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(file_button_frame, text="Clear All", command=self.clear_videos).pack(side=tk.LEFT)
        
        # Processing controls
        ttk.Separator(left_frame, orient='horizontal').grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        ttk.Label(left_frame, text="Processing:", font=("Arial", 12, "bold")).grid(row=6, column=0, sticky=tk.W, pady=(0, 10))
        
        # Updated workflow: Just transcription, then prompt-driven script generation
        self.transcribe_button = ttk.Button(left_frame, text="🎤 Transcribe Videos", command=self.start_transcription)
        self.transcribe_button.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.script_button = ttk.Button(left_frame, text="📝 Create Script", command=self.open_script_generator, state=tk.DISABLED)
        self.script_button.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Progress bar
        self.progress = ttk.Progressbar(left_frame, mode='indeterminate')
        self.progress.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Export controls
        ttk.Separator(left_frame, orient='horizontal').grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        ttk.Label(left_frame, text="Export:", font=("Arial", 12, "bold")).grid(row=11, column=0, sticky=tk.W, pady=(0, 10))
        
        export_text = "📤 Export XML" if XML_EXPORT_AVAILABLE else "📤 Export (Text Only)"
        self.export_button = ttk.Button(left_frame, text=export_text, command=self.export_xml, state=tk.DISABLED)
        self.export_button.grid(row=12, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
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
        file_menu.add_command(label="New Project", command=self.new_project)
        file_menu.add_separator()
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
    
    def _on_project_name_change(self, event=None):
        """Handle project name changes"""
        self.project_name = self.project_name_var.get() or "Untitled Project"
    
    def _update_video_type_display(self):
        """Update the video type indicator based on groupings"""
        if not self.video_files:
            self.video_type_label.config(text="No videos loaded", foreground="gray")
            return
        
        # Count groups
        groups = {}
        for video_path in self.video_files:
            group = self.video_groups.get(video_path, "Single")
            if group not in groups:
                groups[group] = []
            groups[group].append(video_path)
        
        # Create display text
        group_info = []
        for group_name, videos in groups.items():
            if group_name == "Single":
                if len(videos) == 1:
                    group_info.append("1 single video")
                else:
                    group_info.append(f"{len(videos)} single videos")
            else:
                group_info.append(f"{group_name}: {len(videos)} videos")
        
        display_text = " | ".join(group_info)
        
        # Set color based on complexity
        if len(groups) == 1 and "Single" in groups:
            color = "blue"
            icon = "📹"
        else:
            color = "green" 
            icon = "🎥"
        
        self.video_type_label.config(text=f"{icon} {display_text}", foreground=color)
    
    def new_project(self):
        """Start a new project"""
        if self.video_files or self.transcription_results or self.generated_script:
            if not messagebox.askyesno("New Project", "This will clear all current work. Continue?"):
                return
        
        self.clear_videos()
        self.project_name = "Untitled Project"
        self.project_name_var.set(self.project_name)
        self.log_message("🆕 Started new project")
    
    def add_videos(self):
        """Add video files to the processing list"""
        filetypes = [
            ("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=filetypes
        )
        
        added_count = 0
        for file_path in files:
            if file_path not in self.video_files:
                self.video_files.append(file_path)
                # Default to "Single" group
                self.video_groups[file_path] = "Single"
                
                filename = os.path.basename(file_path)
                # Show file size
                try:
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    display_name = f"{filename} ({size_mb:.1f} MB) [Single]"
                except:
                    display_name = f"{filename} [Single]"
                
                self.file_listbox.insert(tk.END, display_name)
                added_count += 1
        
        if added_count > 0:
            self._update_video_type_display()
            self.update_status(f"{len(self.video_files)} video(s) loaded")
            self.log_message(f"📁 Added {added_count} video file(s)")
            
            # Auto-generate project name from first video if still default
            if self.project_name == "Untitled Project" and self.video_files:
                first_video = Path(self.video_files[0]).stem
                self.project_name = f"{first_video}_edit"
                self.project_name_var.set(self.project_name)
    
    def remove_video(self):
        """Remove selected video from the list"""
        selection = self.file_listbox.curselection()
        if selection:
            index = selection[0]
            self.file_listbox.delete(index)
            removed_file = self.video_files.pop(index)
            # Remove from groups tracking
            if removed_file in self.video_groups:
                del self.video_groups[removed_file]
            self.log_message(f"🗑️ Removed: {os.path.basename(removed_file)}")
            self._update_video_type_display()
            self.update_status(f"{len(self.video_files)} video(s) loaded")
            
            # Clear group selection
            self.group_var.set("Single")
            
            # Clear results if no videos left
            if not self.video_files:
                self._reset_processing_state()
    
    def clear_videos(self):
        """Clear all videos from the list"""
        self.video_files.clear()
        self.video_groups.clear()  # Clear group tracking
        self.selected_video_index = -1  # Reset selection
        self.file_listbox.delete(0, tk.END)
        self.group_var.set("Single") 
        self._reset_processing_state()
        self._update_video_type_display()
        self.update_status("Ready - Load video files to begin")
        self.log_message("🗑️ Cleared all video files")
    
    def _on_file_click(self, event=None):
        """Handle direct clicks on file list"""
        # Small delay to ensure selection is processed
        self.root.after(10, self._on_file_select)
    
    def _on_file_select(self, event=None):
        """Handle file selection in listbox"""
        try:
            selection = self.file_listbox.curselection()
            if selection and hasattr(self, 'group_var'):
                index = selection[0]
                if 0 <= index < len(self.video_files):
                    self.selected_video_index = index  # Store selected index
                    video_path = self.video_files[index]
                    current_group = self.video_groups.get(video_path, "Single")
                    self.group_var.set(current_group)
                    self.log_message(f"🎯 Selected: {os.path.basename(video_path)} [{current_group}]")
            else:
                # No selection - reset
                self.selected_video_index = -1
                self.group_var.set("Single")
        except Exception as e:
            self.log_message(f"⚠️ Error in file selection: {e}")
    
    def _on_group_change(self, event=None):
        """Handle group assignment change"""
        try:
            # Use stored index instead of current selection
            if self.selected_video_index >= 0 and self.selected_video_index < len(self.video_files):
                index = self.selected_video_index
                video_path = self.video_files[index]
                new_group = self.group_var.get()
                old_group = self.video_groups.get(video_path, "Single")
                
                if new_group == old_group:
                    return  # No change needed
                
                # Update group assignment
                self.video_groups[video_path] = new_group
                
                # Update listbox display
                filename = os.path.basename(video_path)
                try:
                    size_mb = os.path.getsize(video_path) / (1024 * 1024)
                    display_name = f"{filename} ({size_mb:.1f} MB) [{new_group}]"
                except:
                    display_name = f"{filename} [{new_group}]"
                
                # Safely update listbox
                self.file_listbox.delete(index)
                self.file_listbox.insert(index, display_name)
                self.file_listbox.select_set(index)  # Re-select the item
                
                self._update_video_type_display()
                self.log_message(f"📁 {filename}: {old_group} → {new_group}")
            else:
                self.log_message(f"⚠️ No valid file selected (index: {self.selected_video_index})")
        except Exception as e:
            self.log_message(f"⚠️ Error changing group: {e}")
    
    def _get_video_groups(self):
        """Get videos organized by groups for export"""
        groups = {}
        for video_path in self.video_files:
            group = self.video_groups.get(video_path, "Single")
            if group not in groups:
                groups[group] = []
            groups[group].append(video_path)
        return groups
    
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
        
        # Reset transcription state
        self.transcription_results.clear()
        self.generated_script = None
        self.script_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        
        # Start transcription in background thread
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
            total_videos = len(self.video_files)
            
            for i, video_path in enumerate(self.video_files):
                video_name = os.path.basename(video_path)
                self.root.after(0, lambda v=video_name, idx=i+1, total=total_videos: 
                               self.log_message(f"🎤 Transcribing {idx}/{total}: {v}"))
                
                # Transcribe individual video
                result = transcribe_video(video_path)
                self.transcription_results.append(result)
                
                duration_mins = result.metadata.get('total_duration', 0) / 60
                segment_count = len(result.segments)
                self.root.after(0, lambda v=video_name, d=duration_mins, s=segment_count:
                               self.log_message(f"✅ Completed: {v} ({d:.1f}min, {s} segments)"))
            
            # Update UI on main thread
            self.root.after(0, self._transcription_complete)
            
        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            self.root.after(0, lambda: self.log_message(f"❌ {error_msg}"))
            self.root.after(0, lambda: messagebox.showerror("Transcription Error", error_msg))
            self.root.after(0, self._transcription_failed)
    
    def _transcription_complete(self):
        """Handle successful transcription completion"""
        self.progress.stop()
        self.transcribe_button.config(state=tk.NORMAL)
        self.script_button.config(state=tk.NORMAL)
        
        # Show transcription results
        self._update_transcription_results()
        
        self.update_status("Transcription complete - Ready to create script")
        self.log_message("🎉 All transcription complete! Click 'Create Script' to continue.")
    
    def _transcription_failed(self):
        """Handle transcription failure"""
        self.progress.stop()
        self.transcribe_button.config(state=tk.NORMAL)
        self.update_status("Transcription failed - Check logs for details")
    
    def _update_transcription_results(self):
        """Update the results display with transcription summary"""
        if not self.transcription_results:
            return
        
        # Build transcription summary
        results = []
        results.append("=== TRANSCRIPTION RESULTS ===\n")
        
        total_duration = sum(t.metadata.get('total_duration', 0) for t in self.transcription_results)
        total_segments = sum(len(t.segments) for t in self.transcription_results)
        
        results.append(f"📊 PROJECT OVERVIEW:")
        results.append(f"  • Project: {self.project_name}")
        results.append(f"  • Videos: {len(self.transcription_results)}")
        results.append(f"  • Type: {'Multi-Camera' if len(self.transcription_results) > 1 else 'Single Video'}")
        results.append(f"  • Total Duration: {total_duration/60:.1f} minutes")
        results.append(f"  • Total Segments: {total_segments}")
        results.append("")
        
        # Individual video details
        results.append("📹 VIDEO DETAILS:")
        for i, result in enumerate(self.transcription_results):
            video_name = os.path.basename(self.video_files[i])
            duration = result.metadata.get('total_duration', 0)
            segments = len(result.segments)
            language = result.metadata.get('language_detected', 'unknown')
            
            results.append(f"  Video {i+1}: {video_name}")
            results.append(f"    • Duration: {duration/60:.1f} min")
            results.append(f"    • Segments: {segments}")
            results.append(f"    • Language: {language}")
        
        results.append("")
        results.append("🎬 NEXT STEP:")
        results.append("  Click 'Create Script' to generate your video script")
        results.append("  with AI-powered editing decisions based on your prompt!")
        
        # Display results
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(1.0, "\n".join(results))
        self.results_text.config(state=tk.DISABLED)
    
    def open_script_generator(self):
        """Open the script generator/editor window"""
        if not self.transcription_results:
            messagebox.showwarning("No Transcription", "Please transcribe videos first.")
            return
        
        try:
            # Open the script editor with transcription results
            self.log_message("📝 Opening script generator...")
            
            final_script = show_script_editor(
                parent=self.root,
                transcriptions=self.transcription_results,
                project_name=self.project_name
            )
            
            if final_script:
                # User completed script generation
                self.generated_script = final_script
                self.log_message("✅ Script generation completed!")
                self._update_script_results()
                self.export_button.config(state=tk.NORMAL)
                self.update_status("Script ready - Ready to export")
            else:
                # User cancelled
                self.log_message("❌ Script generation cancelled")
                
        except Exception as e:
            error_msg = f"Script generator error: {str(e)}"
            self.log_message(f"❌ {error_msg}")
            messagebox.showerror("Script Generator Error", error_msg)
    
    def _update_script_results(self):
        """Update results display with script information"""
        if not self.generated_script:
            return
        
        results = []
        results.append("=== SCRIPT GENERATION RESULTS ===\n")
        
        # Script overview
        results.append("📝 GENERATED SCRIPT:")
        results.append(f"  • Title: {getattr(self.generated_script, 'title', 'Untitled')}")
        results.append(f"  • Target Duration: {getattr(self.generated_script, 'target_duration_minutes', 'N/A')} minutes")
        results.append(f"  • Estimated Duration: {getattr(self.generated_script, 'estimated_duration_seconds', 0)/60:.1f} minutes")
        results.append(f"  • Original Duration: {getattr(self.generated_script, 'original_duration_seconds', 0)/60:.1f} minutes")
        
        segments = getattr(self.generated_script, 'segments', [])
        selected_segments = [s for s in segments if getattr(s, 'keep', True)]
        
        results.append(f"  • Total Segments: {len(segments)}")
        results.append(f"  • Selected Segments: {len(selected_segments)}")
        
        if hasattr(self.generated_script, 'metadata'):
            compression = self.generated_script.metadata.get('compression_ratio', 0)
            results.append(f"  • Compression Ratio: {compression:.1%}")
        
        results.append("")
        
        # User prompt
        user_prompt = getattr(self.generated_script, 'user_prompt', '')
        if user_prompt:
            results.append("💭 USER INSTRUCTIONS:")
            # Show first 100 characters of prompt
            prompt_preview = user_prompt[:100] + "..." if len(user_prompt) > 100 else user_prompt
            results.append(f"  \"{prompt_preview}\"")
            results.append("")
        
        # Sample segments
        results.append("📋 SELECTED SEGMENTS:")
        for i, segment in enumerate(selected_segments[:5]):
            start_time = getattr(segment, 'start_time', 0)
            content = getattr(segment, 'content', 'No content')
            video_idx = getattr(segment, 'video_index', 0)
            
            video_indicator = f"[V{video_idx + 1}]" if len(self.transcription_results) > 1 else ""
            results.append(f"  {start_time:.1f}s {video_indicator}: {content[:60]}...")
        
        if len(selected_segments) > 5:
            results.append(f"  ... and {len(selected_segments) - 5} more segments")
        
        results.append("")
        results.append("📤 READY FOR EXPORT:")
        if XML_EXPORT_AVAILABLE:
            results.append("  Click 'Export XML' to create Premiere Pro project file")
        else:
            results.append("  XML export module not available - will export text format")
        
        # Display results
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(1.0, "\n".join(results))
        self.results_text.config(state=tk.DISABLED)
    
    def export_xml(self):
        """Export the generated script to XML with proper grouping"""
        if not self.generated_script:
            messagebox.showwarning("No Script", "Please create a script first.")
            return
        
        # Get video groups
        video_groups = self._get_video_groups()
        
        # Handle different export scenarios
        multicam_groups = {k: v for k, v in video_groups.items() if k != "Single" and len(v) > 1}
        single_videos = video_groups.get("Single", [])
        
        export_count = len(multicam_groups) + len(single_videos)
        
        if export_count == 0:
            messagebox.showwarning("No Valid Groups", "No videos to export.")
            return
        elif export_count == 1:
            # Single export - choose one file
            if multicam_groups:
                group_name, videos = next(iter(multicam_groups.items()))
                default_name = f"{self.project_name}_{group_name}.xml"
            else:
                videos = single_videos
                default_name = f"{self.project_name}.xml"
            
            self._export_single_group(videos, default_name, len(videos) > 1)
        else:
            # Multiple exports - choose directory
            directory = filedialog.askdirectory(title="Choose Export Directory")
            if directory:
                self._export_multiple_groups(video_groups, directory)
    
    def _export_single_group(self, videos, default_name, is_multicam):
        """Export a single group of videos"""
        if XML_EXPORT_AVAILABLE:
            filetypes = [("XML files", "*.xml"), ("All files", "*.*")]
        else:
            filetypes = [("Text files", "*.txt"), ("All files", "*.*")]
            default_name = default_name.replace('.xml', '.txt')
        
        output_path = filedialog.asksaveasfilename(
            title="Save Export File",
            initialfile=default_name,
            filetypes=filetypes
        )
        
        if not output_path:
            return
        
        self._perform_export(videos, output_path, is_multicam)
    
    def _export_multiple_groups(self, video_groups, directory):
        """Export multiple groups to separate files"""
        exported_count = 0
        
        for group_name, videos in video_groups.items():
            if group_name == "Single":
                # Export each single video separately
                for i, video in enumerate(videos):
                    filename = f"{self.project_name}_single_{i+1}.xml"
                    output_path = os.path.join(directory, filename)
                    if self._perform_export([video], output_path, False):
                        exported_count += 1
            else:
                # Export multicam group
                if len(videos) > 1:
                    filename = f"{self.project_name}_{group_name}.xml"
                    output_path = os.path.join(directory, filename)
                    if self._perform_export(videos, output_path, True):
                        exported_count += 1
        
        if exported_count > 0:
            messagebox.showinfo("Export Complete", 
                               f"Exported {exported_count} XML file(s) to:\n{directory}")
        else:
            messagebox.showerror("Export Failed", "No files were exported successfully.")
    
    def _perform_export(self, videos, output_path, is_multicam):
        """Perform the actual export"""
        try:
            if XML_EXPORT_AVAILABLE:
                self.log_message(f"📤 Exporting {'multicam' if is_multicam else 'single cam'} XML...")
                
                success = export_script_to_xml(
                    script=self.generated_script,
                    video_paths=videos,
                    output_path=output_path,
                    sequence_name=os.path.splitext(os.path.basename(output_path))[0]
                )
                
                if success:
                    self.log_message(f"✅ XML exported: {os.path.basename(output_path)}")
                    return True
                else:
                    self.log_message(f"❌ XML export failed: {os.path.basename(output_path)}")
                    return False
            else:
                # Fallback to text export
                self.log_message("📤 Exporting text representation...")
                self._export_text_representation(output_path)
                self.log_message(f"✅ Text export completed: {os.path.basename(output_path)}")
                return True
                
        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            self.log_message(f"❌ {error_msg}")
            return False
    
    def _export_text_representation(self, output_path):
        """Export script as text representation (fallback when XML export not available)"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"Smart Edit Project Export\n")
            f.write(f"=" * 50 + "\n\n")
            
            f.write(f"Project: {self.project_name}\n")
            f.write(f"Generated: {getattr(self.generated_script, 'title', 'Untitled')}\n")
            f.write(f"Type: {'Multi-Camera' if len(self.transcription_results) > 1 else 'Single Video'}\n")
            f.write(f"Videos: {len(self.video_files)}\n")
            
            # List video files
            f.write(f"\nVideo Files:\n")
            for i, video_path in enumerate(self.video_files):
                f.write(f"  {i+1}. {os.path.basename(video_path)}\n")
            
            # User prompt
            user_prompt = getattr(self.generated_script, 'user_prompt', '')
            if user_prompt:
                f.write(f"\nUser Instructions:\n{user_prompt}\n\n")
            
            # Full script text
            full_text = getattr(self.generated_script, 'full_text', '')
            if full_text:
                f.write(f"Generated Script:\n{'-' * 20}\n{full_text}\n\n")
            
            # Timeline data
            f.write(f"Timeline Segments:\n{'-' * 20}\n")
            segments = getattr(self.generated_script, 'segments', [])
            selected_segments = [s for s in segments if getattr(s, 'keep', True)]
            
            for i, segment in enumerate(selected_segments):
                start_time = getattr(segment, 'start_time', 0)
                end_time = getattr(segment, 'end_time', 0)
                content = getattr(segment, 'content', 'No content')
                video_idx = getattr(segment, 'video_index', 0)
                
                f.write(f"{i+1}. {start_time:.2f}s - {end_time:.2f}s [Video {video_idx + 1}]: {content}\n")
    
    def show_settings(self):
        """Show settings dialog"""
        messagebox.showinfo("Settings", 
                           "Settings dialog not yet implemented.\n"
                           "Configuration is currently handled via .env file.\n\n"
                           "Available settings:\n"
                           "• OPENAI_API_KEY - Your OpenAI API key\n"
                           "• WHISPER_MODEL_SIZE - base, large-v3, etc.\n"
                           "• OPENAI_MODEL - gpt-4, gpt-3.5-turbo, etc.")
    
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
        about_text = """Smart Edit - AI Video Editor v2.0

An intelligent video editing system that uses AI to automatically 
generate edit decisions from raw footage based on user instructions.

NEW WORKFLOW:
1. Load video files (single video or multi-camera)
2. Transcribe with high-accuracy Whisper AI
3. Provide custom instructions for your video
4. AI generates script based on your vision
5. Review and edit the generated script
6. Export to Premiere Pro XML

Features:
• High-accuracy transcription with Whisper
• User prompt-driven script generation with GPT-4
• Full script text editing and review
• Multi-camera and single video support
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