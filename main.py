#!/usr/bin/env python3
"""
GLSFS (Granite LLM Semantic File System) - Main Entry Point
Competitor to AIOS-LSFS
"""

import argparse
import sys
import os
import json

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.glsfs_system import LSFSCompetitor


def main():
    parser = argparse.ArgumentParser(
        description='GLSFS - Natural Language Filesystem Operations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (default) - accesses your real Mac folders
  python main.py
  
  # Specify custom model path
  python main.py --model-path ~/glsfs/models/granite/glsfs_granite_finetuned
  
  # Single query mode
  python main.py --query "Show all Python files on Desktop"
  
  # Without Docker (less safe - not recommended)
  python main.py --no-docker

Mounted Folders (read-only):
  - Desktop    -> Your Mac ~/Desktop
  - Documents  -> Your Mac ~/Documents  
  - Downloads  -> Your Mac ~/Downloads

Writable Folder:
  - workspace  -> ~/glsfs/data/workspace
        """
    )
    
    parser.add_argument(
        '--model-path',
        type=str,
        default=None,
        help='Path to fine-tuned Granite model (default: ~/glsfs/src/models/granite/glsfs_granite_finetuned)'
    )
    
    parser.add_argument(
        '--mode',
        choices=['interactive', 'web'],
        default='interactive',
        help='Run mode: interactive CLI or web interface'
    )
    
    parser.add_argument(
        '--no-docker',
        action='store_true',
        help='Run without Docker (LESS SAFE - not recommended)'
    )
    
    parser.add_argument(
        '--query',
        type=str,
        help='Single query to process (non-interactive mode)'
    )
    
    parser.add_argument(
        '--rebuild-container',
        action='store_true',
        help='Force rebuild of Docker container (useful after changing mounts)'
    )
    
    args = parser.parse_args()
    
    # Expand model path
    if args.model_path:
        args.model_path = os.path.expanduser(args.model_path)
    
    # Handle container rebuild request
    if args.rebuild_container:
        print("🔄 Removing existing container...")
        import subprocess
        subprocess.run(['docker', 'stop', 'glsfs-sandbox-exec'], 
                      capture_output=True)
        subprocess.run(['docker', 'rm', 'glsfs-sandbox-exec'], 
                      capture_output=True)
        print("✅ Container removed. It will be recreated on next run.")
    
    try:
        # Initialize system
        lsfs = LSFSCompetitor(
            model_path=args.model_path,
            use_docker=not args.no_docker
        )
        
        if args.query:
            # Process single query
            print("\n" + "=" * 60)
            print("Single Query Mode")
            print("=" * 60)
            result = lsfs.process_query(args.query, auto_execute=True)
            
            print("\n" + "=" * 60)
            print("Full Result (JSON):")
            print("=" * 60)
            print(json.dumps(result, indent=2, default=str))
            
        elif args.mode == 'web':
            # Launch web interface
            print("\n🌐 Launching web interface...")
            try:
                from app import demo
                demo.launch(share=False, server_port=7860)
            except ImportError as e:
                print(f"❌ Failed to import web interface: {e}")
                print("   Install Gradio with: pip install gradio")
                sys.exit(1)
        else:
            # Interactive mode (default)
            lsfs.interactive_mode()
            
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        print("\n   Make sure your model is at the expected path.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
