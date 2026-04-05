# SimpleClaw Agent

基于火山方舟 SDK 的 Web Agent 对话工具。AI 可以自主执行终端命令来完成你的任务，并通过技能系统动态扩展能力。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的火山方舟 API Key：

```
ARK_API_KEY=你的API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=deepseek-v3-2-251201
```

> 也可以在 Web 界面的设置面板中直接修改。

### 3. 启动

```bash
python app.py
```

浏览器打开 http://127.0.0.1:5001

## 技能系统

SimpleClaw 支持通过技能（Skill）扩展 AI 的能力。技能按需加载——系统只将技能目录（名称 + 描述）告知 AI，AI 判断需要时才会激活并加载完整指引。

### 技能结构

每个技能是 `skills/` 下的一个文件夹：

```
skills/
├── git-helper/
│   ├── SKILL.md          # 核心文件（必需）
│   ├── scripts/          # 可执行脚本（可选）
│   ├── references/       # 参考文档（可选）
│   └── assets/           # 静态资源（可选）
└── _template/            # 模板（_ 开头自动跳过）
```

### SKILL.md 格式

使用 YAML frontmatter + Markdown 正文：

```markdown
---
name: 技能名称
description: 一句话描述，让 AI 知道何时触发
version: 1.0.0
---

# 技能名称

## 概述
解决什么问题

## 使用说明
具体操作步骤

## 示例
场景 → 处理方式
```

### 安装技能

**方式一：Web 上传**

在侧边栏底部的上传区域，拖放或选择 `.zip` 压缩包即可安装。ZIP 内需包含 `SKILL.md` 文件。

**方式二：手动放置**

将技能文件夹直接放入 `skills/` 目录，重启生效。

### 删除技能

在侧边栏的技能列表中点击 ✕ 按钮即可删除。

## 项目结构

```
simpleClaw/
├── app.py                # Flask 后端
├── templates/
│   └── index.html        # Web 前端
├── skills/               # 技能目录
│   ├── git-helper/
│   ├── file-manager/
│   └── _template/        # 新建技能的参考模板
├── .env                  # 本地配置（不提交到 Git）
├── .env.example          # 配置模板
├── requirements.txt      # pip 依赖
├── pyproject.toml        # 项目元数据
└── .gitignore
```
