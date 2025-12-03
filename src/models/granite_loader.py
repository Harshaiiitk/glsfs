# src/models/granite_loader.py
"""
Granite Model Loader for GLSFS

This module handles loading the fine-tuned Granite model and generating
bash commands from natural language queries.

PATH NORMALIZATION:
==================
The model may output paths in various formats:
  - "Desktop" or "desktop"
  - "Desktop/" or "Documents/file.txt"
  - "~/Desktop" or "$HOME/Documents"
  
This module normalizes ALL of these to absolute Docker paths:
  - /home/user/Desktop
  - /home/user/Documents
  - /home/user/Downloads
  - /home/user/workspace
"""

import torch
import os
import re


class GraniteCommandGenerator:
    def __init__(self, model_path=None):
        """
        Initialize with your fine-tuned Granite model
        
        Args:
            model_path: Path to your fine-tuned LoRA adapter
        """
        # Set default path if not provided
        if model_path is None:
            model_path = os.path.expanduser("~/glsfs/src/models/granite/glsfs_granite_finetuned")
        
        # Expand and normalize path
        model_path = os.path.expanduser(model_path)
        model_path = os.path.abspath(model_path)
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"❌ Model not found at {model_path}")
        
        print(f"⏳ Loading model from {model_path}...")
        
        try:
            # Try using unsloth (same as training)
            from unsloth import FastLanguageModel
            
            self.model, self.tokenizer = FastLanguageModel.from_pretrained(
                model_name=model_path,
                max_seq_length=2048,
                dtype=None,
                load_in_4bit=False,
            )
            
            FastLanguageModel.for_inference(self.model)
            print("✅ Model loaded with Unsloth!")
            
        except ImportError:
            print("⚠️  Unsloth not available, trying standard loading...")
            
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float32,
                device_map="cpu",
                low_cpu_mem_usage=True
            )
            self.model.eval()
            print("✅ Model loaded with Transformers!")
        
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        print()
        
    def generate_command(self, user_query):
        """
        Generate bash command from natural language query
        
        Args:
            user_query: Natural language question/request from user
            
        Returns:
            dict with 'command' and 'explanation' keys
        """
        system_message = "You are an expert Linux filesystem assistant. When users ask about file operations, provide accurate bash commands with clear explanations. For dangerous operations, include warnings."
        
        formatted_prompt = (
            f"System: {system_message}\n\n"
            f"User: {user_query}\n\n"
            f"Assistant:"
        )
        
        inputs = self.tokenizer(
            formatted_prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=2048
        )
        
        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.3,
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
        
        generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        if "Assistant:" in generated_text:
            response_text = generated_text.split("Assistant:")[-1].strip()
        else:
            response_text = generated_text.strip()
        
        command, explanation = self._parse_response(response_text)
        
        # CRITICAL: Normalize paths before returning
        command = self._normalize_paths(command)
        
        return {
            'command': command,
            'explanation': explanation,
            'raw_response': response_text
        }
    
    def _normalize_paths(self, command):
        """
        Normalize ALL path variations to absolute /home/user/ paths.
        
        Handles:
          - desktop, Desktop, DESKTOP -> /home/user/Desktop
          - documents/, Documents -> /home/user/Documents
          - ~/Desktop -> /home/user/Desktop
          - $HOME/Documents -> /home/user/Documents
          - Bare folder names at start of path arguments
        """
        if not command:
            return command
        
        # Fix common model output bugs
        command = command.replace('find.', 'find .')
        command = command.replace('ls.', 'ls .')
        
        # Handle ~ and $HOME first
        command = command.replace('~/', '/home/user/')
        command = command.replace('$HOME/', '/home/user/')
        command = command.replace('${HOME}/', '/home/user/')
        command = re.sub(r'~(?=\s|$|/)', '/home/user', command)
        command = re.sub(r'\$HOME(?=\s|$|/)', '/home/user', command)
        command = re.sub(r'\$\{HOME\}(?=\s|$|/)', '/home/user', command)
        
        # If already has /home/user/, we're mostly done
        # But still need to handle case sensitivity
        
        # Define the canonical folder mappings (case-insensitive)
        folder_mappings = {
            'desktop': '/home/user/Desktop',
            'documents': '/home/user/Documents',
            'downloads': '/home/user/Downloads',
            'workspace': '/home/user/workspace',
        }
        
        # Strategy: Split command into tokens, normalize path-like tokens
        # This handles cases like: ls -la desktop/ | head
        
        result = self._normalize_command_paths(command, folder_mappings)
        
        return result
    
    def _normalize_command_paths(self, command, folder_mappings):
        """
        Intelligently normalize paths in a command string.
        
        This function identifies path arguments in commands and normalizes them.
        """
        # Patterns that indicate a path argument follows
        # After these, the next token is likely a path
        path_indicators = [
            'ls', 'cat', 'head', 'tail', 'less', 'more',
            'find', 'grep', 'du', 'df', 'wc', 'file', 'stat',
            'cd', 'tree', 'mkdir', 'rmdir', 'touch', 'rm',
            'cp', 'mv', 'chmod', 'chown',
            '-name', '-path', '-type',  # find arguments
            '-C',  # some commands use -C for directory
        ]
        
        # Split preserving quotes and special characters
        tokens = self._tokenize_command(command)
        normalized_tokens = []
        
        for i, token in enumerate(tokens):
            normalized = self._normalize_single_path(token, folder_mappings)
            normalized_tokens.append(normalized)
        
        return ' '.join(normalized_tokens)
    
    def _tokenize_command(self, command):
        """
        Split command into tokens, preserving quoted strings.
        """
        tokens = []
        current = ""
        in_quote = None
        
        for char in command:
            if char in '"\'':
                if in_quote == char:
                    in_quote = None
                elif in_quote is None:
                    in_quote = char
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
    
    def _normalize_single_path(self, token, folder_mappings):
        """
        Normalize a single token if it looks like a path.
        """
        # Skip flags, operators, and special tokens
        if token.startswith('-') or token in ['|', '&&', '||', ';', '>', '<', '>>', '2>', '2>&1']:
            return token
        
        # Skip if already an absolute path (but might need case fixing)
        if token.startswith('/home/user/'):
            # Fix case: /home/user/documents -> /home/user/Documents
            for folder_lower, folder_correct in folder_mappings.items():
                wrong_case = f'/home/user/{folder_lower}'
                if token.lower().startswith(wrong_case.lower()):
                    # Replace the folder part with correct case
                    remainder = token[len(wrong_case):]
                    return folder_correct + remainder
            return token
        
        # Skip other absolute paths
        if token.startswith('/'):
            return token
        
        # Check if token starts with a known folder name (case-insensitive)
        token_lower = token.lower()
        
        for folder_lower, folder_correct in folder_mappings.items():
            # Match: "desktop", "desktop/", "desktop/file.txt", "Desktop/subdir/file"
            if token_lower == folder_lower:
                # Bare folder name: desktop -> /home/user/Desktop
                return folder_correct
            
            if token_lower.startswith(folder_lower + '/'):
                # Folder with path: desktop/file.txt -> /home/user/Desktop/file.txt
                remainder = token[len(folder_lower):]  # Keep original case for remainder
                return folder_correct + remainder
        
        # Check for patterns like "*.pdf" in current directory - leave as is
        # Check for relative paths like "./something" - leave as is
        
        return token
    
    def _parse_response(self, response_text):
        """Parse response to extract command and explanation"""
        lines = response_text.strip().split('\n')
        
        command_lines = []
        explanation_lines = []
        found_blank = False
        
        for line in lines:
            stripped = line.strip()
            
            if not found_blank:
                if stripped == '':
                    found_blank = True
                elif not stripped.startswith('#') and not stripped.startswith('This') and not stripped.startswith('The '):
                    command_lines.append(stripped)
                else:
                    found_blank = True
                    explanation_lines.append(stripped)
            else:
                explanation_lines.append(stripped)
        
        command = ' '.join(command_lines).strip()
        explanation = ' '.join(explanation_lines).strip()
        
        # Fallback: look for command pattern at start
        if not command:
            command_starters = r'^(find|ls|grep|du|df|cat|head|tail|sort|chmod|rm|cp|mv|mkdir|touch|echo|wc|file|stat|tree|pwd|less|more|awk|sed|cut|uniq|diff)\b'
            match = re.match(command_starters, response_text, re.IGNORECASE)
            if match:
                first_line_end = response_text.find('\n')
                if first_line_end > 0:
                    command = response_text[:first_line_end].strip()
                    explanation = response_text[first_line_end:].strip()
                else:
                    command = response_text.strip()
                    explanation = ""
            else:
                command = response_text.strip()
                explanation = ""
        
        # Clean up command
        command = self._clean_command(command)
        
        return command, explanation
    
    def _clean_command(self, command):
        """Clean up command formatting issues"""
        if not command:
            return command
        
        # Fix spacing issues
        command = command.replace('find.', 'find .')
        command = command.replace('ls.', 'ls .')
        
        # Remove wrapping quotes
        if (command.startswith('"') and command.endswith('"')) or \
           (command.startswith("'") and command.endswith("'")):
            command = command[1:-1]
        
        # Remove markdown code formatting
        if command.startswith('`') and command.endswith('`'):
            command = command[1:-1]
        
        # Remove shell prompt prefixes
        for prefix in ['$ ', '# ', '> ']:
            if command.startswith(prefix):
                command = command[len(prefix):]
        
        return command.strip()