#!/usr/bin/env python3
"""
Smart Edit - AI Video Editor
Main Entry Point

Launch the Smart Edit application with GUI or process videos via command line.
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to Python path (not smart_edit subfolder)
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
        # Try to import UI components
        from smart_edit.ui.main_window import SmartEditMainWindow
        print("🎬 Starting Smart Edit GUI...")
        app = SmartEditMainWindow()
        app.run()
        return True
    except ImportError as e:
        print("❌ GUI components not available.")
        print("   The UI module is not yet implemented.")
        print("   Please use command-line mode instead:")
        print("   python run.py video.mp4")
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

def process_command_line(video_paths, output_path=None, compression=0.7):
    """Process videos via command line using available modules"""
    try:
        # Import the modules we know exist
        from smart_edit.transcription import transcribe_video
        from smart_edit.script_generation import generate_script
        
        def progress_callback(message, percent):
            print(f"[{percent:5.1f}%] {message}")
        
        print(f"🎬 Processing {len(video_paths)} video(s)...")
        print(f"📊 Target compression: {compression:.1%}")
        
        # For now, process first video only (until multicam is implemented)
        if len(video_paths) > 1:
            print("⚠️  Multiple videos detected. Processing first video only.")
            print("   Full multicam support coming soon!")
        
        video_path = video_paths[0]
        
        # Step 1: Transcribe
        progress_callback("Transcribing audio...", 10)
        transcription_result = transcribe_video(video_path)
        
        if not transcription_result:
            print("❌ Transcription failed")
            return False
        
        progress_callback("Transcription complete", 50)
        
        # Step 2: Generate script
        progress_callback("Generating edit script...", 60)
        edit_script = generate_script(transcription_result, target_compression=compression)
        
        if not edit_script:
            print("❌ Script generation failed")
            return False
        
        progress_callback("Script generation complete", 90)
        
        # Step 3: Output results
        if output_path:
            # For now, save a simple representation
            # TODO: Replace with actual XML export when xml_export module is ready
            try:
                with open(output_path, 'w') as f:
                    f.write(f"# Smart Edit Results for {video_path}\n")
                    f.write(f"# Compression: {edit_script.compression_ratio:.1%}\n")
                    f.write(f"# Segments: {len(edit_script.cuts)}\n\n")
                    
                    for i, cut in enumerate(edit_script.cuts):
                        f.write(f"Segment {i+1}: {cut.action} - {cut.start_time:.2f}s to {cut.end_time:.2f}s\n")
                
                progress_callback(f"Results saved to {output_path}", 100)
                print(f"📤 Results exported to: {output_path}")
            except Exception as e:
                print(f"❌ Failed to save output: {e}")
                return False
        else:
            progress_callback("Processing complete", 100)
            print(f"📋 Edit script generated successfully")
        
        # Show summary
        print(f"✅ Processing completed!")
        print(f"📊 Final compression: {edit_script.compression_ratio:.1%}")
        print(f"📊 Segments processed: {len(edit_script.cuts)}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Required modules not found: {e}")
        print("   Make sure transcription.py and script_generation.py are implemented")
        return False
    except Exception as e:
        print(f"❌ Command line processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_version():
    """Show version information"""
    print("Smart Edit - AI Video Editor")
    print("Version: 1.0.0")
    print("Built with Python, OpenAI APIs, and FFmpeg")
    print("")
    print("Features:")
    print("• High-accuracy transcription with Whisper")
    print("• AI-powered content analysis with GPT-4")
    print("• Intelligent cut decisions and pacing")
    print("• Multi-camera angle assignment (coming soon)")
    print("• Premiere Pro XML export (coming soon)")

def show_examples():
    """Show usage examples"""
    print("Smart Edit Usage Examples:")
    print("")
    print("1. Launch GUI (if available):")
    print("   python run.py")
    print("   python run.py --gui")
    print("")
    print("2. Process single video:")
    print("   python run.py video.mp4")
    print("   python run.py video.mp4 --output results.txt")
    print("")
    print("3. Process with custom compression:")
    print("   python run.py video.mp4 --compression 0.8 --output output.txt")
    print("")
    print("4. Check system setup:")
    print("   python run.py --check-deps")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Smart Edit - AI Video Editor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                           # Launch GUI (if available)
  python run.py video.mp4                 # Process single video
  python run.py video.mp4 -o output.txt   # Save results to file
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
        '-o', '--output',
        help='Output file path (will be .txt for now, .xml when export module ready)'
    )
    
    parser.add_argument(
        '-c', '--compression',
        type=float,
        default=0.7,
        help='Target compression ratio (0.1-1.0, default: 0.7)'
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
    
    # Validate compression ratio
    if not 0.1 <= args.compression <= 1.0:
        print("❌ Compression ratio must be between 0.1 and 1.0")
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
            output_path = f"{video_stem}_edited_results.txt"
        
        # Validate output path
        if not validate_output_path(output_path):
            return 1
        
        # Process videos
        success = process_command_line(video_paths, output_path, args.compression)
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