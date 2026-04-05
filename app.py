import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import yaml
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")

BASE_PROMPT = """
你的目标是完成用户的任务，你必须选择下面的其中一种格式进行回复：
1. 如果你认为需要激活某个技能来辅助完成任务，则输出'技能：XXX'，XXX 为技能名称
2. 如果你认为需要执行命令，则输出'命令：XXX'，XXX 为命令本身，不要用任何的格式，不要解释
3. 如果你认为不需要执行命令，则输出'完成：XXX'，XXX 为你的总结信息

注意：
- 每次只能选择一种格式回复
- 激活技能后你会收到该技能的详细指引，然后再继续处理任务
""".strip()


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


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
    """base prompt + 技能目录（仅 name + description，不含详细内容）"""
    skills = load_skills()
    if not skills:
        return BASE_PROMPT

    catalog = [BASE_PROMPT, "\n\n你可以使用以下技能（回复'技能：名称'来激活）："]
    for s in skills:
        catalog.append(f"- {s['name']}：{s.get('description', '')}")
    return "\n".join(catalog)


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

    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    events = []

    max_rounds = 20

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
                break

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

    new_history = [m for m in messages if m["role"] != "system"]
    return jsonify({"events": events, "history": new_history})

def main():
    app.run(debug=True, port=5001)

if __name__ == "__main__":
    main()
