# src/sandbox/executor.py

import docker
import subprocess
import os
import json
import shlex

from datetime import datetime

class SandboxExecutor:
    def __init__(self, use_docker=True):
        """Initialize sandbox executor"""
        self.use_docker = use_docker
        
        # IMPORTANT: Initialize local_workspace FIRST (before Docker setup)
        self.local_workspace = os.path.expanduser("~/glsfs/data/workspace")
        os.makedirs(self.local_workspace, exist_ok=True)
        
        if use_docker:
            try:
                self.client = docker.from_env()
                self.container_name = "glsfs-sandbox-exec"
                self._ensure_container()
            except Exception as e:
                print(f"⚠️  Docker initialization failed: {e}")
                print("⚠️  Falling back to local execution (less safe)")
                self.use_docker = False
        
        print(f"📁 Local workspace: {self.local_workspace}")
    
    def _ensure_container(self):
        """Ensure sandbox container is running"""
        try:
            # Try to get existing container
            self.container = self.client.containers.get(self.container_name)
            print(f"✅ Found existing container: {self.container_name}")
            
            if self.container.status != 'running':
                print(f"🔄 Starting container...")
                self.container.start()
                print(f"✅ Container started")
            else:
                print(f"✅ Container already running")
                
        except docker.errors.NotFound:
            # Container doesn't exist, create new one
            print(f"📦 Creating new container from image 'glsfs-sandbox'...")
            
            try:
                self.container = self.client.containers.run(
                    "glsfs-sandbox",
                    name=self.container_name,
                    detach=True,
                    tty=True,
                    volumes={
                        self.local_workspace: {
                            'bind': '/workspace',
                            'mode': 'rw'
                        }
                    },
                    working_dir='/home/user',
                    mem_limit='512m',
                    cpu_quota=50000,
                    command="/bin/bash"
                )
                print(f"✅ Container created and started: {self.container_name}")
                
            except docker.errors.ImageNotFound:
                print(f"❌ ERROR: Docker image 'glsfs-sandbox' not found!")
                print(f"   Please build it first: docker build -t glsfs-sandbox .")
                raise
            except Exception as e:
                print(f"❌ ERROR creating container: {e}")
                raise
    
    def execute(self, command, timeout=30):
        """Execute command in sandbox"""
        if self.use_docker:
            return self._execute_docker(command, timeout)
        else:
            return self._execute_local(command, timeout)
    
    def _execute_docker(self, command, timeout):
        """Execute command inside Docker container with detailed error reporting"""
        try:
            print(f"🐳 Executing in Docker: {command}")
            
            # Execute with demux=True to separate stdout and stderr
            exec_result = self.container.exec_run(
                cmd=['bash', '-c', command],
                stderr=True,
                stdout=True,
                workdir='/home/user',
                user='root',
                demux=True  # ← Separate stdout and stderr
            )
            
            # Unpack stdout and stderr
            stdout, stderr = exec_result.output
            stdout = stdout.decode('utf-8', errors='replace') if stdout else ''
            stderr = stderr.decode('utf-8', errors='replace') if stderr else ''
            
            # Debug output
            if exec_result.exit_code != 0:
                print(f"   ⚠️  Exit code: {exec_result.exit_code}")
                if stdout:
                    print(f"   📤 stdout: {stdout}")
                if stderr:
                    print(f"   ❌ stderr: {stderr}")
            
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
            print(f"   ❌ Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'error',
                'exit_code': -1,
                'stdout': '',
                'stderr': f"Docker execution error: {str(e)}",
                'command': command,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'docker'
            }
    
    def _execute_local(self, command, timeout):
        """Execute locally with restrictions (FALLBACK - less safe)"""
        try:
            print(f"⚠️  Executing locally (not in Docker): {command}")
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.local_workspace,
                env={
                    'PATH': '/usr/bin:/bin:/usr/local/bin',
                    'HOME': self.local_workspace,
                    'USER': 'safeuser'
                }
            )
            
            return {
                'status': 'success' if result.returncode == 0 else 'error',
                'exit_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': command,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'local'
            }
            
        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'exit_code': -1,
                'stdout': '',
                'stderr': f'Command timed out after {timeout} seconds',
                'command': command,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'local'
            }
        except Exception as e:
            return {
                'status': 'error',
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e),
                'command': command,
                'timestamp': datetime.now().isoformat(),
                'execution_method': 'local'
            }
    
    def get_workspace_contents(self):
        """List files in workspace"""
        if self.use_docker:
            result = self.execute("ls -la /workspace")
            return result['stdout']
        else:
            try:
                return subprocess.run(
                    ['ls', '-la', self.local_workspace],
                    capture_output=True,
                    text=True
                ).stdout
            except Exception as e:
                return f"Error: {e}"
    
    def cleanup(self):
        """Stop and remove container"""
        if self.use_docker and hasattr(self, 'container'):
            try:
                print(f"🧹 Cleaning up container...")
                self.container.stop()
                self.container.remove()
                print(f"✅ Container removed")
            except Exception as e:
                print(f"⚠️  Cleanup error: {e}")
