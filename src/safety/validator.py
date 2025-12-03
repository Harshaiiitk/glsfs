# src/safety/validator.py

import re
import os


class CommandSafetyValidator:
    def __init__(self, sandbox_root="/home/user"):
        """Initialize safety validator"""
        self.sandbox_root = sandbox_root
        
        # Dangerous commands that should NEVER be executed
        self.forbidden_patterns = [
            r'rm\s+-rf\s+/\s*$',           # rm -rf /
            r'rm\s+-rf\s+/\s+',             # rm -rf / something
            r'rm\s+-rf\s+~\s*$',            # rm -rf ~
            r'rm\s+-rf\s+/home/user\s*$',   # rm -rf /home/user (entire home)
            r':\(\)\{:\|:&\};:',            # Fork bomb
            r'dd\s+if=/dev/(zero|random)\s+of=/dev/sd',  # Disk wipe
            r'mkfs\.',                       # Format filesystem
            r'>\s*/dev/sd[a-z]',            # Write to disk device
            r'chmod\s+-R\s+777\s+/',        # Recursive chmod on root
            r'chown\s+-R.*\s+/',            # Recursive chown on root
            r'/dev/sd[a-z]',                # Direct disk access
            r'curl.*\|\s*bash',             # Download and execute
            r'wget.*\|\s*sh',               # Download and execute
            r'>\s*/etc/',                   # Write to /etc
            r'rm\s+-rf\s+/etc',             # Delete /etc
            r'rm\s+-rf\s+/usr',             # Delete /usr
            r'rm\s+-rf\s+/var',             # Delete /var
        ]
        
        # Commands that modify files (need extra checks)
        self.write_commands = ['rm', 'mv', 'cp', 'chmod', 'chown', 'touch', 'mkdir', 
                               'rmdir', 'ln', 'truncate', 'shred']
        
        # Read-only commands (always safe for mounted folders)
        self.readonly_commands = [
            'ls', 'cat', 'head', 'tail', 'less', 'more', 'find', 'grep', 'egrep', 'fgrep',
            'wc', 'file', 'stat', 'du', 'df', 'tree', 'pwd', 'echo', 'printf',
            'sort', 'uniq', 'cut', 'awk', 'sed', 'diff', 'comm', 'cmp',
            'basename', 'dirname', 'realpath', 'readlink', 'md5sum', 'sha256sum',
            'strings', 'od', 'hexdump', 'xxd', 'nl', 'tac', 'rev', 'column',
            'date', 'cal', 'env', 'printenv', 'id', 'whoami', 'hostname',
            'true', 'false', 'test', '[', 'expr'
        ]
        
        # Safe directories within the sandbox
        self.safe_paths = [
            '/home/user',
            '/home/user/Desktop',
            '/home/user/Documents',
            '/home/user/Downloads',
            '/home/user/workspace',
            '/workspace',  # Alternative mount point
            '/tmp'
        ]
        
        # Read-only mounted paths (Mac folders)
        self.readonly_mounts = [
            '/home/user/Desktop',
            '/home/user/Documents',
            '/home/user/Downloads',
        ]
        
        # Writable paths
        self.writable_paths = [
            '/home/user/workspace',
            '/workspace',
            '/tmp'
        ]
        
    def validate(self, command):
        """
        Validate if command is safe to execute.
        
        Returns:
            tuple: (is_safe, warnings, sanitized_command)
        """
        warnings = []
        
        if not command or not command.strip():
            return False, ["❌ Empty command"], None
        
        command = command.strip()
        
        # Step 1: Check for forbidden patterns (highest priority)
        for pattern in self.forbidden_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, [f"❌ FORBIDDEN: Dangerous operation detected"], None
        
        # Step 2: Sanitize paths (expand ~, $HOME, etc.)
        sanitized_command = self._sanitize_paths(command)
        
        # Step 3: Determine if this is a read-only or write command
        base_command = self._get_base_command(sanitized_command)
        is_readonly = base_command in self.readonly_commands
        is_write_cmd = base_command in self.write_commands
        
        # Step 4: For write commands, check if target is writable
        if is_write_cmd:
            target_paths = self._extract_target_paths(sanitized_command, base_command)
            
            for target in target_paths:
                # Check if target is in a read-only mount
                if self._is_readonly_path(target):
                    return False, [f"❌ BLOCKED: Cannot write to read-only path: {target}"], None
                
                # Check if target is outside sandbox
                if not self._is_in_sandbox(target):
                    return False, [f"❌ BLOCKED: Path outside sandbox: {target}"], None
            
            # Add warning for destructive commands
            if base_command in ['rm', 'rmdir', 'shred', 'truncate']:
                warnings.append(f"⚠️  Destructive command: {base_command}")
        
        # Step 5: Check for command injection
        injection_detected, injection_warnings = self._detect_injection(sanitized_command)
        if injection_detected:
            return False, [f"❌ Security risk: Command injection detected"], None
        warnings.extend(injection_warnings)
        
        # Step 6: Validate all paths in command are accessible
        path_check_passed, path_error = self._validate_all_paths(sanitized_command)
        if not path_check_passed:
            return False, [path_error], None
        
        return True, warnings, sanitized_command
    
    def _get_base_command(self, command):
        """Extract the base command from a command string"""
        # Handle pipes - get first command
        if '|' in command:
            command = command.split('|')[0]
        
        # Handle command chaining
        for sep in ['&&', '||', ';']:
            if sep in command:
                command = command.split(sep)[0]
        
        # Get first word
        parts = command.strip().split()
        if not parts:
            return ''
        
        cmd = parts[0]
        
        # Handle sudo
        if cmd == 'sudo' and len(parts) > 1:
            cmd = parts[1]
        
        # Handle path to command (/usr/bin/ls -> ls)
        if '/' in cmd:
            cmd = os.path.basename(cmd)
        
        return cmd
    
    def _sanitize_paths(self, command):
        """Expand and normalize paths in command"""
        result = command
        
        # Replace home directory references
        result = result.replace('~/', f'{self.sandbox_root}/')
        result = result.replace('$HOME/', f'{self.sandbox_root}/')
        result = result.replace('${HOME}/', f'{self.sandbox_root}/')
        result = result.replace('$HOME', self.sandbox_root)
        result = result.replace('${HOME}', self.sandbox_root)
        
        # Handle bare ~ at end of path
        result = re.sub(r'~(?=\s|$)', self.sandbox_root, result)
        
        return result
    
    def _extract_target_paths(self, command, base_cmd):
        """Extract target paths that would be modified by a write command"""
        paths = []
        parts = command.split()
        
        if base_cmd in ['rm', 'rmdir', 'shred']:
            # All non-flag arguments are targets
            for part in parts[1:]:
                if not part.startswith('-'):
                    paths.append(part)
                    
        elif base_cmd in ['mv', 'cp', 'ln']:
            # Last argument is target (destination)
            non_flags = [p for p in parts[1:] if not p.startswith('-')]
            if non_flags:
                paths.append(non_flags[-1])
                
        elif base_cmd in ['touch', 'mkdir']:
            # All non-flag arguments are targets
            for part in parts[1:]:
                if not part.startswith('-'):
                    paths.append(part)
                    
        elif base_cmd in ['chmod', 'chown']:
            # Arguments after mode/owner are targets
            non_flags = [p for p in parts[1:] if not p.startswith('-')]
            # Skip first non-flag (it's the mode/owner)
            paths.extend(non_flags[1:])
        
        return paths
    
    def _is_readonly_path(self, path):
        """Check if path is in a read-only mounted directory"""
        # Normalize path
        if not path.startswith('/'):
            path = f'{self.sandbox_root}/{path}'
        
        # Resolve relative components
        try:
            # Simple normalization without actual filesystem access
            path = os.path.normpath(path)
        except:
            pass
        
        for ro_path in self.readonly_mounts:
            if path.startswith(ro_path) or path == ro_path:
                return True
        
        return False
    
    def _is_in_sandbox(self, path):
        """Check if path is within the sandbox"""
        # Normalize path
        if not path.startswith('/'):
            path = f'{self.sandbox_root}/{path}'
        
        try:
            path = os.path.normpath(path)
        except:
            pass
        
        # Check against safe paths
        for safe_path in self.safe_paths:
            if path.startswith(safe_path) or path == safe_path:
                return True
        
        # Also allow current directory references that stay in sandbox
        if path.startswith('.'):
            return True
        
        return False
    
    def _validate_all_paths(self, command):
        """Validate that all paths in command are accessible"""
        # Extract potential paths from command
        parts = command.split()
        
        dangerous_paths = ['/etc', '/root', '/sys', '/proc', '/boot', '/dev/sd']
        
        for part in parts:
            # Skip flags
            if part.startswith('-'):
                continue
            
            # Check for dangerous paths
            for dangerous in dangerous_paths:
                if part.startswith(dangerous) or f'/{dangerous}' in part:
                    return False, f"❌ Access to {dangerous} is forbidden"
        
        # Check for directory traversal attacks
        if '/../' in command or command.endswith('/..'):
            # Count how many levels up
            levels_up = command.count('..')
            if levels_up > 3:  # Allow some relative navigation
                return False, "❌ Excessive directory traversal detected"
        
        return True, None
    
    def _detect_injection(self, command):
        """Detect potential command injection attempts"""
        warnings = []
        is_dangerous = False
        
        # Dangerous patterns that indicate injection
        dangerous_patterns = [
            (r';\s*rm\s+-rf', "Chained destructive command"),
            (r'\$\([^)]*rm[^)]*\)', "Command substitution with rm"),
            (r'`[^`]*rm[^`]*`', "Backtick command with rm"),
            (r'\|\s*sh\s*$', "Piping to shell"),
            (r'\|\s*bash\s*$', "Piping to bash"),
            (r'\|\s*zsh\s*$', "Piping to zsh"),
            (r'eval\s+', "Use of eval"),
            (r'2>&1.*\|\s*(nc|netcat)', "Potential reverse shell"),
            (r'>\s*/dev/null\s*2>&1\s*&', "Background execution with redirect"),
        ]
        
        for pattern, message in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                is_dangerous = True
                break
        
        # Check for suspicious but not necessarily dangerous patterns
        suspicious_patterns = [
            (r'\$\([^)]+\)', "Command substitution used"),
            (r'`[^`]+`', "Backtick substitution used"),
        ]
        
        for pattern, message in suspicious_patterns:
            if re.search(pattern, command):
                warnings.append(f"⚠️  {message}")
        
        return is_dangerous, warnings
    
    def is_safe_for_readonly(self, command):
        """Quick check if command is safe for read-only execution"""
        base_cmd = self._get_base_command(command)
        return base_cmd in self.readonly_commands
