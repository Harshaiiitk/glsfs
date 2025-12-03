# src/lsfs_system.py

import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.granite_loader import GraniteCommandGenerator
from src.safety.validator import CommandSafetyValidator
from src.sandbox.executor import SandboxExecutor

class LSFSCompetitor:
    def __init__(self, model_path=None, use_docker=True):
        """
        Initialize LSFS competitor system
        
        Args:
            model_path: Path to fine-tuned Granite model
                       If None, uses default: ~/glsfs/models/granite/glsfs_granite_finetuned
            use_docker: Whether to use Docker sandbox (recommended)
        """
        print("="*60)
        print("Initializing GLSFS (Granite LLM Semantic File System)...")
        print("="*60)
        
        # Set default model path if not provided
        if model_path is None:
            model_path = os.path.expanduser("~/glsfs/models/granite/glsfs_granite_finetuned")
        
        print(f"\n📦 Model path: {model_path}")
        print(f"🐳 Docker mode: {'Enabled' if use_docker else 'Disabled'}")
        
        # Initialize components
        try:
            print("\n1️⃣  Loading Granite model...")
            self.command_generator = GraniteCommandGenerator(model_path)
            
            print("2️⃣  Initializing safety validator...")
            self.validator = CommandSafetyValidator()
            
            print("3️⃣  Setting up sandbox executor...")
            self.executor = SandboxExecutor(use_docker=use_docker)
            
        except Exception as e:
            print(f"\n❌ Initialization failed: {e}")
            raise
        
        # Logging setup
        log_dir = os.path.expanduser("~/glsfs/logs")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "lsfs_operations.json")
        
        print(f"\n📝 Logging to: {self.log_file}")
        print("\n" + "="*60)
        print("✅ System initialized successfully!")
        print("="*60 + "\n")
    
    def process_query(self, natural_language_query, auto_execute=True):
        """
        Main pipeline: Query -> Command -> Validate -> Execute
        
        Args:
            natural_language_query: User's question in plain English
            auto_execute: If False, ask for confirmation before executing
            
        Returns:
            dict with full pipeline results
        """
        response = {
            'query': natural_language_query,
            'timestamp': datetime.now().isoformat(),
            'steps': []
        }
        
        # Step 1: Generate command using Granite model
        print(f"\n{'='*60}")
        print(f"🤖 Query: '{natural_language_query}'")
        print(f"{'='*60}")
        
        try:
            command_result = self.command_generator.generate_command(natural_language_query)
            command = command_result['command']
            explanation = command_result.get('explanation', '')
            
            response['generated_command'] = command
            response['explanation'] = explanation
            response['steps'].append({
                'step': 'command_generation',
                'result': command,
                'explanation': explanation
            })
            
            print(f"\n📝 Generated command:")
            print(f"   {command}")
            if explanation:
                print(f"\n💡 Explanation:")
                print(f"   {explanation[:200]}...")  # First 200 chars
                
        except Exception as e:
            response['status'] = 'generation_error'
            response['error'] = str(e)
            print(f"\n❌ Command generation failed: {e}")
            self._log_operation(response)
            return response
        
        # Step 2: Validate safety
        print(f"\n🔒 Validating safety...")
        is_safe, warnings, sanitized_command = self.validator.validate(command)
        
        response['safety_check'] = {
            'is_safe': is_safe,
            'warnings': warnings,
            'sanitized_command': sanitized_command
        }
        response['steps'].append({
            'step': 'safety_validation',
            'is_safe': is_safe,
            'warnings': warnings
        })
        
        if not is_safe:
            response['status'] = 'blocked'
            response['warnings'] = warnings
            print(f"\n⛔ Command BLOCKED for safety:")
            for warning in warnings:
                print(f"   {warning}")
            self._log_operation(response)
            return response
        
        if warnings:
            print(f"\n⚠️  Safety warnings:")
            for warning in warnings:
                print(f"   {warning}")
            
            if not auto_execute:
                confirm = input("\n⚠️  Proceed anyway? (yes/no): ").strip().lower()
                if confirm not in ['yes', 'y']:
                    response['status'] = 'cancelled_by_user'
                    print("\n🚫 Execution cancelled by user")
                    self._log_operation(response)
                    return response
        else:
            print(f"   ✅ Command is safe")
        
        # Use sanitized command if available
        final_command = sanitized_command if sanitized_command else command
        response['final_command'] = final_command
        
        # Step 3: Execute in sandbox
        if auto_execute or warnings:
            print(f"\n🚀 Executing in sandbox...")
            print(f"   Command: {final_command}")
            
            try:
                execution_result = self.executor.execute(final_command, timeout=30)
                response['execution'] = execution_result
                response['steps'].append({
                    'step': 'execution',
                    'result': execution_result
                })
                
                if execution_result['status'] == 'success':
                    print(f"\n✅ Execution successful!")
                    if execution_result['stdout']:
                        print(f"\n📤 Output:")
                        print(f"{execution_result['stdout']}")
                else:
                    print(f"\n❌ Execution failed!")
                    if execution_result['stderr']:
                        print(f"\n📤 Error:")
                        print(f"{execution_result['stderr']}")
                        
            except Exception as e:
                response['execution'] = {
                    'status': 'error',
                    'error': str(e)
                }
                print(f"\n❌ Execution error: {e}")
        
        response['status'] = 'completed'
        self._log_operation(response)
        return response
    
    def _log_operation(self, response):
        """Log operation for audit trail and model improvement"""
        try:
            # Load existing logs
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    try:
                        logs = json.load(f)
                    except json.JSONDecodeError:
                        logs = []
            else:
                logs = []
            
            # Append new log
            logs.append(response)
            
            # Save logs
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            print(f"⚠️  Logging error: {e}")
    
    def interactive_mode(self):
        """Run in interactive mode"""
        print("\n" + "="*60)
        print("GLSFS - Interactive Mode")
        print("="*60)
        print("Commands:")
        print("  - Type your question in natural language")
        print("  - 'help' - Show help")
        print("  - 'workspace' - Show workspace contents")
        print("  - 'exit' - Quit")
        print("="*60 + "\n")
        
        while True:
            try:
                query = input("\n💬 Your query: ").strip()
                
                if not query:
                    continue
                    
                if query.lower() == 'exit':
                    print("\n👋 Goodbye!")
                    break
                    
                elif query.lower() == 'help':
                    self._show_help()
                    
                elif query.lower() == 'workspace':
                    print("\n📁 Workspace contents:")
                    print(self.executor.get_workspace_contents())
                    
                else:
                    self.process_query(query, auto_execute=True)
                    
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted! Type 'exit' to quit.\n")
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    def _show_help(self):
        """Show help information"""
        help_text = """

📝 EXAMPLE QUERIES:

  Basic Operations:
    • "What files are on my desktop?"
    • "Show all Python files"
    • "List files in my documents folder"
    
  Search Operations:
    • "Find files modified in the last week"
    • "Show me files larger than 10MB"
    • "Find all text files containing 'TODO'"
    
  File Management:
    • "Create a folder called projects"
    • "Copy all images to backup folder"
    • "Show the 10 largest files"
    
  Advanced:
    • "Find Python files modified today"
    • "Show disk usage of each folder"
    • "Count how many log files I have"

⚠️  SAFETY:
  - All commands execute in isolated Docker container
  - Dangerous operations are blocked automatically
  - Destructive operations require confirmation

📁 WORKSPACE:
  - Files in ~/glsfs/data/workspace sync with Docker
  - Commands run in /home/user inside Docker
  - Use 'workspace' command to see contents
        """
        print(help_text)
    
    def __del__(self):
        """Cleanup when system shuts down"""
        if hasattr(self, 'executor'):
            self.executor.cleanup()
