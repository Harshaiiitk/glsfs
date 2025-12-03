#!/usr/bin/env python3
"""
GLSFS (Granite LLM Semantic File System) - Main Entry Point
Competitor to AIOS-LSFS
"""

import argparse
import sys
import os
import json

# Add src to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.glsfs_system import LSFSCompetitor

def main():
    parser = argparse.ArgumentParser(
        description='GLSFS - Natural Language Filesystem Operations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode with Docker
  python main.py --model-path ~/glsfs/models/granite/glsfs_granite_finetuned
  
  # Single query
  python main.py --model-path ~/glsfs/models/granite/glsfs_granite_finetuned \\
                 --query "Show all Python files"
  
  # Without Docker (less safe)
  python main.py --model-path ~/glsfs/models/granite/glsfs_granite_finetuned \\
                 --no-docker
        """
    )
    
    parser.add_argument(
        '--model-path',
        type=str,
        default=None,
        help='Path to fine-tuned Granite model (default: ~/glsfs/models/granite/glsfs_granite_finetuned)'
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
    
    args = parser.parse_args()
    
    # Expand model path
    if args.model_path:
        args.model_path = os.path.expanduser(args.model_path)
    
    try:
        # Initialize system
        lsfs = LSFSCompetitor(
            model_path=args.model_path,
            use_docker=not args.no_docker
        )
        
        if args.query:
            # Process single query
            print("\n" + "="*60)
            print("Single Query Mode")
            print("="*60)
            result = lsfs.process_query(args.query, auto_execute=True)
            
            print("\n" + "="*60)
            print("Full Result (JSON):")
            print("="*60)
            print(json.dumps(result, indent=2))
            
        elif args.mode == 'web':
            # Launch web interface
            print("\n🌐 Launching web interface...")
            try:
                from app import demo
                demo.launch(share=False, server_port=7860)
            except ImportError:
                print("❌ Gradio not installed. Install with: pip install gradio")
                sys.exit(1)
        else:
            # Interactive mode (default)
            lsfs.interactive_mode()
            
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
