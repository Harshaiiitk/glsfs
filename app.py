# app.py

import gradio as gr
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.glsfs_system import LSFSCompetitor

# Initialize system
MODEL_PATH = os.getenv(
    'GLSFS_MODEL_PATH',
    os.path.expanduser("~/glsfs/src/models/granite/glsfs_granite_finetuned")
)

print(f"Initializing web interface with model: {MODEL_PATH}")

try:
    lsfs = LSFSCompetitor(MODEL_PATH, use_docker=True)
except Exception as e:
    print(f"❌ Failed to initialize: {e}")
    raise

def process_user_query(query, auto_execute):
    """Process user query and return formatted results"""
    if not query:
        return "⚠️ Please enter a query", "", "No query provided"
    
    try:
        result = lsfs.process_query(query, auto_execute=auto_execute)
        
        # Extract command
        command = result.get('final_command', result.get('generated_command', 'N/A'))
        
        # Extract explanation
        explanation = result.get('explanation', '')
        if explanation:
            command_display = f"{command}\n\n💡 {explanation}"
        else:
            command_display = command
        
        # Format output based on status
        if result['status'] == 'blocked':
            output = "⛔ COMMAND BLOCKED FOR SAFETY\n\n"
            output += "\n".join(result.get('warnings', []))
            status = "🔴 Blocked"
            
        elif result['status'] == 'cancelled_by_user':
            output = "🚫 Execution cancelled by user"
            status = "🟡 Cancelled"
            
        elif result['status'] == 'completed' and 'execution' in result:
            exec_result = result['execution']
            
            if exec_result['status'] == 'success':
                output = "✅ EXECUTION SUCCESSFUL\n\n"
                if exec_result.get('stdout'):
                    output += "Output:\n" + exec_result['stdout']
                else:
                    output += "(No output)"
                status = "🟢 Success"
            else:
                output = "❌ EXECUTION FAILED\n\n"
                if exec_result.get('stderr'):
                    output += "Error:\n" + exec_result['stderr']
                else:
                    output += exec_result.get('error', 'Unknown error')
                status = "🔴 Failed"
        else:
            output = json.dumps(result, indent=2)
            status = result.get('status', 'Unknown')
        
        return command_display, output, status
        
    except Exception as e:
        return "Error", f"❌ System error: {str(e)}", "🔴 Error"

# Create Gradio interface WITHOUT theme parameter
with gr.Blocks(title="GLSFS - Granite LLM Semantic File System") as demo:
    gr.Markdown("""
    # 🚀 GLSFS - Granite LLM Semantic File System
    ### Natural Language Filesystem Operations (AIOS-LSFS Competitor)
    
    Ask questions about your filesystem in plain English! Commands execute safely in an isolated Docker container.
    """)
    
    with gr.Row():
        with gr.Column(scale=1):
            query_input = gr.Textbox(
                label="💬 Your Query",
                placeholder="e.g., 'What files are on my desktop?' or 'Show all Python files'",
                lines=3
            )
            
            auto_execute = gr.Checkbox(
                label="🚀 Auto-execute commands (uncheck to review first)",
                value=True
            )
            
            submit_btn = gr.Button("🔍 Process Query", variant="primary")
            
            gr.Markdown("### 📝 Example Queries")
            gr.Examples(
                examples=[
                    ["list all files in Desktop"],
                    ["show contents of sample1.txt in Desktop"],
                    ["create file test.txt in Desktop"],
                    ["find files modified today"],
                    ["show disk usage"],
                    ["count how many log files I have"],
                ],
                inputs=query_input
            )
        
        with gr.Column(scale=1):
            status_output = gr.Textbox(label="📊 Status", lines=1)
            command_output = gr.Textbox(label="📝 Generated Command", lines=4)
            execution_output = gr.Textbox(label="📤 Output", lines=12)
    
    gr.Markdown("""
    ---
    ### ⚙️ System Info
    - **Model**: Granite 3B (Fine-tuned for filesystem operations)
    - **Safety**: All commands validated before execution
    - **Sandbox**: Commands run in isolated Docker container
    - **Performance**: 90% semantic accuracy, 100% syntax correctness
    """)
    
    submit_btn.click(
        process_user_query,
        inputs=[query_input, auto_execute],
        outputs=[command_output, execution_output, status_output]
    )

if __name__ == "__main__":
    demo.launch(
        share=False,
        server_port=7860,
        server_name="127.0.0.1"
    )