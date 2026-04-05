import os
import subprocess
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

SYSTEM_PROMPT = """
你的目标是完成用户的任务，你必须选择下面的其中一种格式进行回复：
1. 如果你认为需要执行命令，则输出'命令：XXX'，XXX 为命令本身，不要用任何的格式，不要解释
2. 如果你认为不需要执行命令，则输出'完成：XXX'，XXX 为你的总结信息
""".strip()

def get_config():
    return {
        "api_key": session.get("api_key", os.getenv("ARK_API_KEY", "")),
        "base_url": session.get("base_url", os.getenv("ARK_BASE_URL", "")),
        "model": session.get("model", os.getenv("ARK_MODEL", "")),
    }

def create_client(config):
    return Ark(
        api_key=config["api_key"],
        timeout=1800,
        max_retries=2,
        base_url=config["base_url"],
    )

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET"])
def get_config_api():
    return jsonify(get_config())

@app.route("/api/config", methods=["POST"])
def save_config_api():
    data = request.json
    session["api_key"] = data.get("api_key", "")
    session["base_url"] = data.get("base_url", "")
    session["model"] = data.get("model", "")
    return jsonify({"ok": True})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")
    history = data.get("history", [])

    config = get_config()
    if not config["api_key"]:
        return jsonify({"error": "请先在设置中填写 API Key"}), 400

    client = create_client(config)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    events = []

    try:
        while True:
            response = client.chat.completions.create(
                model=config["model"],
                messages=messages,
            )

            reply = response.choices[0].message.content
            messages.append({"role": "assistant", "content": reply})

            stripped = reply.strip()

            if stripped.startswith("完成：") or stripped.startswith("完成:"):
                summary = stripped.split("完成：", 1)[-1] if "完成：" in stripped else stripped.split("完成:", 1)[-1]
                events.append({"type": "done", "content": reply, "summary": summary.strip()})
                break
            elif stripped.startswith("命令：") or stripped.startswith("命令:"):
                cmd = stripped.split("命令：", 1)[-1] if "命令：" in stripped else stripped.split("命令:", 1)[-1]
                command = cmd.strip()
                events.append({"type": "command", "content": reply, "command": command})

                try:
                    result = subprocess.run(
                        command, shell=True, capture_output=True, text=True, timeout=30
                    )
                    command_result = result.stdout + result.stderr
                except subprocess.TimeoutExpired:
                    command_result = "命令执行超时（30秒）"
                except Exception as e:
                    command_result = f"执行出错: {str(e)}"

                feedback = f"执行完毕 {command_result}"
                events.append({"type": "exec_result", "content": feedback})
                messages.append({"role": "user", "content": feedback})
            else:
                events.append({"type": "reply", "content": reply})
                break
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    new_history = [m for m in messages if m["role"] != "system"]
    return jsonify({"events": events, "history": new_history})

def main():
    app.run(debug=True, port=5001)

if __name__ == "__main__":
    main()
