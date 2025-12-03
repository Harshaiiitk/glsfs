# src/safety/validator.py

import re
import os

class CommandSafetyValidator:
    def __init__(self, sandbox_root="/home/user"):
        """Initialize safety validator"""
        # Dangerous commands that should NEVER be executed
        self.forbidden_patterns = [
            r'rm\s+-rf\s+/\s*$',
            r'rm\s+-rf\s+/\s+',
            r'rm\s+-rf\s+~\s*$',
            r':\(\)\{:\|:&\};:',
            r'dd\s+if=/dev/(zero|random)\s+of=/dev/sd',
            r'mkfs',
            r'>\s*/dev/sd[a-z]',
            r'chmod\s+-R\s+777\s+/',
            r'chown\s+-R.*/',
            r'/dev/sd[a-z]',
            r'curl.*\|\s*bash',
            r'wget.*\|\s*sh',
        ]
        
        # Commands requiring confirmation (but allowed)
        self.warning_commands = ['rm', 'mv', 'chmod', 'chown']
        
        # Allowed directories (sandbox paths)
        self.safe_paths = [
            '/home/user',
            '/home/user/Desktop',
            '/home/user/Documents', 
            '/home/user/Downloads',
            '/workspace',
            '/tmp'
        ]
        
        # Relative path prefixes that are safe (in Docker context)
        self.safe_relative_prefixes = [
            'Desktop/',
            'Documents/',
            'Downloads/',
            './',
            '../',  # Only if it doesn't escape /home/user
        ]
        
        self.sandbox_root = sandbox_root
        
    def validate(self, command):
        """Validate if command is safe to execute"""
        warnings = []
        
        # Step 1: Check for forbidden patterns
        for pattern in self.forbidden_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, [f"❌ FORBIDDEN: Dangerous operation detected matching pattern: {pattern}"], None
        
        # Step 2: Check for warning commands
        for warn_cmd in self.warning_commands:
            if warn_cmd in command:
                warnings.append(f"⚠️  Warning: Command contains '{warn_cmd}' - destructive operation")
        
        # Step 3: Sanitize paths
        try:
            sanitized_command = self._sanitize_paths(command)
        except ValueError as e:
            return False, [f"❌ Path validation failed: {str(e)}"], None
        
        # Step 4: Check for command injection
        injection_detected, injection_warnings = self._detect_injection(sanitized_command)
        if injection_detected:
            return False, [f"❌ Security risk: {w}" for w in injection_warnings], None
        
        warnings.extend(injection_warnings)
        
        # Step 5: Validate paths (FIXED - allows relative paths in Docker context)
        if not self._validate_sandbox_paths(sanitized_command):
            return False, ["❌ FORBIDDEN: Command attempts to access paths outside sandbox"], None
        
        is_safe = True
        return is_safe, warnings, sanitized_command
    
    def _sanitize_paths(self, command):
        """Ensure paths are within sandbox boundaries"""
        # Replace home directory references
        command = command.replace('~/', f'{self.sandbox_root}/')
        command = command.replace('$HOME', self.sandbox_root)
        command = command.replace('${HOME}', self.sandbox_root)
        
        # Handle common directory shortcuts
        command = command.replace('~/Desktop', f'{self.sandbox_root}/Desktop')
        command = command.replace('~/Documents', f'{self.sandbox_root}/Documents')
        command = command.replace('~/Downloads', f'{self.sandbox_root}/Downloads')
        
        return command

    def _validate_sandbox_paths(self, command):
        """Ultra-permissive validator - only blocks dangerous system paths"""
        
        # Block dangerous absolute paths
        dangerous = ['/etc/', '/root/', '/sys/', '/proc/', '/boot/', r'/dev/sd[a-z]']
        for pattern in dangerous:
            if re.search(pattern, command):
                return False
        
        # Block excessive escapes and dangerous relative paths
        if '../../../' in command or any(d in command for d in ['etc/', 'root/', 'sys/', 'proc/']):
            return False
        
        return True  # Everything else allowed

    def _detect_injection(self, command):
        """Detect potential command injection attempts"""
        warnings = []
        is_dangerous = False
        
        # Check for dangerous character combinations
        dangerous_patterns = [
            (r';\s*rm\s+-rf', "Chained rm -rf command detected"),
            (r'\$\([^)]+\)', "Command substitution detected"),
            (r'`[^`]+`', "Backtick command substitution detected"),
            (r'\|\s*sh\s*$', "Piping to shell detected"),
            (r'\|\s*bash\s*$', "Piping to bash detected"),
            (r'2>&1.*\|\s*nc', "Potential reverse shell detected"),
        ]
        
        for pattern, message in dangerous_patterns:
            if re.search(pattern, command):
                warnings.append(message)
                is_dangerous = True
        
        # Check for safe usage of special characters
        special_chars = {
            '&&': self._is_safe_and_usage,
            '||': self._is_safe_or_usage,
            ';': self._is_safe_semicolon_usage,
            '|': self._is_safe_pipe_usage,
        }
        
        for char, check_func in special_chars.items():
            if char in command:
                if not check_func(command):
                    warnings.append(f"Potentially unsafe use of '{char}'")
        
        return is_dangerous, warnings
    
    def _is_safe_and_usage(self, command):
        """Check if && usage is safe"""
        safe_patterns = [
            r'mkdir.*&&.*cd',
            r'test.*&&.*echo',
            r'\[\s*.*\]\s*&&.*echo',
            r'find.*&&.*wc',
        ]
        
        for pattern in safe_patterns:
            if re.search(pattern, command):
                return True
        return False
    
    def _is_safe_or_usage(self, command):
        """Check if || usage is safe"""
        safe_patterns = [
            r'\|\|\s*echo',
            r'\|\|\s*printf',
            r'\|\|\s*true',
        ]
        
        for pattern in safe_patterns:
            if re.search(pattern, command):
                return True
        return False
    
    def _is_safe_semicolon_usage(self, command):
        """Check if semicolon usage separates safe commands"""
        parts = command.split(';')
        forbidden_after_semi = ['rm -rf /', 'dd if=', 'mkfs']
        
        for part in parts:
            part = part.strip()
            for forbidden in forbidden_after_semi:
                if forbidden in part:
                    return False
        return True
    
    def _is_safe_pipe_usage(self, command):
        """Check if pipe usage is for safe operations"""
        dangerous_pipe_targets = [
            r'\|\s*sh\s*$',
            r'\|\s*bash\s*$',
            r'\|\s*eval',
            r'\|\s*sudo',
        ]
        
        for pattern in dangerous_pipe_targets:
            if re.search(pattern, command):
                return False
        
        safe_pipes = [
            r'\|\s*grep',
            r'\|\s*sort',
            r'\|\s*uniq',
            r'\|\s*wc',
            r'\|\s*head',
            r'\|\s*tail',
            r'\|\s*awk',
            r'\|\s*sed',
            r'\|\s*cut',
            r'\|\s*xargs\s+(ls|cat|grep)',
        ]
        
        for pattern in safe_pipes:
            if re.search(pattern, command):
                return True
        
        return False
