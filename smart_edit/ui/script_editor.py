"""
Smart Edit Script Editor Window

Interactive editor for reviewing and modifying AI-generated edit decisions.
Allows users to override AI choices before final XML export.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Optional
import copy

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from script_generation import EditScript, CutDecision, EditAction, ConfidenceLevel
from transcription import TranscriptionResult

class ScriptEditorWindow:
    """Interactive editor for edit scripts"""
    
    def __init__(self, parent, edit_script: EditScript, transcription_result: Optional[TranscriptionResult] = None):
        self.parent = parent
        self.original_script = edit_script
        self.transcription_result = transcription_result
        
        # Create working copy
        self.edit_script = copy.deepcopy(edit_script)
        self.modified = False
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Smart Edit - Script Editor")
        self.window.geometry("1400x800")
        self.window.transient(parent)
        self.window.grab_set()
        
        # Track which cuts are selected
        self.selected_cuts = set()
        
        self._setup_ui()
        self._populate_cuts()
        self._update_summary()
    
    def _setup_ui(self):
        """Set up the script editor interface"""
        # Main container
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title and summary
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(title_frame, text="Edit Script Review", font=("Arial", 16, "bold")).pack(side=tk.LEFT)
        
        # Summary info
        self.summary_label = ttk.Label(title_frame, text="", font=("Arial", 10))
        self.summary_label.pack(side=tk.RIGHT)
        
        # Create paned window for main content
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Left panel - Cut list
        left_frame = ttk.LabelFrame(paned, text="Edit Decisions", padding="5")
        paned.add(left_frame, weight=2)
        
        # Controls frame
        controls_frame = ttk.Frame(left_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Bulk actions
        ttk.Label(controls_frame, text="Bulk Actions:").pack(side=tk.LEFT)
        ttk.Button(controls_frame, text="Keep Selected", command=self.keep_selected).pack(side=tk.LEFT, padx=(5, 2))
        ttk.Button(controls_frame, text="Remove Selected", command=self.remove_selected).pack(side=tk.LEFT, padx=(2, 2))
        ttk.Button(controls_frame, text="Speed Up Selected", command=self.speed_up_selected).pack(side=tk.LEFT, padx=(2, 5))
        
        # Filter controls
        filter_frame = ttk.Frame(controls_frame)
        filter_frame.pack(side=tk.RIGHT)
        
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_var = tk.StringVar(value="all")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_var, values=["all", "keep", "remove", "speed_up"], width=10)
        filter_combo.pack(side=tk.LEFT, padx=(0, 5))
        filter_combo.bind("<<ComboboxSelected>>", self._filter_cuts)
        
        ttk.Button(filter_frame, text="Refresh", command=self._populate_cuts).pack(side=tk.LEFT)
        
        # Cuts treeview
        self.tree_frame = ttk.Frame(left_frame)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview with scrollbars
        self.tree = ttk.Treeview(self.tree_frame, columns=("time", "duration", "action", "reason", "confidence", "text"), show="headings")
        
        # Configure columns
        self.tree.heading("time", text="Time")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("action", text="Action")
        self.tree.heading("reason", text="Reason")
        self.tree.heading("confidence", text="Confidence")
        self.tree.heading("text", text="Text")
        
        self.tree.column("time", width=80, minwidth=60)
        self.tree.column("duration", width=60, minwidth=50)
        self.tree.column("action", width=80, minwidth=60)
        self.tree.column("reason", width=150, minwidth=100)
        self.tree.column("confidence", width=80, minwidth=60)
        self.tree.column("text", width=300, minwidth=200)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        self.tree_frame.columnconfigure(0, weight=1)
        self.tree_frame.rowconfigure(0, weight=1)
        
        # Bind events
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_single_click)
        self.tree.bind("<Button-3>", self._on_right_click)  # Right click context menu
        
        # Right panel - Details and preview
        right_frame = ttk.LabelFrame(paned, text="Details & Preview", padding="5")
        paned.add(right_frame, weight=1)
        
        # Details section
        details_frame = ttk.LabelFrame(right_frame, text="Selected Cut Details", padding="5")
        details_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.details_text = ScrolledText(details_frame, height=8, state=tk.DISABLED)
        self.details_text.pack(fill=tk.BOTH, expand=True)
        
        # Quick edit controls
        edit_frame = ttk.LabelFrame(right_frame, text="Quick Edit", padding="5")
        edit_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Action buttons
        action_frame = ttk.Frame(edit_frame)
        action_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(action_frame, text="✅ Keep", command=lambda: self._change_action(EditAction.KEEP)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="❌ Remove", command=lambda: self._change_action(EditAction.REMOVE)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="⚡ Speed Up", command=lambda: self._change_action(EditAction.SPEED_UP)).pack(side=tk.LEFT)
        
        # Speed factor control
        speed_frame = ttk.Frame(edit_frame)
        speed_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(speed_frame, text="Speed Factor:").pack(side=tk.LEFT, padx=(0, 5))
        self.speed_var = tk.DoubleVar(value=1.5)
        speed_spin = ttk.Spinbox(speed_frame, from_=1.1, to=3.0, increment=0.1, textvariable=self.speed_var, width=10)
        speed_spin.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(speed_frame, text="Apply", command=self._apply_speed_factor).pack(side=tk.LEFT)
        
        # Timeline preview
        preview_frame = ttk.LabelFrame(right_frame, text="Timeline Preview", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        self.timeline_text = ScrolledText(preview_frame, height=10, state=tk.DISABLED)
        self.timeline_text.pack(fill=tk.BOTH, expand=True)
        
        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Reset All", command=self.reset_script).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Undo Changes", command=self.undo_changes).pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Save & Close", command=self.save_and_close).pack(side=tk.RIGHT, padx=(0, 10))
    
    def _populate_cuts(self):
        """Populate the cuts treeview"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Get filter
        filter_action = self.filter_var.get()
        
        # Add cuts
        for i, cut in enumerate(self.edit_script.cuts):
            # Apply filter
            if filter_action != "all" and cut.action.value != filter_action:
                continue
            
            # Format time
            time_str = f"{cut.start_time:.1f}s"
            duration_str = f"{cut.end_time - cut.start_time:.1f}s"
            
            # Format action with emoji
            action_emoji = {"keep": "✅", "remove": "❌", "speed_up": "⚡"}.get(cut.action.value, "?")
            action_str = f"{action_emoji} {cut.action.value}"
            
            # Confidence color
            confidence_str = cut.confidence.value
            
            # Truncate text
            text_preview = cut.original_text[:60] + "..." if len(cut.original_text) > 60 else cut.original_text
            
            # Insert item
            item_id = self.tree.insert("", tk.END, values=(
                time_str, duration_str, action_str, cut.reason, confidence_str, text_preview
            ))
            
            # Store cut index in item tags (more reliable than set)
            self.tree.item(item_id, tags=(f"cut_{i}",))
            
            # Color coding based on action
            if cut.action == EditAction.KEEP:
                self.tree.item(item_id, tags=(f"cut_{i}", "keep"))
            elif cut.action == EditAction.REMOVE:
                self.tree.item(item_id, tags=(f"cut_{i}", "remove"))
            elif cut.action == EditAction.SPEED_UP:
                self.tree.item(item_id, tags=(f"cut_{i}", "speed"))
        
        # Configure tags
        self.tree.tag_configure("keep", background="#e8f5e8")
        self.tree.tag_configure("remove", background="#ffe8e8")
        self.tree.tag_configure("speed", background="#fff3e0")
        
        self._update_timeline_preview()
    
    def _filter_cuts(self, event=None):
        """Filter cuts based on selection"""
        self._populate_cuts()
    
    def _get_cut_index_from_item(self, item):
        """Extract cut index from tree item tags"""
        tags = self.tree.item(item, "tags")
        for tag in tags:
            if tag.startswith("cut_"):
                try:
                    return int(tag.split("_")[1])
                except (IndexError, ValueError):
                    continue
        return None
    
    def _on_single_click(self, event):
        """Handle single click on tree item"""
        item = self.tree.selection()[0] if self.tree.selection() else None
        if item:
            self._show_cut_details(item)
    
    def _on_double_click(self, event):
        """Handle double click on tree item"""
        item = self.tree.selection()[0] if self.tree.selection() else None
        if item:
            self._edit_cut_dialog(item)
    
    def _on_right_click(self, event):
        """Handle right click context menu"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self._show_context_menu(event, item)
    
    def _show_cut_details(self, item):
        """Show details for selected cut"""
        cut_index = self._get_cut_index_from_item(item)
        if cut_index is None:
            return
            
        cut = self.edit_script.cuts[cut_index]
        
        # Build details text
        details = []
        details.append(f"=== CUT #{cut_index + 1} DETAILS ===\n")
        details.append(f"Time Range: {cut.start_time:.2f}s - {cut.end_time:.2f}s")
        details.append(f"Duration: {cut.end_time - cut.start_time:.2f} seconds")
        details.append(f"Action: {cut.action.value.upper()}")
        details.append(f"Reason: {cut.reason}")
        details.append(f"Confidence: {cut.confidence.value}")
        
        if hasattr(cut, 'speed_factor') and cut.speed_factor:
            details.append(f"Speed Factor: {cut.speed_factor:.1f}x")
        
        if hasattr(cut, 'camera_id') and cut.camera_id:
            details.append(f"Camera: {cut.camera_id}")
        
        details.append(f"\nOriginal Text:")
        details.append(f'"{cut.original_text}"')
        
        # Show transcription context if available
        if self.transcription_result:
            segment = next((s for s in self.transcription_result.segments if s.start == cut.start_time), None)
            if segment:
                details.append(f"\nTranscription Details:")
                details.append(f"Speaker: {segment.speaker}")
                details.append(f"Content Type: {segment.content_type}")
                details.append(f"Speech Rate: {segment.speech_rate}")
                details.append(f"Contains Filler: {segment.contains_filler}")
                details.append(f"Pause After: {segment.pause_after:.2f}s")
        
        # Display details
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)
        self.details_text.insert(1.0, "\n".join(details))
        self.details_text.config(state=tk.DISABLED)
    
    def _show_context_menu(self, event, item):
        """Show context menu for cut"""
        cut_index = self._get_cut_index_from_item(item)
        if cut_index is None:
            return
            
        context_menu = tk.Menu(self.window, tearoff=0)
        cut = self.edit_script.cuts[cut_index]
        
        context_menu.add_command(label="✅ Keep", command=lambda: self._change_cut_action(cut_index, EditAction.KEEP))
        context_menu.add_command(label="❌ Remove", command=lambda: self._change_cut_action(cut_index, EditAction.REMOVE))
        context_menu.add_command(label="⚡ Speed Up", command=lambda: self._change_cut_action(cut_index, EditAction.SPEED_UP))
        context_menu.add_separator()
        context_menu.add_command(label="📝 Edit Details...", command=lambda: self._edit_cut_dialog(item))
        
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
    
    def _change_action(self, new_action):
        """Change action for currently selected cut"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a cut to modify.")
            return
        
        item = selection[0]
        cut_index = self._get_cut_index_from_item(item)
        if cut_index is not None:
            self._change_cut_action(cut_index, new_action)
    
    def _change_cut_action(self, cut_index, new_action):
        """Change action for specific cut"""
        cut = self.edit_script.cuts[cut_index]
        old_action = cut.action
        
        cut.action = new_action
        cut.reason = f"User modified: {new_action.value}"
        cut.confidence = ConfidenceLevel.HIGH
        
        # Handle speed factor
        if new_action == EditAction.SPEED_UP and not cut.speed_factor:
            cut.speed_factor = self.speed_var.get()
        elif new_action != EditAction.SPEED_UP:
            cut.speed_factor = None
        
        self.modified = True
        self._populate_cuts()
        self._update_summary()
        
        # Re-select the modified item
        for item in self.tree.get_children():
            if self._get_cut_index_from_item(item) == cut_index:
                self.tree.selection_set(item)
                self._show_cut_details(item)
                break
    
    def _apply_speed_factor(self):
        """Apply speed factor to selected cut"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a cut to modify.")
            return
        
        item = selection[0]
        cut_index = self._get_cut_index_from_item(item)
        if cut_index is None:
            return
            
        cut = self.edit_script.cuts[cut_index]
        
        if cut.action == EditAction.SPEED_UP:
            cut.speed_factor = self.speed_var.get()
            self.modified = True
            self._populate_cuts()
            self._show_cut_details(item)
        else:
            messagebox.showwarning("Invalid Action", "Speed factor can only be applied to 'Speed Up' cuts.")
    
    def _edit_cut_dialog(self, item):
        """Open dialog to edit cut details"""
        cut_index = self._get_cut_index_from_item(item)
        if cut_index is None:
            return
            
        cut = self.edit_script.cuts[cut_index]
        
        # Create edit dialog
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Edit Cut #{cut_index + 1}")
        dialog.geometry("400x300")
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Edit form
        form_frame = ttk.Frame(dialog, padding="10")
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # Action selection
        ttk.Label(form_frame, text="Action:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        action_var = tk.StringVar(value=cut.action.value)
        action_combo = ttk.Combobox(form_frame, textvariable=action_var, values=["keep", "remove", "speed_up"])
        action_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Reason
        ttk.Label(form_frame, text="Reason:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        reason_var = tk.StringVar(value=cut.reason)
        reason_entry = ttk.Entry(form_frame, textvariable=reason_var)
        reason_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Speed factor (if applicable)
        ttk.Label(form_frame, text="Speed Factor:").grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        speed_var = tk.DoubleVar(value=cut.speed_factor or 1.5)
        speed_entry = ttk.Entry(form_frame, textvariable=speed_var)
        speed_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        form_frame.columnconfigure(1, weight=1)
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        def apply_changes():
            try:
                new_action = EditAction(action_var.get())
                cut.action = new_action
                cut.reason = reason_var.get()
                
                if new_action == EditAction.SPEED_UP:
                    cut.speed_factor = speed_var.get()
                else:
                    cut.speed_factor = None
                
                self.modified = True
                self._populate_cuts()
                self._update_summary()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply changes: {e}")
        
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Apply", command=apply_changes).pack(side=tk.RIGHT, padx=(0, 10))
    
    def keep_selected(self):
        """Keep all selected cuts"""
        self._bulk_action(EditAction.KEEP)
    
    def remove_selected(self):
        """Remove all selected cuts"""
        self._bulk_action(EditAction.REMOVE)
    
    def speed_up_selected(self):
        """Speed up all selected cuts"""
        self._bulk_action(EditAction.SPEED_UP)
    
    def _bulk_action(self, action):
        """Apply action to all selected cuts"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select cuts to modify.")
            return
        
        count = 0
        for item in selection:
            cut_index = self._get_cut_index_from_item(item)
            if cut_index is None:
                continue
                
            cut = self.edit_script.cuts[cut_index]
            
            cut.action = action
            cut.reason = f"User bulk action: {action.value}"
            cut.confidence = ConfidenceLevel.HIGH
            
            if action == EditAction.SPEED_UP:
                cut.speed_factor = self.speed_var.get()
            else:
                cut.speed_factor = None
            
            count += 1
        
        self.modified = True
        self._populate_cuts()
        self._update_summary()
        
        messagebox.showinfo("Bulk Action", f"Applied '{action.value}' to {count} cut(s).")
    
    def _update_summary(self):
        """Update the summary information"""
        keep_count = sum(1 for cut in self.edit_script.cuts if cut.action == EditAction.KEEP)
        remove_count = sum(1 for cut in self.edit_script.cuts if cut.action == EditAction.REMOVE)
        speed_count = sum(1 for cut in self.edit_script.cuts if cut.action == EditAction.SPEED_UP)
        
        # Recalculate compression ratio
        total_kept_duration = sum(
            cut.end_time - cut.start_time for cut in self.edit_script.cuts 
            if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]
        )
        
        if self.edit_script.original_duration > 0:
            compression_ratio = total_kept_duration / self.edit_script.original_duration
        else:
            compression_ratio = 0.0
        
        summary_text = f"Keep: {keep_count} | Remove: {remove_count} | Speed: {speed_count} | Compression: {compression_ratio:.1%}"
        if self.modified:
            summary_text += " (Modified)"
        
        self.summary_label.config(text=summary_text)
    
    def _update_timeline_preview(self):
        """Update the timeline preview"""
        timeline = []
        timeline.append("=== TIMELINE PREVIEW ===\n")
        
        current_time = 0.0
        kept_cuts = [cut for cut in self.edit_script.cuts if cut.action in [EditAction.KEEP, EditAction.SPEED_UP]]
        
        for i, cut in enumerate(kept_cuts[:10]):  # Show first 10 cuts
            duration = cut.end_time - cut.start_time
            if cut.speed_factor:
                duration = duration / cut.speed_factor
                speed_note = f" ({cut.speed_factor:.1f}x)"
            else:
                speed_note = ""
            
            camera_note = ""
            if hasattr(cut, 'camera_id') and cut.camera_id:
                camera_note = f" [{cut.camera_id}]"
            
            timeline.append(f"{current_time:6.1f}s - {current_time + duration:6.1f}s: {cut.original_text[:40]}...{speed_note}{camera_note}")
            current_time += duration
        
        if len(kept_cuts) > 10:
            timeline.append(f"\n... and {len(kept_cuts) - 10} more cuts")
        
        timeline.append(f"\nTotal Timeline Duration: {current_time:.1f}s")
        
        # Display timeline
        self.timeline_text.config(state=tk.NORMAL)
        self.timeline_text.delete(1.0, tk.END)
        self.timeline_text.insert(1.0, "\n".join(timeline))
        self.timeline_text.config(state=tk.DISABLED)
    
    def reset_script(self):
        """Reset script to original state"""
        if messagebox.askyesno("Reset Script", "Are you sure you want to reset all changes?"):
            self.edit_script = copy.deepcopy(self.original_script)
            self.modified = False
            self._populate_cuts()
            self._update_summary()
    
    def undo_changes(self):
        """Undo recent changes"""
        # Simple implementation - just reset to original
        self.reset_script()
    
    def save_and_close(self):
        """Save changes and close window"""
        if self.modified:
            # Update the script's metadata
            keep_count = sum(1 for cut in self.edit_script.cuts if cut.action == EditAction.KEEP)
            remove_count = sum(1 for cut in self.edit_script.cuts if cut.action == EditAction.REMOVE)
            
            self.edit_script.metadata.update({
                "segments_kept": keep_count,
                "segments_removed": remove_count,
                "user_modified": True
            })
        
        # Store modified script
        self.modified_script = self.edit_script
        self.window.destroy()
    
    def cancel(self):
        """Cancel without saving"""
        if self.modified:
            if messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Are you sure you want to cancel?"):
                self.window.destroy()
        else:
            self.window.destroy()

if __name__ == "__main__":
    # Test the script editor with dummy data
    from script_generation import EditScript, CutDecision, EditAction, ConfidenceLevel
    
    # Create test data
    test_cuts = [
        CutDecision(0, 0.0, 3.0, "Hello world", EditAction.KEEP, "Important", ConfidenceLevel.HIGH),
        CutDecision(1, 3.5, 7.0, "Um, this is filler", EditAction.REMOVE, "Filler", ConfidenceLevel.HIGH),
        CutDecision(2, 7.5, 10.0, "Key information here", EditAction.KEEP, "Main point", ConfidenceLevel.HIGH)
    ]
    
    test_script = EditScript(
        cuts=test_cuts,
        transitions=[],
        estimated_final_duration=6.0,
        original_duration=10.0,
        compression_ratio=0.6,
        metadata={}
    )
    
    root = tk.Tk()
    root.withdraw()  # Hide main window
    
    editor = ScriptEditorWindow(root, test_script)
    root.mainloop()