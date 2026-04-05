import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import date
import yaml
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")
MEMORY_CORE = os.path.join(MEMORY_DIR, "core.md")
MEMORY_DAILY_DIR = os.path.join(MEMORY_DIR, "daily")

BASE_PROMPT = """
你的目标是完成用户的任务，你必须选择下面的其中一种格式进行回复：
1. 如果你认为需要回忆某天的记录来辅助任务，则输出'回忆：YYYY-MM-DD'
2. 如果你认为需要激活某个技能来辅助完成任务，则输出'技能：XXX'，XXX 为技能名称
3. 如果你认为需要执行命令，则输出'命令：XXX'，XXX 为命令本身，不要用任何的格式，不要解释
4. 如果你认为不需要执行命令，则输出'完成：XXX'，XXX 为你的总结信息

注意：
- 每次只能选择一种格式回复
- 激活技能后你会收到该技能的详细指引，然后再继续处理任务
- 你可以查看可用的流水记忆日期列表来决定是否需要回忆
""".strip()

MEMORY_SUMMARIZE_PROMPT = """请根据以下对话内容进行归纳总结，输出两部分：

1. **流水记忆**：简洁记录本次任务的关键信息（做了什么、结果如何），1-3 句话
2. **核心记忆**：如果对话中包含需要长期记住的重要信息（如用户偏好、项目配置、关键决策、用户明确要求记住的内容），则输出需要追加的内容；如果没有，输出"无"

请严格使用以下格式：
流水记忆：<内容>
核心记忆：<内容或"无">
""".strip()


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)

# ── 记忆系统 ──

def read_core_memory():
    if os.path.isfile(MEMORY_CORE):
        with open(MEMORY_CORE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def append_core_memory(content):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(MEMORY_CORE, "a", encoding="utf-8") as f:
        f.write(f"\n- {content}\n")


def read_daily_memory(day):
    """读取指定日期的流水记忆，day 格式 YYYY-MM-DD"""
    path = os.path.join(MEMORY_DAILY_DIR, f"{day}.md")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def append_daily_memory(day, content):
    os.makedirs(MEMORY_DAILY_DIR, exist_ok=True)
    path = os.path.join(MEMORY_DAILY_DIR, f"{day}.md")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n- {content}\n")


def list_daily_memory_dates():
    """返回所有有流水记忆的日期列表"""
    if not os.path.isdir(MEMORY_DAILY_DIR):
        return []
    dates = []
    for f in sorted(os.listdir(MEMORY_DAILY_DIR), reverse=True):
        if f.endswith(".md"):
            dates.append(f.replace(".md", ""))
    return dates


def parse_skill_md(path):
    """解析 SKILL.md：YAML frontmatter → meta，剩余 Markdown → content"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta = yaml.safe_load(m.group(1))
    if not meta or not meta.get("name"):
        return None
    meta["content"] = m.group(2).strip()
    return meta


def load_skills():
    """扫描 skills/ 下所有子目录的 SKILL.md（跳过 _ 开头的目录）"""
    skills = []
    if not os.path.isdir(SKILLS_DIR):
        return skills
    for entry in sorted(os.listdir(SKILLS_DIR)):
        if entry.startswith("_"):
            continue
        skill_file = os.path.join(SKILLS_DIR, entry, "SKILL.md")
        if not os.path.isfile(skill_file):
            continue
        try:
            skill = parse_skill_md(skill_file)
            if skill:
                skill["dir"] = entry
                skills.append(skill)
        except Exception:
            continue
    return skills


def build_system_prompt():
    parts = [BASE_PROMPT]

    # 注入核心记忆
    core = read_core_memory()
    if core:
        parts.append(f"\n\n## 你的核心记忆（长期有效）\n{core}")

    # 注入流水记忆日期索引
    dates = list_daily_memory_dates()
    if dates:
        today = date.today().isoformat()
        parts.append(f"\n\n## 可用的流水记忆\n当前日期：{today}\n可回忆日期：{', '.join(dates[:30])}")

    # 注入技能目录
    skills = load_skills()
    if skills:
        parts.append("\n\n## 可用技能（回复'技能：名称'来激活）")
        for s in skills:
            parts.append(f"- {s['name']}：{s.get('description', '')}")

    return "\n".join(parts)


def find_skill_by_name(name):
    """根据名称查找 skill，返回包含完整 content 的 dict"""
    for s in load_skills():
        if s["name"] == name:
            return s
    return None

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

@app.route("/api/skills", methods=["GET"])
def list_skills():
    skills = load_skills()
    return jsonify([{
        "name": s["name"],
        "description": s.get("description", ""),
        "version": s.get("version", ""),
        "dir": s["dir"],
    } for s in skills])


@app.route("/api/skills/upload", methods=["POST"])
def upload_skill():
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({"error": "只支持 .zip 格式"}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        f.save(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                # 找到 SKILL.md 所在的顶层目录
                skill_md_paths = [n for n in names if n.endswith("SKILL.md")]
                if not skill_md_paths:
                    return jsonify({"error": "ZIP 中未找到 SKILL.md 文件"}), 400

                skill_md_path = min(skill_md_paths, key=lambda x: x.count("/"))

                # 验证 SKILL.md 能正确解析
                with zf.open(skill_md_path) as mf:
                    content = mf.read().decode("utf-8")
                m = FRONTMATTER_RE.match(content)
                if not m:
                    return jsonify({"error": "SKILL.md 格式错误：缺少 YAML frontmatter"}), 400
                meta = yaml.safe_load(m.group(1))
                if not meta or not meta.get("name"):
                    return jsonify({"error": "SKILL.md 缺少 name 字段"}), 400

                # 确定目录名：使用 ZIP 内的顶层文件夹名，或根据 skill name 生成
                parts = skill_md_path.split("/")
                if len(parts) > 1:
                    dir_name = parts[0]
                else:
                    dir_name = re.sub(r"[^\w\-]", "-", meta["name"].lower()).strip("-")

                if dir_name.startswith("_"):
                    dir_name = dir_name.lstrip("_")

                # 解压到临时目录先
                extract_dir = os.path.join(tmpdir, "extracted")
                zf.extractall(extract_dir)

            # 找到实际的 skill 根目录
            if len(parts) > 1:
                src = os.path.join(extract_dir, dir_name)
            else:
                src = extract_dir

            dest = os.path.join(SKILLS_DIR, dir_name)

            # 如果已存在同名目录，先删除（覆盖安装）
            if os.path.exists(dest):
                shutil.rmtree(dest)

            shutil.copytree(src, dest)

        except zipfile.BadZipFile:
            return jsonify({"error": "无效的 ZIP 文件"}), 400

    skill = parse_skill_md(os.path.join(dest, "SKILL.md"))
    return jsonify({
        "ok": True,
        "skill": {
            "name": skill["name"],
            "description": skill.get("description", ""),
            "dir": dir_name,
        }
    })


@app.route("/api/skills/delete", methods=["POST"])
def delete_skill():
    data = request.json
    dir_name = data.get("dir", "")

    if not dir_name or dir_name.startswith("_"):
        return jsonify({"error": "无效的技能目录"}), 400

    # 防止路径穿越
    if "/" in dir_name or "\\" in dir_name or ".." in dir_name:
        return jsonify({"error": "非法路径"}), 400

    target = os.path.join(SKILLS_DIR, dir_name)
    if not os.path.isdir(target):
        return jsonify({"error": "技能不存在"}), 404

    shutil.rmtree(target)
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

    MAX_HISTORY = 20  # 保留最近 10 轮（每轮 user + assistant = 2 条）

    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(history[-MAX_HISTORY:])
    messages.append({"role": "user", "content": user_input})

    events = []

    max_rounds = 20
    task_done = False

    try:
        for _ in range(max_rounds):
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
                task_done = True
                break

            elif stripped.startswith("回忆：") or stripped.startswith("回忆:"):
                day = (stripped.split("回忆：", 1)[-1] if "回忆：" in stripped else stripped.split("回忆:", 1)[-1]).strip()
                daily = read_daily_memory(day)
                if daily:
                    events.append({"type": "memory_recall", "content": f"回忆 {day} 的记录"})
                    messages.append({"role": "user", "content": f"以下是 {day} 的流水记忆：\n\n{daily}\n\n请继续处理用户的任务。"})
                else:
                    events.append({"type": "memory_empty", "content": f"{day} 没有记录"})
                    messages.append({"role": "user", "content": f"{day} 没有流水记忆，请继续处理任务。"})

            elif stripped.startswith("技能：") or stripped.startswith("技能:"):
                skill_name = (stripped.split("技能：", 1)[-1] if "技能：" in stripped else stripped.split("技能:", 1)[-1]).strip()
                skill = find_skill_by_name(skill_name)

                if skill and skill.get("content"):
                    events.append({"type": "skill", "content": reply, "skill": skill_name})
                    injection = f"已激活技能「{skill_name}」，以下是该技能的指引：\n\n{skill['content']}\n\n请根据以上指引继续处理用户的任务。"
                    messages.append({"role": "user", "content": injection})
                    events.append({"type": "skill_loaded", "content": f"已加载技能：{skill_name}"})
                else:
                    messages.append({"role": "user", "content": f"未找到名为「{skill_name}」的技能，请直接处理任务。"})
                    events.append({"type": "skill_not_found", "content": f"未找到技能：{skill_name}"})

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

    # 任务完成后，异步归纳记忆
    if task_done:
        try:
            memorize(client, config["model"], messages)
            events.append({"type": "memory_saved", "content": "记忆已更新"})
        except Exception:
            pass

    new_history = [m for m in messages if m["role"] != "system"][-MAX_HISTORY:]
    return jsonify({"events": events, "history": new_history})

def memorize(client, model, messages):
    """调用模型归纳对话，写入流水记忆，必要时写入核心记忆"""
    conversation = "\n".join(
        f"[{m['role']}] {m['content'][:500]}"
        for m in messages if m["role"] != "system"
    )
    # 限制总长度避免 token 过大
    if len(conversation) > 6000:
        conversation = conversation[:6000] + "\n...(截断)"

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": MEMORY_SUMMARIZE_PROMPT},
            {"role": "user", "content": conversation},
        ],
    )

    result = resp.choices[0].message.content.strip()
    today = date.today().isoformat()

    # 解析流水记忆
    daily_match = re.search(r"流水记忆[：:]\s*(.+?)(?=\n核心记忆|$)", result, re.DOTALL)
    if daily_match:
        daily_content = daily_match.group(1).strip()
        if daily_content:
            append_daily_memory(today, daily_content)

    # 解析核心记忆
    core_match = re.search(r"核心记忆[：:]\s*(.+)", result, re.DOTALL)
    if core_match:
        core_content = core_match.group(1).strip()
        if core_content and core_content != "无":
            append_core_memory(core_content)


@app.route("/api/memory", methods=["GET"])
def get_memory():
    core = read_core_memory()
    dates = list_daily_memory_dates()
    return jsonify({"core": core, "dates": dates})


@app.route("/api/memory/daily/<day>", methods=["GET"])
def get_daily_memory(day):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return jsonify({"error": "日期格式无效"}), 400
    content = read_daily_memory(day)
    return jsonify({"date": day, "content": content})


def main():
    app.run(debug=True, port=5001)

if __name__ == "__main__":
    main()
