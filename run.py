#!/usr/bin/env python3
"""
Smart Edit - AI Video Editor
Main Entry Point - Updated for EDL Export Workflow

Launch the Smart Edit application with GUI or process videos via command line.
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def check_dependencies():
    """Check if required dependencies are installed"""
    missing_deps = []
    
    try:
        import whisper
    except ImportError:
        missing_deps.append("openai-whisper")
    
    try:
        import openai
    except ImportError:
        missing_deps.append("openai")
    
    try:
        import torch
    except ImportError:
        missing_deps.append("torch")
    
    try:
        from dotenv import load_dotenv
    except ImportError:
        missing_deps.append("python-dotenv")
    
    if missing_deps:
        print("❌ Missing required dependencies:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print("\nInstall with: pip install " + " ".join(missing_deps))
        return False
    
    return True

def check_ffmpeg():
    """Check if FFmpeg is available"""
    import subprocess
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ FFmpeg not found. Please install FFmpeg:")
        print("   Windows: Download from https://ffmpeg.org/download.html")
        print("   Mac: brew install ffmpeg")
        print("   Linux: sudo apt install ffmpeg")
        return False

def launch_gui():
    """Launch the GUI application"""
    try:
        # Updated import path for new UI structure
        from smart_edit.ui.main_window import SmartEditMainWindow
        print("🎬 Starting Smart Edit GUI...")
        app = SmartEditMainWindow()
        app.run()
        return True
    except ImportError as e:
        print("❌ GUI components not available.")
        print(f"   Import error: {e}")
        print("   Please use command-line mode instead:")
        print("   python run.py video.mp4 --prompt 'Your editing instructions'")
        return False
    except Exception as e:
        print(f"❌ Failed to launch GUI: {e}")
        print("Make sure all dependencies are installed and try again.")
        return False

def validate_video_files(video_paths):
    """Validate video files exist and are accessible"""
    errors = []
    
    for video_path in video_paths:
        path = Path(video_path)
        
        # Check if file exists
        if not path.exists():
            errors.append(f"{video_path}: File not found")
            continue
            
        # Check if it's a file (not directory)
        if not path.is_file():
            errors.append(f"{video_path}: Not a file")
            continue
            
        # Check if readable
        if not os.access(path, os.R_OK):
            errors.append(f"{video_path}: File not readable")
            continue
            
        # Basic video format check
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
        if path.suffix.lower() not in video_extensions:
            errors.append(f"{video_path}: Unsupported format (expected: {', '.join(video_extensions)})")
    
    if errors:
        print("❌ Video file validation failed:")
        for error in errors:
            print(f"   - {error}")
        return False
    
    return True

def validate_output_path(output_path):
    """Validate output path is writable"""
    if not output_path:
        return True
        
    output_path = Path(output_path)
    
    # Check if directory exists and is writable
    parent_dir = output_path.parent
    if not parent_dir.exists():
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"❌ Cannot create output directory {parent_dir}: {e}")
            return False
    
    if not os.access(parent_dir, os.W_OK):
        print(f"❌ Output directory not writable: {parent_dir}")
        return False
    
    # Check if file already exists and is writable
    if output_path.exists() and not os.access(output_path, os.W_OK):
        print(f"❌ Output file not writable: {output_path}")
        return False
    
    return True

def process_command_line_transcription_only(video_paths, output_path=None):
    """Process videos via command line - transcription only (new workflow step 1)"""
    try:
        # Import the updated pipeline
        from smart_edit.core.pipeline import quick_transcribe_videos
        
        def progress_callback(message, percent):
            print(f"[{percent:5.1f}%] {message}")
        
        print(f"🎤 Transcribing {len(video_paths)} video(s)...")
        print("📝 After transcription, use GUI or provide --prompt for script generation")
        
        # Generate project name from first video
        project_name = Path(video_paths[0]).stem + "_project"
        
        # Step 1: Transcribe videos
        result = quick_transcribe_videos(
            project_name=project_name,
            video_paths=video_paths,
            progress_callback=progress_callback
        )
        
        if result.success:
            print("✅ Transcription completed successfully!")
            
            # Save transcription results if output path specified
            if output_path:
                try:
                    # Export transcription summary
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write("Smart Edit Transcription Results\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(f"Project: {project_name}\n")
                        f.write(f"Videos processed: {len(video_paths)}\n\n")
                        
                        for i, video_path in enumerate(video_paths):
                            f.write(f"Video {i+1}: {os.path.basename(video_path)}\n")
                        
                        f.write("\nTotal transcription segments: Available\n")
                        f.write("\nNext steps:\n")
                        f.write("1. Use GUI: python run.py --gui\n")
                        f.write(f"2. Or provide prompt: python run.py {' '.join(video_paths)} --prompt 'Your instructions'\n")
                    
                    print(f"📤 Transcription summary saved to: {output_path}")
                except Exception as e:
                    print(f"⚠️  Could not save transcription summary: {e}")
            
            print("\n🎬 Next Steps:")
            print("   1. Launch GUI: python run.py --gui")
            print("   2. Or use prompt: python run.py video.mp4 --prompt 'Create a 10-minute tutorial...'")
            
            return True
        else:
            print(f"❌ Transcription failed: {result.message}")
            return False
            
    except ImportError as e:
        print(f"❌ Required modules not found: {e}")
        print("   Make sure the updated pipeline is implemented")
        return False
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_command_line_with_prompt(video_paths, user_prompt, target_duration=10, output_path=None):
    """Process videos with user prompt - complete workflow via command line"""
    try:
        # Import updated modules
        from smart_edit.core.pipeline import quick_transcribe_videos, quick_generate_script, quick_export_script
        
        def progress_callback(message, percent):
            print(f"[{percent:5.1f}%] {message}")
        
        print(f"🎬 Processing {len(video_paths)} video(s) with user prompt...")
        print(f"📝 Prompt: {user_prompt[:100]}{'...' if len(user_prompt) > 100 else ''}")
        print(f"🎯 Target duration: {target_duration} minutes")
        
        # Generate project name
        project_name = Path(video_paths[0]).stem + "_project"
        
        # Step 1: Transcribe videos
        print("\n📋 Step 1: Transcribing videos...")
        transcription_result = quick_transcribe_videos(
            project_name=project_name,
            video_paths=video_paths,
            progress_callback=progress_callback
        )
        
        if not transcription_result.success:
            print(f"❌ Transcription failed: {transcription_result.message}")
            return False
        
        print("✅ Transcription completed!")
        
        # Step 2: Generate script from prompt
        print("\n🤖 Step 2: Generating script from prompt...")
        script_result = quick_generate_script(
            transcription_results=transcription_result.data,
            user_prompt=user_prompt,
            target_duration_minutes=target_duration,
            progress_callback=progress_callback
        )
        
        if not script_result.success:
            print(f"❌ Script generation failed: {script_result.message}")
            return False
        
        print("✅ Script generation completed!")
        
        # Step 3: Export results
        if output_path:
            print("\n📤 Step 3: Exporting results...")
            
            # Determine export format from file extension
            output_ext = Path(output_path).suffix.lower()
            if output_ext == '.edl':
                export_format = "edl"
            elif output_ext == '.json':
                export_format = "json"
            else:
                export_format = "text"
            
            export_result = quick_export_script(
                generated_script=script_result.data,
                video_paths=video_paths,  # Fixed: Pass video_paths
                output_path=output_path,
                export_format=export_format,
                progress_callback=progress_callback
            )
            
            if export_result.success:
                print(f"✅ Export completed: {output_path}")
            else:
                print(f"❌ Export failed: {export_result.message}")
                return False
        
        # Show summary
        generated_script = script_result.data
        segments_count = len(getattr(generated_script, 'segments', []))
        estimated_duration = getattr(generated_script, 'estimated_duration_seconds', 0) / 60
        
        print(f"\n🎉 Processing completed successfully!")
        print(f"📊 Generated script with {segments_count} segments")
        print(f"📊 Estimated duration: {estimated_duration:.1f} minutes")
        
        if output_path:
            print(f"📤 Results exported to: {output_path}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Required modules not found: {e}")
        print("   Make sure the updated pipeline modules are implemented")
        return False
    except Exception as e:
        print(f"❌ Command line processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_version():
    """Show version information"""
    print("Smart Edit - AI Video Editor v2.0")
    print("Built with Python, OpenAI APIs, and FFmpeg")
    print("")
    print("NEW WORKFLOW:")
    print("• Load videos → Transcribe → User prompt → AI script → Review → Export")
    print("")
    print("Features:")
    print("• High-accuracy transcription with Whisper AI")
    print("• User prompt-driven script generation with GPT-4o-mini")
    print("• Interactive script review and editing")
    print("• EDL (Edit Decision List) export for universal compatibility")

def show_examples():
    """Show usage examples"""
    print("Smart Edit Usage Examples (Updated Workflow):")
    print("")
    print("1. Launch GUI (recommended):")
    print("   python run.py")
    print("   python run.py --gui")
    print("")
    print("2. Transcription only (then use GUI for script):")
    print("   python run.py video.mp4")
    print("   python run.py video1.mp4 video2.mp4 video3.mp4")
    print("")
    print("3. Complete workflow with prompt:")
    print("   python run.py video.mp4 --prompt 'Create a 10-minute tutorial about Python'")
    print("   python run.py video.mp4 --prompt 'Make an engaging vlog' --duration 8")
    print("")
    print("4. Export to different formats:")
    print("   python run.py video.mp4 --prompt 'Educational content' --output script.edl")
    print("   python run.py video.mp4 --prompt 'Quick highlights' --output results.json")
    print("")
    print("5. Multiple videos with prompt:")
    print("   python run.py video1.mp4 video2.mp4 --prompt 'Compile best moments' --duration 15")
    print("")
    print("6. Check system setup:")
    print("   python run.py --check-deps")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Smart Edit - AI Video Editor v2.0 (EDL Export Workflow)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EDL EXPORT Examples:
  python run.py                                    # Launch GUI
  python run.py video.mp4                          # Transcribe only
  python run.py video.mp4 --prompt "Make tutorial" # Complete workflow
  python run.py video1.mp4 video2.mp4 --prompt "Edit compilation" --duration 20
        """
    )
    
    parser.add_argument(
        'videos', 
        nargs='*', 
        help='Video file(s) to process (leave empty for GUI mode)'
    )
    
    parser.add_argument(
        '--gui', 
        action='store_true', 
        help='Force GUI mode (default if no videos specified)'
    )
    
    parser.add_argument(
        '--prompt',
        help='User prompt for script generation (enables complete workflow)'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        default=10,
        help='Target duration in minutes (default: 10, used with --prompt)'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output file path (.edl for EDL format, .json for data, .txt for text)'
    )
    
    parser.add_argument(
        '--version',
        action='store_true',
        help='Show version information'
    )
    
    parser.add_argument(
        '--examples',
        action='store_true',
        help='Show usage examples'
    )
    
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Check dependencies and exit'
    )
    
    args = parser.parse_args()
    
    # Handle special commands
    if args.version:
        show_version()
        return 0
    
    if args.examples:
        show_examples()
        return 0
    
    if args.check_deps:
        print("🔍 Checking dependencies...")
        deps_ok = check_dependencies()
        ffmpeg_ok = check_ffmpeg()
        
        if deps_ok and ffmpeg_ok:
            print("✅ All dependencies are installed!")
            return 0
        else:
            return 1
    
    # Validate duration
    if args.duration <= 0:
        print("❌ Duration must be positive")
        return 1
    
    # Check dependencies first
    if not check_dependencies():
        return 1
    
    if not check_ffmpeg():
        return 1
    
    # Determine mode
    if args.gui or not args.videos:
        # GUI mode
        success = launch_gui()
        return 0 if success else 1
    
    else:
        # Command line mode
        video_paths = args.videos
        
        # Validate video files
        if not validate_video_files(video_paths):
            return 1
        
        # Generate output path if not specified
        output_path = args.output
        if not output_path and len(video_paths) == 1:
            video_stem = Path(video_paths[0]).stem
            if args.prompt:
                output_path = f"{video_stem}_edited.edl"  # EDL for complete workflow
            else:
                output_path = f"{video_stem}_transcription.txt"  # Text for transcription only
        
        # Validate output path
        if not validate_output_path(output_path):
            return 1
        
        # Choose processing mode based on whether prompt is provided
        if args.prompt:
            # Complete workflow with user prompt
            success = process_command_line_with_prompt(
                video_paths, 
                args.prompt, 
                args.duration, 
                output_path
            )
        else:
            # Transcription only (user will use GUI for script generation)
            success = process_command_line_transcription_only(video_paths, output_path)
        
        return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)