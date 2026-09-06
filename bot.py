"""
Re-AI Agent - Telegram AI Agent Bot (Upgraded)
Command execution, file operations, app building capabilities
Powered by Groq API with function calling
"""

import os
import re
import json
import time
import subprocess
import asyncio
import shutil
import mimetypes
from datetime import datetime
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
GROQ_API_KEY = os.environ.get("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", "")
TELEGRAM_TOKEN = os.environ.get("8852693470:AAHOb7QP5zmt5n29xcRt0oWL3xzy43OKtU4","")

groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# User conversation history
user_history = {}
MAX_HISTORY = 20

# Per-user mode storage
user_modes = {}

MODES = {
    "1": ("general",    "🌐 General",    "ဘက်လိုက်မှုမရှိ၊ ကောင်းမွန်သော ဖြေဆိုမှု (default)"),
    "2": ("creative",   "🎨 Creative",   "စိတ်ကူးဉာဏ်ရှိသော၊ တီထွင်ဖန်တီးမှုများသော ဖြေဆိုမှု"),
    "3": ("technical",  "🔧 Technical",  "အသေးစိတ်၊ တိကျသော technical ဖြေဆိုမှု"),
    "4": ("brief",      "✂️ Brief",      "တိုတိုနှင့် ရှင်းလင်းသော ဖြေဆိုမှု"),
    "5": ("myanmar",    "🇲🇲 Myanmar+",  "မြန်မာဘာသာ အလေးပေး၊ ရင်းနှီးသော ပြောဆိုမှု"),
}

MODE_EXTRA = {
    "general":   "",
    "creative":  "တီထွင်ဖန်တီးတတ်သော၊ မထင်မှတ်သော perspectives များ ပေးပါ။ ရုပ်ဝတ္ထုပုံဆောင်ချက်များ သုံးပါ။",
    "technical": "အသေးစိတ် technical ရှင်းပြချက်များ ပေးပါ။ Code examples များ ထည့်ပါ။ Edge cases တွေကိုပါ ဆွေးနွေးပါ။",
    "brief":     "တိုတိုနှင့် အဓိကကိုသာ ပြောပါ။ 3-5 ကြောင်းထက် မကျော်ပါနှင့်။ Bullet points သုံးပါ။",
    "myanmar":   "ရင်းနှီးသော မြန်မာဘာသာ (informal) သုံးပါ။ ဆရာ/မ မလိုပါ၊ သူငယ်ချင်းကဲ့သို့ ပြောဆိုပါ။",
}

# Workspace dir per user (sandbox)
WORKSPACE_BASE = Path("/tmp/agent_workspace")
WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)

def get_workspace(user_id: int) -> Path:
    ws = WORKSPACE_BASE / str(user_id)
    ws.mkdir(parents=True, exist_ok=True)
    return ws

# ============================================================
# SYSTEM PROMPT - Myanmar language always
# ============================================================
SYSTEM_PROMPT = """သင်သည် Re-AI Agent ဖြစ်သည်။ သင်သည် အမိန့်များ execute လုပ်နိုင်သည်၊ files များ ရေးနိုင်/ဖတ်နိုင်သည်၊ applications များ build လုပ်နိုင်သည်။

**အရေးကြီးသောစည်းကမ်း: အမြဲ မြန်မာဘာသာဖြင့်သာ ဖြေဆိုရမည်။ English မသုံးရ။**

သင့်တွင် အောက်ပါ tools များရှိသည်:
- `execute_command` — shell command များ run နိုင်
- `write_file` — file ရေးနိုင်
- `read_file` — file ဖတ်နိုင်
- `list_directory` — folder ထဲ files ကြည့်နိုင်
- `install_package` — pip package install နိုင်
- `run_python_file` — Python file run နိုင်
- `create_project` — app project တစ်ခု scaffold လုပ်နိုင်
- `delete_file` — file ဖျက်နိုင်

**Agent ဆုံးဖြတ်ချက်များ:**
- User သည် "command run ပါ"、"file ရေး"、"app build" ဟု တောင်းဆိုလာပါက tool ကို အသုံးပြုပါ
- Tool result ကို မြန်မာဘာသာဖြင့် ရှင်းပြပါ
- Error ဖြစ်ပါက ဘာကြောင့် error ဖြစ်သည်ကို ရှင်းပြပြီး fix လုပ်နည်းကို အကြံပေးပါ
- Code ကို code block ဖြင့် ပြပါ
- Step-by-step ရှင်းပြပါ
"""

# ============================================================
# TOOL DEFINITIONS
# ============================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Shell command တစ်ခု execute လုပ်သည်။ ls, mkdir, git, python, node, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Run မည့် shell command"},
                    "working_dir": {"type": "string", "description": "Command run မည့် directory (optional)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "File တစ်ခုကို ရေးသည် သို့မဟုတ် create လုပ်သည်",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "File path (workspace-relative)"},
                    "content": {"type": "string", "description": "File ထဲ ရေးမည့် content"}
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "File တစ်ခု၏ content ကို ဖတ်သည်",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "ဖတ်မည့် file path"}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Directory ထဲ files နှင့် folders များ ကြည့်သည်",
            "parameters": {
                "type": "object",
                "properties": {
                    "dirpath": {"type": "string", "description": "Directory path (blank = workspace root)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "install_package",
            "description": "pip ဖြင့် Python package တစ်ခု install လုပ်သည်",
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {"type": "string", "description": "Install မည့် package name (e.g. 'requests', 'flask')"}
                },
                "required": ["package"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_python_file",
            "description": "Python file တစ်ခုကို run သည်",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Run မည့် .py file path"},
                    "args": {"type": "string", "description": "Command line arguments (optional)"}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": "App project တစ်ခု scaffold လုပ်သည် (python-basic, flask-app, fastapi-app, html-app)",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_type": {
                        "type": "string",
                        "description": "Project type: python-basic, flask-app, fastapi-app, html-app, node-app"
                    },
                    "project_name": {"type": "string", "description": "Project folder name"}
                },
                "required": ["project_type", "project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "File သို့မဟုတ် folder တစ်ခု ဖျက်သည်",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "ဖျက်မည့် file/folder path"}
                },
                "required": ["filepath"]
            }
        }
    }
]

# ============================================================
# TOOL EXECUTORS
# ============================================================
def tool_execute_command(user_id: int, command: str, working_dir: str = None) -> str:
    ws = get_workspace(user_id)
    cwd = ws / working_dir if working_dir else ws
    cwd.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=60, cwd=str(cwd)
        )
        output = result.stdout or ""
        error = result.stderr or ""
        code = result.returncode
        response = f"Exit code: {code}\n"
        if output:
            response += f"Output:\n{output}"
        if error:
            response += f"Stderr:\n{error}"
        return response.strip() or "Command completed (no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (60s limit)"
    except Exception as e:
        return f"Error: {str(e)}"


def tool_write_file(user_id: int, filepath: str, content: str) -> str:
    ws = get_workspace(user_id)
    # Sanitize path to stay inside workspace
    safe_path = ws / Path(filepath).name if "/" not in filepath else ws / filepath.lstrip("/")
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        safe_path.write_text(content, encoding="utf-8")
        return f"File saved: {safe_path.relative_to(ws)}\nSize: {safe_path.stat().st_size} bytes"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def tool_read_file(user_id: int, filepath: str) -> str:
    ws = get_workspace(user_id)
    safe_path = ws / Path(filepath).name if "/" not in filepath else ws / filepath.lstrip("/")
    try:
        content = safe_path.read_text(encoding="utf-8")
        if len(content) > 3000:
            content = content[:3000] + f"\n...[truncated, total {len(content)} chars]"
        return content
    except FileNotFoundError:
        return f"Error: File not found: {filepath}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


def tool_list_directory(user_id: int, dirpath: str = "") -> str:
    ws = get_workspace(user_id)
    target = ws / dirpath if dirpath else ws
    try:
        items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        if not items:
            return "Directory is empty"
        lines = []
        for item in items:
            if item.is_dir():
                lines.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                lines.append(f"📄 {item.name} ({size} bytes)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"


def tool_install_package(package: str) -> str:
    try:
        result = subprocess.run(
            ["pip", "install", package, "-q"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return f"Successfully installed: {package}"
        else:
            return f"Install failed:\n{result.stderr}"
    except Exception as e:
        return f"Error: {str(e)}"


def tool_run_python_file(user_id: int, filepath: str, args: str = "") -> str:
    ws = get_workspace(user_id)
    safe_path = ws / Path(filepath).name if "/" not in filepath else ws / filepath.lstrip("/")
    if not safe_path.exists():
        return f"Error: File not found: {filepath}"
    try:
        cmd = f"python3 {safe_path} {args}".strip()
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=str(ws)
        )
        output = result.stdout or ""
        error = result.stderr or ""
        response = f"Exit code: {result.returncode}\n"
        if output:
            response += f"Output:\n{output}"
        if error:
            response += f"Error:\n{error}"
        return response.strip() or "Ran successfully (no output)"
    except subprocess.TimeoutExpired:
        return "Error: Execution timed out (30s)"
    except Exception as e:
        return f"Error: {str(e)}"


def tool_create_project(user_id: int, project_type: str, project_name: str) -> str:
    ws = get_workspace(user_id)
    proj_dir = ws / project_name
    if proj_dir.exists():
        return f"Error: Project '{project_name}' already exists"
    proj_dir.mkdir(parents=True)

    templates = {
        "python-basic": {
            "main.py": '# Python Project: ' + project_name + '\n\ndef main():\n    print("Hello from ' + project_name + '!")\n\nif __name__ == "__main__":\n    main()\n',
            "requirements.txt": "# Add your dependencies here\n",
            "README.md": f"# {project_name}\n\nA Python project.\n\n## Run\n```bash\npython main.py\n```\n"
        },
        "flask-app": {
            "app.py": 'from flask import Flask, jsonify\n\napp = Flask(__name__)\n\n@app.route("/")\ndef home():\n    return jsonify({"message": "Hello from ' + project_name + '!", "status": "ok"})\n\n@app.route("/api/hello")\ndef hello():\n    return jsonify({"greeting": "Hello, World!"})\n\nif __name__ == "__main__":\n    app.run(debug=True, port=5000)\n',
            "requirements.txt": "flask\n",
            "README.md": f"# {project_name} - Flask App\n\n## Setup\n```bash\npip install -r requirements.txt\npython app.py\n```\n"
        },
        "fastapi-app": {
            "main.py": 'from fastapi import FastAPI\nfrom pydantic import BaseModel\n\napp = FastAPI(title="' + project_name + '")\n\n@app.get("/")\ndef root():\n    return {"message": "Hello from ' + project_name + '"}\n\n@app.get("/items/{item_id}")\ndef get_item(item_id: int):\n    return {"item_id": item_id, "name": f"Item {item_id}"}\n',
            "requirements.txt": "fastapi\nuvicorn\n",
            "README.md": f"# {project_name} - FastAPI App\n\n## Run\n```bash\npip install -r requirements.txt\nuvicorn main:app --reload\n```\n"
        },
        "html-app": {
            "index.html": f'<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <title>{project_name}</title>\n  <style>\n    body {{ font-family: sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}\n    h1 {{ color: #333; }}\n  </style>\n</head>\n<body>\n  <h1>Welcome to {project_name}</h1>\n  <p>Your web app is ready!</p>\n  <script src="app.js"></script>\n</body>\n</html>\n',
            "app.js": f"// {project_name} - JavaScript\nconsole.log('App loaded!');\n",
            "style.css": "/* Styles */\nbody { margin: 0; padding: 0; }\n",
            "README.md": f"# {project_name} - HTML App\n\nOpen `index.html` in a browser.\n"
        },
        "node-app": {
            "index.js": f'const http = require("http");\n\nconst PORT = 3000;\n\nconst server = http.createServer((req, res) => {{\n  res.writeHead(200, {{"Content-Type": "application/json"}});\n  res.end(JSON.stringify({{ message: "Hello from {project_name}!" }}));\n}});\n\nserver.listen(PORT, () => {{\n  console.log(`Server running on port ${{PORT}}`);\n}});\n',
            "package.json": json.dumps({"name": project_name, "version": "1.0.0", "main": "index.js", "scripts": {"start": "node index.js"}}, indent=2),
            "README.md": f"# {project_name} - Node App\n\n## Run\n```bash\nnode index.js\n```\n"
        }
    }

    template = templates.get(project_type)
    if not template:
        shutil.rmtree(proj_dir)
        return f"Unknown project type: {project_type}. Available: python-basic, flask-app, fastapi-app, html-app, node-app"

    for filename, content in template.items():
        (proj_dir / filename).write_text(content, encoding="utf-8")

    files_created = list(template.keys())
    return f"Project '{project_name}' created!\nType: {project_type}\nFiles: {', '.join(files_created)}\nLocation: {project_name}/"


def tool_delete_file(user_id: int, filepath: str) -> str:
    ws = get_workspace(user_id)
    safe_path = ws / Path(filepath).name if "/" not in filepath else ws / filepath.lstrip("/")
    try:
        if safe_path.is_dir():
            shutil.rmtree(safe_path)
            return f"Deleted folder: {filepath}"
        elif safe_path.exists():
            safe_path.unlink()
            return f"Deleted file: {filepath}"
        else:
            return f"Not found: {filepath}"
    except Exception as e:
        return f"Error: {str(e)}"


def execute_tool(user_id: int, tool_name: str, args: dict) -> str:
    """Dispatch tool call"""
    try:
        if tool_name == "execute_command":
            return tool_execute_command(user_id, args["command"], args.get("working_dir"))
        elif tool_name == "write_file":
            return tool_write_file(user_id, args["filepath"], args["content"])
        elif tool_name == "read_file":
            return tool_read_file(user_id, args["filepath"])
        elif tool_name == "list_directory":
            return tool_list_directory(user_id, args.get("dirpath", ""))
        elif tool_name == "install_package":
            return tool_install_package(args["package"])
        elif tool_name == "run_python_file":
            return tool_run_python_file(user_id, args["filepath"], args.get("args", ""))
        elif tool_name == "create_project":
            return tool_create_project(user_id, args["project_type"], args["project_name"])
        elif tool_name == "delete_file":
            return tool_delete_file(user_id, args["filepath"])
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        return f"Tool error: {str(e)}"


# ============================================================
# MODEL FALLBACK LIST  (tried in order when rate-limited)
# ============================================================
MODELS = [
    "llama-3.3-70b-versatile",   # primary — best quality
    "llama-3.1-8b-instant",      # fallback 1 — separate daily quota
    "llama3-8b-8192",            # fallback 2 — older llama3, separate quota
    "llama-3.2-3b-preview",      # fallback 3 — lightweight
]

def parse_retry_after(err_str: str) -> str:
    """Extract human-readable wait time from Groq 429 error string."""
    import re as _re
    # e.g. "Please try again in 30m56.735999999s"
    m = _re.search(r"try again in ([^\.'\"]+)", err_str)
    if m:
        raw = m.group(1).strip()
        # convert "30m56s" → "၃၀ မိနစ် ၅၆ စက္ကန့်"
        parts = []
        mins = _re.search(r"(\d+)m", raw)
        secs = _re.search(r"(\d+(?:\.\d+)?)s", raw)
        if mins:
            parts.append(f"{mins.group(1)} မိနစ်")
        if secs:
            parts.append(f"{int(float(secs.group(1)))} စက္ကန့်")
        return " ".join(parts) if parts else raw
    return ""


# ============================================================
# AI AGENT RUNNER (with tool calling loop + model fallback)
# ============================================================
async def run_agent(user_id: int, user_message: str) -> str:
    if user_id not in user_history:
        user_history[user_id] = []

    user_history[user_id].append({"role": "user", "content": user_message})
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    mode_key = user_modes.get(user_id, "general")
    extra = MODE_EXTRA.get(mode_key, "")
    system = SYSTEM_PROMPT + (f"\n\n**လက်ရှိ Mode:** {mode_key}\n{extra}" if extra else "")
    messages = [{"role": "system", "content": system}] + user_history[user_id]

    max_iterations = 6

    for iteration in range(max_iterations):
        # --- try each model in fallback order ---
        response = None
        used_model = None
        last_err = None

        for model in MODELS:
            try:
                response = groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=4096,
                    temperature=0.5,
                )
                used_model = model
                break  # success — stop trying fallbacks
            except Exception as e:
                err_str = str(e)
                last_err = err_str
                if (
                    "429" in err_str
                    or "ratelimit" in err_str.lower()
                    or "rate_limit" in err_str.lower()
                    or "model_decommissioned" in err_str.lower()
                    or "decommissioned" in err_str.lower()
                ):
                    # rate-limited or deprecated model → skip, try next
                    continue
                else:
                    # non-rate-limit error — fail immediately
                    return _fmt_api_error(err_str)

        if response is None:
            # All models rate-limited
            wait = parse_retry_after(last_err or "")
            wait_msg = f" ({wait} နောက်မှ ထပ်ကြိုးစားပါ)" if wait else " နောက်မှ ထပ်ကြိုးစားပါ"
            return (
                "⏳ **Token limit ထိနေပါပြီ**\n\n"
                "Groq free tier ၏ နေ့စဉ် token အကန့်အသတ် (100,0000) ထိနေပါသည်။\n"
                f"🕐{wait_msg}\n\n"
                "**အခြားနည်းလမ်းများ:**\n"
                "• https://console.groq.com → Dev Tier upgrade\n"
                "• သို့မဟုတ် မနက်ဖြန် (UTC 00:00 မှာ reset ဖြစ်) ထပ်သုံးပါ\n"
                "• /clear ဆိုပြီး history ရှင်းပြီး တိုတောင်းသော message နှင့် ထပ်ကြိုးစားပါ"
            )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # Prefix model name note if fell back
        model_note = f"\n\n_(⚡ {used_model})_" if used_model != MODELS[0] else ""

        # Add assistant message to context
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            **({"tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in msg.tool_calls
            ]} if msg.tool_calls else {})
        })

        if finish_reason == "stop" or not msg.tool_calls:
            final = (msg.content or "") + model_note
            user_history[user_id].append({"role": "assistant", "content": msg.content or ""})
            return final

        # Execute tool calls
        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except Exception:
                func_args = {}

            result = execute_tool(user_id, func_name, func_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result
            })

    return "⚠️ Agent max iterations ထိသွားပါပြီ။ တိုတောင်းသော request တစ်ခု ထပ်ကြိုးစားပါ။"


def _fmt_api_error(err_str: str) -> str:
    """Format unexpected API errors in Myanmar."""
    if "401" in err_str or "invalid_api_key" in err_str.lower():
        return "❌ **API Key မမှန်ပါ**\n\nGROQ_API_KEY ကို စစ်ဆေးပါ။"
    if "503" in err_str or "unavailable" in err_str.lower():
        return "❌ **Groq server ယာယီပိတ်နေပါသည်**\n\nခဏနောက်မှ ထပ်ကြိုးစားပါ။"
    return f"❌ **API Error**\n\n{err_str[:300]}"


# ============================================================
# KEYBOARDS
# ============================================================
main_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("🤖 Agent Mode"), KeyboardButton("💻 Code Run")],
    [KeyboardButton("📁 Files"), KeyboardButton("🏗️ Build App")],
    [KeyboardButton("📦 Install Package"), KeyboardButton("❓ Help")],
], resize_keyboard=True)


# ============================================================
# COMMAND HANDLERS
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_history[user_id] = []
    ws = get_workspace(user_id)

    welcome_msg = f"""🤖 **Re-AI Agent မှ ကြိုဆိုပါသည်၊ {user.first_name}!**

ကျွန်ုပ်သည် text-based chatbot တစ်ခုမဟုတ်ပါ။ ကျွန်ုပ်သည် **AI Agent** ဖြစ်ပြီး:

⚡ **ကျွန်ုပ်ပြုလုပ်နိုင်သည်:**
- 🖥️ Shell commands execute လုပ်နိုင်
- 📝 Files ရေး/ဖတ်/ဖျက်နိုင်
- 🐍 Python files run နိုင်
- 📦 Packages install နိုင်
- 🏗️ Apps (Flask, FastAPI, HTML) build လုပ်နိုင်
- 🔍 Code debug နိုင်

📂 **သင်၏ workspace:** `/tmp/agent_workspace/{user_id}/`

**ဥပမာ commands:**
- "hello.py ဆိုတဲ့ file ရေးပြီး run ပေးပါ"
- "flask app တစ်ခု build ပေးပါ"
- "requests package install လုပ်ပေးပါ"
- "ls command run ပေးပါ"

**Bot Commands:**
- /start - ကြိုဆိုစာ
- /clear - History ရှင်းပါ
- /workspace - Workspace files ကြည့်
- /help - အကူအညီ

💬 မြန်မာဘာသာဖြင့် မေးနိုင်ပါသည်!
"""
    await update.message.reply_text(welcome_msg, reply_markup=main_keyboard, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """📖 **Re-AI Agent - အကူအညီ**

🔧 **Agent ပြုလုပ်နိုင်သည်:**
- Shell command run ခြင်း
- Python files ရေးပြီး run ခြင်း
- Flask/FastAPI/HTML apps build ခြင်း
- Package install ခြင်း
- Files ဖတ်/ရေး/ဖျက်ခြင်း

💬 **ဥပမာ မေးခွန်းများ:**
- "Python file တစ်ခု ရေးပြီး run ပေးပါ"
- "Flask app တစ်ခု create လုပ်ပေးပါ"
- "fastapi package install လုပ်ပေးပါ"
- "workspace ထဲ ဘာ files ရှိလဲ ကြည့်ပေးပါ"
- "hello world Python code ရေးပြီး run ကြည့်ပေးပါ"

⌨️ **Commands:**
- /start — ကြိုဆိုစာ
- /clear — Conversation ရှင်းပါ
- /workspace — Files ကြည့်
- /status — API status စစ်

🌐 **Language:** မြန်မာဘာသာ (အမြဲ)
"""
    await update.message.reply_text(help_text, reply_markup=main_keyboard, parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_history[user_id] = []
    await update.message.reply_text("✅ Conversation history ရှင်းပြီးပါပြီ! အသစ်စတင်နိုင်ပါပြီ။", reply_markup=main_keyboard)


async def workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ws = get_workspace(user_id)
    files = tool_list_directory(user_id)
    msg = f"📂 **သင်၏ Workspace ထဲ files:**\n\n{files}"
    await update.message.reply_text(msg, reply_markup=main_keyboard, parse_mode="Markdown")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args  # e.g. /mode 3

    if args and args[0] in MODES:
        key, label, desc = MODES[args[0]]
        user_modes[user_id] = key
        await update.message.reply_text(
            f"✅ Mode ပြောင်းပြီးပါပြီ!\n\n**{label}** — {desc}",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
        return

    # Show mode list
    current_key = user_modes.get(user_id, "general")
    current_label = next((v[1] for v in MODES.values() if v[0] == current_key), "General")

    lines = [f"🎯 **AI Mode ရွေးချယ်ပါ**\n", f"လက်ရှိ mode: **{current_label}**\n"]
    for num, (key, label, desc) in MODES.items():
        marker = "✅" if key == current_key else "  "
        lines.append(f"{marker} `{num}` — {label}: {desc}")
    lines.append("\n**ပြောင်းနည်း:** `/mode 2` ဟု ရိုက်ပါ")

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Say 'online' in Myanmar"}],
            max_tokens=10
        )
        await update.message.reply_text(
            f"✅ **System Status: ONLINE**\n\n"
            f"🤖 Model: llama-3.3-70b-versatile\n"
            f"🔧 Tools: {len(TOOLS)} tools enabled\n"
            f"⚡ Rate: 8000 tokens/min\n"
            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=main_keyboard)


# ============================================================
# MESSAGE HANDLER
# ============================================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # Quick action button mappings
    quick_actions = {
        "🤖 Agent Mode": "သင်သည် AI Agent mode ရောက်ပါပြီ။ Commands, files, apps - ဘာမဆို ကူညီနိုင်ပါသည်။ ဘာလိုချင်သလဲ?",
        "💻 Code Run": "Python code တစ်ခု ရေးပြီး run ပေးပါ ဟုပြောပါ သို့မဟုတ် code snippet တစ်ခု ပေးပါ — run ကြည့်ပေးမည်။",
        "📁 Files": "File operations (ရေး/ဖတ်/ဖျက်/list) လုပ်ချင်ပါသလား? ဘာ file operation လုပ်ချင်လဲ?",
        "🏗️ Build App": "Flask app, FastAPI app, HTML app, Python basic project — ဘယ် project type build လုပ်ချင်လဲ? Project name ပါ ပြောပါ။",
        "📦 Install Package": "ဘယ် Python package install လုပ်ချင်လဲ? Package name ပြောပါ (ဥပမာ: requests, flask, numpy)。",
        "❓ Help": None,  # Use help command
    }

    if text in quick_actions:
        if text == "❓ Help":
            await help_command(update, context)
            return
        prompt_msg = quick_actions[text]
        await update.message.reply_text(f"✅ {prompt_msg}", reply_markup=main_keyboard)
        return

    # Send thinking indicator
    thinking_msg = await update.message.reply_text("🤔 Agent processing...", reply_markup=main_keyboard)

    try:
        ai_response = await run_agent(user_id, text)
    except Exception as e:
        ai_response = f"⚠️ Error: {str(e)}"

    # Delete thinking message
    try:
        await thinking_msg.delete()
    except Exception:
        pass

    await send_reply(update, ai_response, main_keyboard)


# ============================================================
# HELPER: send long reply safely
# ============================================================
async def send_reply(update: Update, text: str, keyboard):
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            try:
                await update.message.reply_text(part, reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(part, reply_markup=keyboard)
            await asyncio.sleep(0.3)
    else:
        try:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(text, reply_markup=keyboard)


# ============================================================
# TEXT FILE EXTENSIONS (readable as text)
# ============================================================
TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css", ".json", ".yaml", ".yml", ".toml",
    ".csv", ".xml", ".sh", ".bash", ".env", ".cfg",
    ".ini", ".sql", ".rs", ".go", ".java", ".c", ".cpp",
    ".h", ".php", ".rb", ".kt", ".swift", ".dart", ".r",
    ".log", ".conf", ".dockerfile", ".gitignore",
}

# ============================================================
# DOCUMENT / FILE UPLOAD HANDLER
# ============================================================
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ws = get_workspace(user_id)
    doc = update.message.document
    caption = update.message.caption or ""

    # Notify user we're downloading
    thinking_msg = await update.message.reply_text(
        f"📥 File download လုပ်နေသည်: `{doc.file_name}`...",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )

    try:
        # Download file to workspace
        tg_file = await context.bot.get_file(doc.file_id)
        save_path = ws / doc.file_name
        await tg_file.download_to_drive(str(save_path))

        file_size = save_path.stat().st_size
        ext = Path(doc.file_name).suffix.lower()

        # Build context message for AI
        file_info = (
            f"User သည် '{doc.file_name}' ({file_size} bytes) ဟူသော file တစ်ခု upload လုပ်ခဲ့သည်။\n"
            f"File ကို workspace ထဲ save လုပ်ပြီးပါပြီ: {doc.file_name}\n"
        )

        # If text-readable, include content
        if ext in TEXT_EXTENSIONS and file_size < 50_000:
            try:
                content = save_path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 4000:
                    content = content[:4000] + f"\n...[truncated — {len(content)} chars total]"
                file_info += f"\nFile content:\n```\n{content}\n```\n"
            except Exception as e:
                file_info += f"\n(File ဖတ်၍မရပါ: {e})\n"
        elif file_size >= 50_000:
            file_info += f"\n(File ကြီးလွန်းသောကြောင့် content မဖတ်ပါ — workspace ထဲ save ပြီး)\n"
        else:
            file_info += f"\n(Binary file — workspace ထဲ save ပြီး, run/process နိုင်ပါသည်)\n"

        # Add caption if user wrote one
        if caption:
            file_info += f"\nUser ၏ instruction: {caption}"
        else:
            file_info += "\nUser ၏ instruction: ဤ file ကို ဘာလုပ်ရမည်ကို Agent ဆုံးဖြတ်ပါ (content ကြည့်ပေးပါ သို့မဟုတ် သင့်တော်သည့် action တစ်ခု propose လုပ်ပါ)။"

        await thinking_msg.delete()

        thinking2 = await update.message.reply_text("🤔 Agent processing...", reply_markup=main_keyboard)
        ai_response = await run_agent(user_id, file_info)
        await thinking2.delete()

        await send_reply(update, ai_response, main_keyboard)

    except Exception as e:
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ File download မအောင်မြင်ပါ: {str(e)}",
            reply_markup=main_keyboard
        )


# ============================================================
# PHOTO UPLOAD HANDLER
# ============================================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ws = get_workspace(user_id)
    caption = update.message.caption or ""

    thinking_msg = await update.message.reply_text(
        "📥 Photo download လုပ်နေသည်...",
        reply_markup=main_keyboard
    )

    try:
        # Get best quality photo
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)

        filename = f"photo_{photo.file_unique_id}.jpg"
        save_path = ws / filename
        await tg_file.download_to_drive(str(save_path))

        file_size = save_path.stat().st_size

        file_info = (
            f"User သည် photo တစ်ပုံ upload လုပ်ခဲ့သည်။\n"
            f"Save path: {filename} ({file_size} bytes)\n"
            f"Workspace ထဲ save ပြီးပါပြီ။\n"
        )

        if caption:
            file_info += f"\nUser ၏ instruction: {caption}"
        else:
            file_info += (
                "\nNote: ဤ model သည် image ကြည့်နိုင်ခြင်းမရှိပါ (vision မပါ)။ "
                "Photo ကို workspace ထဲ save ပြီးပါပြီ။ "
                "User ကို photo save ပြီးကြောင်းနှင့် filename ပြောပြပါ။ "
                "Image processing လိုပါက instruction ထပ်ပေးရန် ပြောပါ။"
            )

        await thinking_msg.delete()

        thinking2 = await update.message.reply_text("🤔 Agent processing...", reply_markup=main_keyboard)
        ai_response = await run_agent(user_id, file_info)
        await thinking2.delete()

        await send_reply(update, ai_response, main_keyboard)

    except Exception as e:
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ Photo download မအောင်မြင်ပါ: {str(e)}",
            reply_markup=main_keyboard
        )


# ============================================================
# MAIN
# ============================================================
def main():
    print("🚀 Re-AI Agent (Upgraded) စတင်နေပါသည်...")
    print(f"🤖 Model: llama-3.3-70b-versatile + Function Calling")
    print(f"🔧 Tools: {len(TOOLS)} agent tools enabled")
    print(f"📁 Workspace: {WORKSPACE_BASE}")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("workspace", workspace_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("mode", mode_command))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("✅ Bot running! Messages + Files အတွက် စောင့်နေပါသည်...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
