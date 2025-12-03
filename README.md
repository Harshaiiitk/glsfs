# glsfs
CS550 Term Project
# GLSFS - Granite LLM Semantic File System

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)

> **A production-ready competitor to AIOS-LSFS** - Natural language filesystem operations powered by a fine-tuned IBM Granite 3B model.

GLSFS translates natural language queries into safe, executable filesystem commands. Ask questions like *"Show me all PDF files in my Documents"* and get accurate bash commands executed in an isolated Docker sandbox.

## 🎯 Key Features

- **Natural Language Interface**: Ask filesystem questions in plain English
- **Fine-tuned Granite 3B Model**: 99.50% semantic accuracy, 0.4% failure rate
- **Safe Execution**: Multi-layer safety validation + Docker sandbox isolation
- **Real File Access**: Mounts your actual Mac folders (Desktop, Documents, Downloads)
- **Read-Only Protection**: Your files are mounted read-only - cannot be modified or deleted

## 📊 Performance Metrics

| Metric | Score |
|--------|-------|
| Semantic Accuracy | 99.50% |
| Syntax Correctness | 100% |
| Failure Rate | 0.4% |
| Inference Time | 3-5 seconds (Mac GPU) |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GLSFS System                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │   User      │    │   Granite   │    │   Safety            │ │
│  │   Query     │ -> │   Model     │ -> │   Validator         │ │
│  │             │    │   (3B)      │    │                     │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│                                                │                │
│                                                ▼                │
│                           ┌─────────────────────────────────┐  │
│                           │      Sandbox Executor           │  │
│                           │   ┌─────────────────────────┐   │  │
│                           │   │    Docker Container     │   │  │
│                           │   │  ┌─────────────────┐    │   │  │
│                           │   │  │ Your Mac Files  │    │   │  │
│                           │   │  │ (mounted r/o)   │    │   │  │
│                           │   │  └─────────────────┘    │   │  │
│                           │   └─────────────────────────┘   │  │
│                           └─────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
glsfs/
├── main.py                      # Entry point - CLI interface
├── app.py                       # Web interface (Gradio)
├── requirements.txt             # Python dependencies
├── data/
│   ├── Dockerfile              # Docker sandbox configuration
│   └── workspace/              # Read-write workspace (synced to Docker)
├── src/
│   ├── __init__.py
│   ├── glsfs_system.py         # Main orchestrator - ties everything together
│   ├── models/
│   │   ├── __init__.py
│   │   ├── granite_loader.py   # Model loading and inference
│   │   └── granite/
│   │       └── glsfs_granite_finetuned/  # Fine-tuned model weights
│   ├── safety/
│   │   ├── __init__.py
│   │   └── validator.py        # Command safety validation
│   └── sandbox/
│       ├── __init__.py
│       └── executor.py         # Docker/local command execution
└── logs/
    └── lsfs_operations.json    # Operation audit log
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+**
- **Docker Desktop** (for Mac/Windows) or Docker Engine (Linux)
- **8GB+ RAM** (for model inference)
- **macOS, Linux, or Windows with WSL2**

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/glsfs.git
cd glsfs
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Download the Fine-tuned Model

Download the fine-tuned Granite model and place it in:
```
glsfs/src/models/granite/glsfs_granite_finetuned/
```

The folder should contain:
- `config.json`
- `tokenizer.json`
- `model.safetensors` (or `.bin` files)
- Other model files

### Step 5: Build Docker Sandbox

```bash
cd data

# For Apple Silicon Macs (M1/M2/M3) - IMPORTANT!
docker build --platform linux/amd64 -t glsfs-sandbox .

# For Intel Macs or Linux
docker build -t glsfs-sandbox .
```

> ⚠️ **Apple Silicon Users**: You MUST use `--platform linux/amd64` for the Python Docker SDK to find the image correctly.

### Step 6: Configure Docker File Sharing (Mac Only)

For Docker to access your Mac folders:

1. Open **Docker Desktop**
2. Go to **Settings** (⚙️ gear icon)
3. Navigate to **Resources** → **File Sharing**
4. Ensure these paths are shared:
   - `/Users/YOUR_USERNAME/Desktop`
   - `/Users/YOUR_USERNAME/Documents`
   - `/Users/YOUR_USERNAME/Downloads`
5. Click **Apply & Restart**

### Step 7: Run GLSFS

```bash
cd ~/glsfs
python main.py
```

Or with explicit model path:
```bash
python main.py --model-path ~/glsfs/src/models/granite/glsfs_granite_finetuned
```

---

## 💻 Usage

### Interactive Mode (Default)

```bash
python main.py
```

```
💬 Your query: Show all PDF files in Documents
📝 Generated command: find /home/user/Documents -name "*.pdf" -type f
🐳 Executing in Docker...
✅ Output:
/home/user/Documents/report.pdf
/home/user/Documents/thesis.pdf
```

### Single Query Mode

```bash
python main.py --query "How much space does my Downloads folder use?"
```

### Web Interface

```bash
python main.py --mode web
# Opens at http://localhost:7860
```

### Without Docker (Not Recommended)

```bash
python main.py --no-docker
```

---

## 🔧 Code Explanation

### `main.py` - Entry Point

The main entry point that parses command-line arguments and initializes the system.

```python
# Key functionality:
- Parse arguments (--model-path, --mode, --query, --no-docker)
- Initialize LSFSCompetitor system
- Run interactive mode, web mode, or single query
```

### `src/glsfs_system.py` - Main Orchestrator

The central coordinator that ties all components together.

```python
class LSFSCompetitor:
    def __init__(self, model_path, use_docker):
        # 1. Load Granite model
        # 2. Initialize safety validator
        # 3. Set up sandbox executor
    
    def process_query(self, query):
        # Pipeline:
        # 1. Generate command (Granite model)
        # 2. Validate safety
        # 3. Execute in sandbox
        # 4. Return results
```

### `src/models/granite_loader.py` - Model Interface

Handles loading and inference with the fine-tuned Granite model.

```python
class GraniteCommandGenerator:
    def generate_command(self, user_query):
        # 1. Format prompt with system message
        # 2. Tokenize input
        # 3. Generate with model
        # 4. Parse command and explanation
        # 5. Normalize paths (Desktop -> /home/user/Desktop)
        return {'command': ..., 'explanation': ...}
```

**Key Features:**
- Tries Unsloth first (faster), falls back to Transformers
- Normalizes relative paths to absolute Docker paths
- Fixes common model output issues (e.g., `find.` → `find .`)

### `src/safety/validator.py` - Security Layer

Validates commands before execution to prevent dangerous operations.

```python
class CommandSafetyValidator:
    def validate(self, command):
        # 1. Check forbidden patterns (rm -rf /, fork bombs, etc.)
        # 2. Sanitize paths (expand ~, $HOME)
        # 3. Check read-only restrictions
        # 4. Detect command injection
        # 5. Validate paths are in sandbox
        return (is_safe, warnings, sanitized_command)
```

**Blocked Operations:**
- `rm -rf /` and variants
- Fork bombs
- Direct disk access (`/dev/sda`)
- Command injection (`curl | bash`)
- Write operations on read-only mounts

### `src/sandbox/executor.py` - Execution Engine

Executes commands safely in Docker or locally with path translation.

```python
class SandboxExecutor:
    def __init__(self, use_docker):
        # Set up Docker container with volume mounts:
        # ~/Desktop    → /home/user/Desktop   (read-only)
        # ~/Documents  → /home/user/Documents (read-only)
        # ~/Downloads  → /home/user/Downloads (read-only)
        # ~/glsfs/data/workspace → /home/user/workspace (read-write)
    
    def execute(self, command):
        if self.use_docker:
            return self._execute_docker(command)
        else:
            # Translate paths and run locally
            translated = self._translate_path_for_local(command)
            return self._execute_local(translated)
```

**How Mounting Works:**
```
YOUR MAC                              DOCKER CONTAINER
────────────────────────────────────────────────────────
~/Desktop/file.txt     ←→     /home/user/Desktop/file.txt
                         │
                    (same file!)
```

---

## 🐳 Docker Mounting Explained

When GLSFS starts, it creates a Docker container with your Mac folders **mounted** inside:

| Mac Path | Docker Path | Mode | Purpose |
|----------|-------------|------|---------|
| `~/Desktop` | `/home/user/Desktop` | Read-Only | View your files |
| `~/Documents` | `/home/user/Documents` | Read-Only | View your files |
| `~/Downloads` | `/home/user/Downloads` | Read-Only | View your files |
| `~/glsfs/data/workspace` | `/home/user/workspace` | Read-Write | Create new files |

**Why Read-Only?**
- Protects your real files from accidental deletion
- Even if the AI generates `rm -rf /home/user/Desktop/*`, it **fails**
- Your files are completely safe!

---

## ⚠️ Troubleshooting

### Docker Image Not Found (Apple Silicon)

**Problem:**
```
❌ Docker image 'glsfs-sandbox' not found!
```

**Solution:**
```bash
docker build --platform linux/amd64 -t glsfs-sandbox .
```

### Permission Denied on Mac Folders

**Problem:** Docker can't access Desktop/Documents/Downloads

**Solution:**
1. Open Docker Desktop → Settings → Resources → File Sharing
2. Add your folders
3. Apply & Restart

### Container Keeps Failing

**Solution:**
```bash
# Remove old container
docker stop glsfs-sandbox-exec
docker rm glsfs-sandbox-exec

# Rebuild image
cd ~/glsfs/data
docker build --platform linux/amd64 -t glsfs-sandbox .

# Run again
python main.py
```

### Model Loading Slow

The model takes 15-30 seconds to load on first run. Subsequent queries are faster (3-5 seconds).

### Tokenizer Warning

```
huggingface/tokenizers: The current process just got forked...
```

This is harmless. To suppress:
```bash
export TOKENIZERS_PARALLELISM=false
python main.py
```

---

## 📈 Training Details

The model was fine-tuned using:

- **Base Model**: IBM Granite 3B
- **Method**: LoRA with Unsloth optimizations
- **Dataset**: ~2,700 natural language → command pairs
- **Hardware**: A100 GPU
- **Training Time**: ~12 minutes (0.28 sec/sample)

---

## 🔒 Security Considerations

1. **Docker Isolation**: Commands run in a container, not on your system
2. **Read-Only Mounts**: Your files cannot be modified through Docker
3. **Command Validation**: Dangerous patterns are blocked before execution
4. **Path Restrictions**: Commands can only access allowed directories
5. **Audit Logging**: All operations are logged for review

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- IBM Research for the Granite model family
- Hugging Face for transformers and model hosting
- Unsloth for efficient fine-tuning
- AIOS-LSFS paper for inspiration

---

## 📚 References

1. [AIOS-LSFS Paper](https://arxiv.org/abs/2410.11843) - LLM-based Semantic File System
2. [LoRA Paper](https://arxiv.org/abs/2106.09685) - Low-Rank Adaptation
3. [IBM Granite Models](https://github.com/ibm-granite) - Model family documentation