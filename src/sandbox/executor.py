# src/sandbox/executor.py
"""
GLSFS Sandbox Executor

SMART PATH HANDLING:
====================
The executor normalizes paths only when necessary:

CONVERTS (would fail otherwise):
  - "ls documents/"      → "ls /home/user/Documents/"    (case sensitivity)
  - "cat Desktop/f.txt"  → "cat /home/user/Desktop/f.txt" (relative path)
  - "~/Downloads"        → "/home/user/Downloads"         (tilde expansion)

LEAVES ALONE (already works):
  - "find . -name '*.pdf'"           (searches from /home/user)
  - "ls"                              (lists /home/user)
  - "find . -path '*/Documents/*'"   (pattern matching)
  - "du -sh *"                        (glob expansion)

Docker working directory is /home/user, which contains:
  - Desktop/    (mounted from ~/Desktop)
  - Documents/  (mounted from ~/Documents)
  - Downloads/  (mounted from ~/Downloads)
  - workspace/  (mounted from ~/glsfs/data/workspace)
"""

import docker
import subprocess
import os
import re
import time
from pathlib import Path
from datetime import datetime


class SandboxExecutor:
    def __init__(self, use_docker=True):
        """Initialize sandbox executor."""
        self.use_docker = use_docker
        self.container = None
        
        self.home = str(Path.home())
        
        # Workspace for write operations
        self.local_workspace = os.path.expanduser("~/glsfs/data/workspace")
        os.makedirs(self.local_workspace, exist_ok=True)
        
        # Mac folders to mount
        self.mac_folders = {
            'Desktop': os.path.join(self.home, 'Desktop'),
            'Documents': os.path.join(self.home, 'Documents'),
            'Downloads': os.path.join(self.home, 'Downloads'),
        }
        
        # Path mapping for local fallback (Docker path → Mac path)
        self.path_mapping = {
            '/home/user/Desktop': self.mac_folders['Desktop'],
            '/home/user/Documents': self.mac_folders['Documents'],
            '/home/user/Downloads': self.mac_folders['Downloads'],
            '/home/user/workspace': self.local_workspace,
            '/home/user': self.home,
        }
        
        # Canonical folder names (for case correction)
        self.canonical_folders = {
            'desktop': 'Desktop',
            'documents': 'Documents', 
            'downloads': 'Downloads',
            'workspace': 'workspace',
        }
        
        # Verify Mac folders
        self.available_mounts = {}
        for name, path in self.mac_folders.items():
            if os.path.exists(path) and os.path.isdir(path):
                self.available_mounts[name] = path
                print(f"   ✅ Found: {path}")
            else:
                print(f"   ⚠️  Not found: {path}")
        
        if use_docker:
            self._setup_docker()
        
        print(f"\n📁 Workspace (read-write): {self.local_workspace}")
        print(f"📁 Mac folders mounted (read-only): {list(self.available_mounts.keys())}")
        if self.use_docker:
            print(f"🐳 Execution mode: Docker (isolated)")
        else:
            print(f"⚠️  Execution mode: Local (less safe)")
    
    def _setup_docker(self):
        """Set up Docker client and container"""
        try:
            self.client = docker.from_env()
            self.container_name = "glsfs-sandbox-exec"
            self._ensure_container()
        except docker.errors.DockerException as e:
            print(f"⚠️  Docker initialization failed: {e}")
            print("⚠️  Falling back to local execution (less safe)")
            self.use_docker = False
        except Exception as e:
            print(f"⚠️  Unexpected error: {e}")
            print("⚠️  Falling back to local execution (less safe)")
            self.use_docker = False
    
    def _cleanup_old_container(self):
        """Remove any existing container"""
        try:
            old_container = self.client.containers.get(self.container_name)
            print(f"🧹 Removing old container...")
            try:
                old_container.stop(timeout=2)
            except:
                pass
            old_container.remove(force=True)
        except docker.errors.NotFound:
            pass
        except Exception:
            subprocess.run(['docker', 'rm', '-f', self.container_name], 
                         capture_output=True, timeout=10)
    
    def _ensure_container(self):
        """Ensure sandbox container is running"""
        self._cleanup_old_container()
        
        print(f"📦 Creating new container with mounts...")
        
        volumes = {
            self.local_workspace: {
                'bind': '/home/user/workspace',
                'mode': 'rw'
            }
        }
        
        for folder_name, mac_path in self.available_mounts.items():
            docker_path = f'/home/user/{folder_name}'
            volumes[mac_path] = {
                'bind': docker_path,
                'mode': 'ro'
            }
            print(f"   📂 {mac_path} -> {docker_path} (ro)")
        
        print(f"   📂 {self.local_workspace} -> /home/user/workspace (rw)")
        
        try:
            self.client.images.get("glsfs-sandbox")
            
            self.container = self.client.containers.run(
                "glsfs-sandbox",
                name=self.container_name,
                detach=True,
                tty=True,
                stdin_open=True,
                volumes=volumes,
                working_dir='/home/user',
                mem_limit='512m',
                cpu_quota=50000,
                command="tail -f /dev/null",
            )
            
            time.sleep(1)
            self.container.reload()
            
            if self.container.status != 'running':
                raise Exception(f"Container status: {self.container.status}")
            
            print(f"✅ Container created and started: {self.container_name}")
            self._test_mounts()
            
        except docker.errors.ImageNotFound:
            print(f"\n❌ Docker image 'glsfs-sandbox' not found!")
            print(f"   Build it first with:")
            print(f"   cd ~/glsfs/data && docker build --platform linux/amd64 -t glsfs-sandbox .")
            raise
        except Exception as e:
            print(f"❌ Error creating container: {e}")
            raise
    
    def _test_mounts(self):
        """Verify mounts are working"""
        print("\n🔍 Testing mounts...")
        
        for name in ['workspace', 'Desktop', 'Documents', 'Downloads']:
            path = f'/home/user/{name}'
            result = self.container.exec_run(['ls', path], stderr=True)
            if result.exit_code == 0:
                print(f"   ✅ {name} mount OK")
            else:
                print(f"   ⚠️  {name} mount issue")
    
    def _smart_normalize_command(self, command):
        """
        Smart path normalization - only fix what needs fixing.
        
        FIXES:
          1. Tilde expansion: ~/Documents → /home/user/Documents
          2. $HOME expansion: $HOME/Desktop → /home/user/Desktop
          3. Case correction: documents/ → Documents/
          4. Bare folder access: ls documents → ls Documents
          
        LEAVES ALONE:
          - find . (works fine from /home/user)
          - Glob patterns like *
          - Already correct paths
        """
        if not command:
            return command
        
        result = command
        
        # 1. Expand ~ to /home/user (tilde doesn't work in Docker)
        result = result.replace('~/', '/home/user/')
        result = re.sub(r'~(?=\s|$)', '/home/user', result)
        
        # 2. Expand $HOME
        result = result.replace('$HOME/', '/home/user/')
        result = result.replace('${HOME}/', '/home/user/')
        result = re.sub(r'\$HOME(?=\s|$)', '/home/user', result)
        result = re.sub(r'\$\{HOME\}(?=\s|$)', '/home/user', result)
        
        # 3. Fix case sensitivity for folder names
        # Linux is case-sensitive, so "documents" won't find "Documents"
        result = self._fix_folder_case(result)
        
        return result
    
    def _fix_folder_case(self, command):
        """
        Fix case sensitivity issues for folder names.
        
        Converts:
          - documents → Documents
          - desktop → Desktop  
          - downloads → Downloads
          
        But only when it's clearly a path reference, not part of a pattern.
        """
        result = command
        
        for wrong_case, correct_case in self.canonical_folders.items():
            if wrong_case == correct_case.lower():
                # Skip if already correct case
                if wrong_case == correct_case:
                    continue
                
                # Pattern 1: In /home/user/documents → /home/user/Documents
                pattern = rf'(/home/user/){wrong_case}(?=/|$|\s)'
                result = re.sub(pattern, rf'\1{correct_case}', result, flags=re.IGNORECASE)
                
                # Pattern 2: Bare folder or folder/ at start of a path argument
                # Match: "ls documents" or "ls documents/" or "cat documents/file.txt"
                # Don't match: "find . -path '*/Documents/*'" (pattern in quotes - already works)
                
                # This regex finds folder names that are command arguments (after space, not in quotes)
                # We only fix obvious cases where the folder is a direct argument
                
                # Case: "ls documents" or "cat documents/file.txt"
                # But NOT: "'*/documents/*'" (inside quotes for pattern matching)
                pattern = rf"(?<=['\"*/]){wrong_case}(?=['\"*/])"  # Inside quotes/patterns - skip
                
                # Fix bare folder references that aren't in quotes
                # This handles: ls documents, cat desktop/file.txt
                tokens = self._tokenize_preserving_quotes(result)
                fixed_tokens = []
                
                for token in tokens:
                    # Skip if token is quoted (pattern matching)
                    if token.startswith("'") or token.startswith('"'):
                        fixed_tokens.append(token)
                        continue
                    
                    # Fix case for this specific folder
                    if token.lower() == wrong_case:
                        fixed_tokens.append(correct_case)
                    elif token.lower().startswith(wrong_case + '/'):
                        fixed_tokens.append(correct_case + token[len(wrong_case):])
                    else:
                        fixed_tokens.append(token)
                
                result = ' '.join(fixed_tokens)
        
        return result
    
    def _tokenize_preserving_quotes(self, command):
        """Split command into tokens, keeping quoted strings together."""
        tokens = []
        current = ""
        in_quote = None
        
        for char in command:
            if char in '"\'':
                if in_quote == char:
                    current += char
                    in_quote = None
                elif in_quote is None:
                    in_quote = char
                    current += char
                else:
                    current += char
            elif char == ' ' and in_quote is None:
                if current:
                    tokens.append(current)
                    current = ""
            else:
                current += char
        
        if current:
            tokens.append(current)
        
        return tokens
    
    def execute(self, command, timeout=30):
        """
        Execute a command with smart path normalization.
        """
        # Smart normalize - only fix what needs fixing
        normalized_command = self._smart_normalize_command(command)
        
        if normalized_command != command:
            print(f"   📍 Normalized: {command}")
            print(f"   📍 To: {normalized_command}")
        
        if self.use_docker:
            return self._execute_docker(normalized_command, timeout)
        else:
            return self._execute_local(normalized_command, timeout)
    
    def _execute_docker(self, command, timeout):
        """Execute command inside Docker container"""
        try:
            print(f"🐳 Executing in Docker: {command}")
            
            if self.container:
                self.container.reload()
                if self.container.status != 'running':
                    self.container.start()
                    time.sleep(0.5)
            
            exec_result = self.container.exec_run(
                cmd=['bash', '-c', command],
                stderr=True,
                stdout=True,
                workdir='/home/user',
                demux=True,
            )
            
            stdout_bytes, stderr_bytes = exec_result.output
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ''
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ''
            
            if exec_result.exit_code != 0 and stderr:
                print(f"   ⚠️  Exit code: {exec_result.exit_code}")
            
            return {
                'status': 'success' if exec_result.exit_code == 0 else 'error',
                'exit_code': exec_result.exit_code,
                'stdout': stdout,
                'stderr': stderr,
                'command': command,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'docker'
            }
            
        except Exception as e:
            print(f"   ❌ Docker error: {e}, falling back to local")
            return self._execute_local(command, timeout)
    
    def _translate_path_for_local(self, command):
        """Translate Docker paths to Mac paths for local execution."""
        result = command
        
        sorted_mappings = sorted(
            self.path_mapping.items(), 
            key=lambda x: len(x[0]), 
            reverse=True
        )
        
        for docker_path, mac_path in sorted_mappings:
            if mac_path:
                result = result.replace(docker_path, mac_path)
        
        return result
    
    def _execute_local(self, command, timeout):
        """Execute locally with path translation (fallback mode)"""
        translated = self._translate_path_for_local(command)
        
        print(f"⚠️  Executing locally: {translated}")
        
        try:
            result = subprocess.run(
                translated,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.home,
                env={**os.environ, 'HOME': self.home}
            )
            
            return {
                'status': 'success' if result.returncode == 0 else 'error',
                'exit_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': translated,
                'original_command': command,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'local'
            }
            
        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'exit_code': -1,
                'stdout': '',
                'stderr': f'Timed out after {timeout}s',
                'command': translated,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'local'
            }
        except Exception as e:
            return {
                'status': 'error',
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e),
                'command': translated,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'local'
            }
    
    def get_workspace_contents(self):
        """Show contents of all accessible directories"""
        if self.use_docker:
            cmd = """
echo '=== Home Directory ===' && ls -la /home/user/
echo ''
echo '=== Workspace (read-write) ===' && ls -la /home/user/workspace 2>/dev/null | head -15
echo ''
echo '=== Desktop (read-only) ===' && ls -la /home/user/Desktop 2>/dev/null | head -15
echo ''
echo '=== Documents (read-only) ===' && ls -la /home/user/Documents 2>/dev/null | head -15
echo ''
echo '=== Downloads (read-only) ===' && ls -la /home/user/Downloads 2>/dev/null | head -15
"""
            result = self.execute(cmd)
            return result['stdout'] if result['status'] == 'success' else result['stderr']
        else:
            lines = ["=== Local Mode - Mac Paths ===\n"]
            for name, path in [
                ("Workspace", self.local_workspace),
                ("Desktop", self.mac_folders['Desktop']),
                ("Documents", self.mac_folders['Documents']),
                ("Downloads", self.mac_folders['Downloads']),
            ]:
                lines.append(f"\n=== {name}: {path} ===")
                try:
                    out = subprocess.run(
                        f'ls -la "{path}" | head -10',
                        shell=True, capture_output=True, text=True, timeout=5
                    )
                    lines.append(out.stdout)
                except:
                    lines.append("(error reading)")
            return '\n'.join(lines)
    
    def cleanup(self):
        """Stop and remove container"""
        if self.use_docker and self.container:
            try:
                print("🧹 Cleaning up container...")
                self.container.stop(timeout=2)
                self.container.remove()
                print("✅ Container removed")
            except:
                pass