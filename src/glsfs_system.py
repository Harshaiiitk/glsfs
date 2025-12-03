# src/glsfs_system.py
"""
GLSFS Main System - Optimized for Speed

Includes warmup call to pre-initialize model caches for faster inference.
"""

import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.granite_loader import GraniteCommandGenerator
from src.safety.validator import CommandSafetyValidator
from src.sandbox.executor import SandboxExecutor


class LSFSCompetitor:
    def __init__(self, model_path=None, use_docker=True, warmup=True):
        """
        Initialize LSFS competitor system.
        
        Args:
            model_path: Path to fine-tuned Granite model
            use_docker: Whether to use Docker sandbox
            warmup: Run warmup inference for faster subsequent calls
        """
        print("=" * 60)
        print("Initializing GLSFS (Granite LLM Semantic File System)...")
        print("=" * 60)
        
        if model_path is None:
            model_path = os.path.expanduser("~/glsfs/models/granite/glsfs_granite_finetuned")
        
        print(f"\n📦 Model path: {model_path}")
        print(f"🐳 Docker mode: {'Enabled' if use_docker else 'Disabled'}")
        
        try:
            print("\n1️⃣  Loading Granite model...")
            load_start = time.time()
            self.command_generator = GraniteCommandGenerator(model_path)
            load_time = time.time() - load_start
            print(f"   Model loaded in {load_time:.1f}s")
            
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
        
        # Warmup for faster inference
        if warmup:
            print("\n4️⃣  Warming up model (for faster responses)...")
            self._warmup()
        
        print("\n" + "=" * 60)
        print("✅ System initialized successfully!")
        print("=" * 60 + "\n")
    
    def _warmup(self):
        """Run warmup inference to pre-initialize caches."""
        try:
            start = time.time()
            # Simple query to warm up the model
            _ = self.command_generator.generate_command("list files")
            warmup_time = time.time() - start
            print(f"   ✅ Warmup complete ({warmup_time:.2f}s)")
            print(f"   📈 Subsequent queries will be faster!")
        except Exception as e:
            print(f"   ⚠️  Warmup failed: {e} (not critical)")
    
    def process_query(self, natural_language_query, auto_execute=True):
        """
        Main pipeline: Query -> Command -> Validate -> Execute
        """
        total_start = time.time()
        
        response = {
            'query': natural_language_query,
            'timestamp': datetime.now().isoformat(),
            'steps': []
        }
        
        print(f"\n{'=' * 60}")
        print(f"🤖 Query: '{natural_language_query}'")
        print(f"{'=' * 60}")
        
        # Step 1: Generate command
        try:
            gen_start = time.time()
            command_result = self.command_generator.generate_command(natural_language_query)
            gen_time = time.time() - gen_start
            
            command = command_result['command']
            explanation = command_result.get('explanation', '')
            
            response['generated_command'] = command
            response['explanation'] = explanation
            response['generation_time'] = gen_time
            response['steps'].append({
                'step': 'command_generation',
                'result': command,
                'time': gen_time
            })
            
            print(f"\n📝 Generated command ({gen_time:.2f}s):")
            print(f"   {command}")
            if explanation:
                exp_preview = explanation[:150] + "..." if len(explanation) > 150 else explanation
                print(f"\n💡 Explanation: {exp_preview}")
                
        except Exception as e:
            response['status'] = 'generation_error'
            response['error'] = str(e)
            print(f"\n❌ Command generation failed: {e}")
            self._log_operation(response)
            return response
        
        # Step 2: Validate safety
        print(f"\n🔒 Validating safety...")
        val_start = time.time()
        is_safe, warnings, sanitized_command = self.validator.validate(command)
        val_time = time.time() - val_start
        
        response['safety_check'] = {
            'is_safe': is_safe,
            'warnings': warnings,
            'sanitized_command': sanitized_command,
            'time': val_time
        }
        
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
            print(f"   ✅ Command is safe ({val_time*1000:.1f}ms)")
        
        final_command = sanitized_command if sanitized_command else command
        response['final_command'] = final_command
        
        # Step 3: Execute
        print(f"\n🚀 Executing...")
        exec_start = time.time()
        
        try:
            execution_result = self.executor.execute(final_command, timeout=30)
            exec_time = time.time() - exec_start
            
            response['execution'] = execution_result
            response['execution_time'] = exec_time
            
            if execution_result['status'] == 'success':
                print(f"\n✅ Execution successful ({exec_time:.2f}s)!")
                if execution_result['stdout']:
                    stdout = execution_result['stdout']
                    lines = stdout.split('\n')
                    if len(lines) > 30:
                        stdout = '\n'.join(lines[:30]) + f"\n... ({len(lines) - 30} more lines)"
                    print(f"\n📤 Output:\n{stdout}")
                else:
                    print(f"\n📤 (No output)")
            else:
                print(f"\n❌ Execution failed ({exec_time:.2f}s)!")
                if execution_result['stderr']:
                    print(f"\n📤 Error:\n{execution_result['stderr']}")
                    
        except Exception as e:
            exec_time = time.time() - exec_start
            response['execution'] = {
                'status': 'error',
                'error': str(e)
            }
            print(f"\n❌ Execution error: {e}")
        
        # Total time
        total_time = time.time() - total_start
        response['status'] = 'completed'
        response['total_time'] = total_time
        
        print(f"\n⏱️  Total time: {total_time:.2f}s")
        
        self._log_operation(response)
        return response
    
    def _log_operation(self, response):
        """Log operation for audit trail."""
        try:
            logs = []
            if os.path.exists(self.log_file):
                try:
                    with open(self.log_file, 'r') as f:
                        logs = json.load(f)
                except:
                    logs = []
            
            logs.append(response)
            
            # Keep only last 500 entries
            if len(logs) > 500:
                logs = logs[-500:]
            
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2, default=str)
                
        except Exception as e:
            print(f"⚠️  Logging error: {e}")
    
    def interactive_mode(self):
        """Run in interactive mode."""
        print("\n" + "=" * 60)
        print("GLSFS - Interactive Mode (Optimized)")
        print("=" * 60)
        print("\n📁 Accessible Directories:")
        print("   • Desktop    (read-only)  - Your Mac Desktop")
        print("   • Documents  (read-only)  - Your Mac Documents")
        print("   • Downloads  (read-only)  - Your Mac Downloads")
        print("   • workspace  (read-write) - For creating files")
        print("\n💬 Commands:")
        print("   • Type your question in natural language")
        print("   • 'help'      - Show examples")
        print("   • 'workspace' - Show all accessible files")
        print("   • 'exit'      - Quit")
        print("=" * 60 + "\n")
        
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
                    print("\n📁 Accessible files:")
                    print(self.executor.get_workspace_contents())
                    
                else:
                    self.process_query(query, auto_execute=True)
                    
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted! Type 'exit' to quit.\n")
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    def _show_help(self):
        """Show help information."""
        help_text = """
╔══════════════════════════════════════════════════════════════╗
║                    GLSFS - Quick Examples                    ║
╚══════════════════════════════════════════════════════════════╝

📝 EXAMPLE QUERIES:

  List Files:
    • "list files on Desktop"
    • "show what's in Documents"
    
  Search:
    • "find all PDF files"
    • "find files named report"
    
  File Info:
    • "show disk usage"
    • "count files in Downloads"

⚡ PERFORMANCE:
  • First query: ~3-8 seconds (model warmup)
  • Subsequent queries: ~2-5 seconds
        """
        print(help_text)
    
    def __del__(self):
        """Cleanup when system shuts down."""
        if hasattr(self, 'executor'):
            try:
                self.executor.cleanup()
            except:
                pass