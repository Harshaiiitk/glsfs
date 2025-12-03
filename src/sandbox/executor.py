# src/sandbox/executor.py
"""
GLSFS Sandbox Executor

Executes commands safely in Docker or locally with path translation.

PATH NORMALIZATION (Defense in Depth):
=====================================
Even if the model outputs incorrect paths, this executor normalizes them
right before execution as a safety net:
  - desktop -> /home/user/Desktop
  - Documents/ -> /home/user/Documents/
  - ~/Downloads -> /home/user/Downloads
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
        
        # Docker path normalization mapping (case-insensitive folder -> correct path)
        self.docker_folder_mapping = {
            'desktop': '/home/user/Desktop',
            'documents': '/home/user/Documents',
            'downloads': '/home/user/Downloads',
            'workspace': '/home/user/workspace',
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
    
    def _normalize_command_for_docker(self, command):
        """
        Normalize paths in command to correct Docker paths.
        
        This is a SAFETY NET - catches any paths the model didn't normalize:
          - desktop -> /home/user/Desktop
          - documents/ -> /home/user/Documents/
          - Documents -> /home/user/Documents
          - ~/Desktop -> /home/user/Desktop
        """
        if not command:
            return command
        
        result = command
        
        # Step 1: Handle ~ and $HOME
        result = result.replace('~/', '/home/user/')
        result = re.sub(r'~(?=\s|$)', '/home/user', result)
        result = result.replace('$HOME/', '/home/user/')
        result = result.replace('${HOME}/', '/home/user/')
        result = re.sub(r'\$HOME(?=\s|$)', '/home/user', result)
        result = re.sub(r'\$\{HOME\}(?=\s|$)', '/home/user', result)
        
        # Step 2: Normalize folder names (case-insensitive)
        # Process the command to find and replace folder references
        result = self._replace_folder_references(result)
        
        return result
    
    def _replace_folder_references(self, command):
        """
        Find and replace folder references in a command.
        
        Handles:
          - Bare names: desktop, Documents, DOWNLOADS
          - With trailing slash: desktop/, Documents/
          - With subpath: desktop/file.txt, Documents/subdir/
          - Already partially correct: /home/user/documents
        """
        # Pattern to match folder references
        # This regex finds word boundaries and matches folder names
        
        for folder_lower, correct_path in self.docker_folder_mapping.items():
            # Pattern 1: Already in /home/user/ but wrong case
            # /home/user/documents -> /home/user/Documents
            pattern = rf'/home/user/{folder_lower}(?=/|$|\s)'
            replacement = correct_path
            command = re.sub(pattern, replacement, command, flags=re.IGNORECASE)
            
            # Pattern 2: Bare folder name or folder/ at word boundary (not already with /home/user)
            # This handles: "ls desktop", "find documents/", "cat Desktop/file.txt"
            # But NOT: "/home/user/Desktop" (already handled above)
            
            # Match folder name at word boundary, not preceded by /user/
            # (?<!...) is negative lookbehind
            pattern = rf'(?<!/user/)(?<![/\w])({folder_lower})(/[^\s]*)?(?=\s|$|[|;&])'
            
            def replace_match(m):
                folder_match = m.group(1)
                path_suffix = m.group(2) or ''
                return correct_path + path_suffix
            
            command = re.sub(pattern, replace_match, command, flags=re.IGNORECASE)
        
        return command
    
    def execute(self, command, timeout=30):
        """
        Execute a command.
        
        Normalizes paths first, then executes in Docker or locally.
        """
        # CRITICAL: Normalize paths before execution
        normalized_command = self._normalize_command_for_docker(command)
        
        if normalized_command != command:
            print(f"   📍 Path normalized: {command}")
            print(f"   📍 Executing: {normalized_command}")
        
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
        """
        Translate Docker paths to Mac paths for local execution.
        
        /home/user/Desktop -> /Users/yourname/Desktop
        """
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