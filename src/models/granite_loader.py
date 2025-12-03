# src/models/granite_loader.py

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
                load_in_4bit=False,  # Set to False for inference on Mac
            )
            
            # Enable fast inference mode
            FastLanguageModel.for_inference(self.model)
            
            print("✅ Model loaded with Unsloth!")
            
        except ImportError:
            print("⚠️  Unsloth not available, trying standard loading...")
            
            # Fallback to standard transformers
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float32,  # Use float32 for Mac
                device_map="cpu",  # Force CPU on Mac
                low_cpu_mem_usage=True
            )
            self.model.eval()
            
            print("✅ Model loaded with Transformers!")
        
        # Set padding token
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
        # Format prompt EXACTLY as in training
        system_message = "You are an expert Linux filesystem assistant. When users ask about file operations, provide accurate bash commands with clear explanations. For dangerous operations, include warnings."
        
        formatted_prompt = (
            f"System: {system_message}\n\n"
            f"User: {user_query}\n\n"
            f"Assistant:"
        )
        
        # Tokenize
        inputs = self.tokenizer(
            formatted_prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=2048
        )
        
        # Move to model device
        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Generate
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
        
        # Decode
        generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract assistant response
        if "Assistant:" in generated_text:
            response_text = generated_text.split("Assistant:")[-1].strip()
        else:
            response_text = generated_text.strip()
        
        # Parse command and explanation
        command, explanation = self._parse_response(response_text)
        
        return {
            'command': command,
            'explanation': explanation,
            'raw_response': response_text
        }
    
    def _normalize_paths(self, command):
        """Convert Desktop/Documents/Downloads to absolute paths"""
        import re
        
        if '/home/user/' not in command:
            # Fix spacing bug
            command = command.replace('find.', 'find .')
            
            # Normalize directory references
            replacements = [
                (r'(\s|^)(Desktop/)', r'\1/home/user/Desktop/'),
                (r'(\s|^)(Documents/)', r'\1/home/user/Documents/'),
                (r'(\s|^)(Downloads/)', r'\1/home/user/Downloads/'),
                (r'(\s|^)(Desktop)(\s|$)', r'\1/home/user/Desktop\3'),
                (r'(\s|^)(Documents)(\s|$)', r'\1/home/user/Documents\3'),
                (r'(\s|^)(Downloads)(\s|$)', r'\1/home/user/Downloads\3'),
            ]
            
            for pattern, replacement in replacements:
                command = re.sub(pattern, replacement, command)
        
        return command
    
    def _parse_response(self, response_text):
        """Parse response to extract command and explanation"""
        lines = response_text.strip().split('\n')
        
        command_lines = []
        explanation_lines = []
        found_blank = False
        
        for line in lines:
            if not found_blank:
                if line.strip() == '':
                    found_blank = True
                elif not line.startswith('#') and not line.startswith('This'):
                    command_lines.append(line.strip())
                else:
                    found_blank = True
                    explanation_lines.append(line.strip())
            else:
                explanation_lines.append(line.strip())
        
        command = ' '.join(command_lines).strip()
        explanation = ' '.join(explanation_lines).strip()
        
        # Fallback: look for command at start
        if not command:
            command_pattern = r'^(find|ls|grep|du|df|cat|head|tail|sort|chmod|rm|cp|mv|mkdir|touch|echo)\b.*'
            match = re.match(command_pattern, response_text, re.IGNORECASE)
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
        command = command.replace('find.', 'find .')    
        command = self._normalize_paths(command)    
        return command, explanation
