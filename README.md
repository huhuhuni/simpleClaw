# SimpleClaw Agent

基于火山方舟 SDK 的 Web Agent 对话工具。AI 可以自主执行终端命令来完成你的任务，通过技能系统动态扩展能力，并具备长期记忆。

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

## 核心功能

### Agent 循环

AI 通过以下指令自主完成任务：

| 指令 | 说明 |
|------|------|
| `命令：XXX` | 执行终端命令，结果自动回传 |
| `技能：XXX` | 激活指定技能，加载详细指引 |
| `回忆：YYYY-MM-DD` | 加载指定日期的流水记忆 |
| `完成：XXX` | 任务结束，输出总结 |

### 记忆系统

对话上下文保留最近 10 轮，重要信息通过记忆系统持久化。

- **核心记忆**（`memory/core.md`）：长期有效的重要信息，每次对话自动加载到 system prompt
- **流水记忆**（`memory/daily/YYYY-MM-DD.md`）：按日期归档的任务记录，AI 按需回忆

**工作流程：**

1. 每次对话自动注入核心记忆 + 流水记忆日期索引
2. AI 可回复 `回忆：2026-04-05` 加载指定日期的详细记录
3. 任务完成后，模型自动归纳总结：
   - 流水记忆 → 追加到当天的日期文件
   - 核心记忆 → 如有长期重要信息或用户明确要求，追加到 `core.md`

### 技能系统

技能按需加载——system prompt 仅包含技能目录（名称 + 描述），AI 判断需要时才激活并加载完整指引。

**SKILL.md 格式：**

```markdown
---
name: 技能名称
description: 一句话描述，让 AI 知道何时触发
version: 1.0.0
---

# 技能标题

## 概述
解决什么问题

## 使用说明
具体操作步骤
```

**安装技能：**

- **Web 上传**：侧边栏拖放或选择 `.zip` 压缩包（内含 `SKILL.md`）
- **手动放置**：将技能文件夹放入 `skills/` 目录，重启生效

**删除技能：** 侧边栏技能列表点击 ✕ 按钮。

## 项目结构

```
simpleClaw/
├── app.py                # Flask 后端
├── templates/
│   └── index.html        # Web 前端
├── skills/               # 技能目录
│   ├── git-helper/
│   │   └── SKILL.md
│   ├── file-manager/
│   │   └── SKILL.md
│   └── _template/        # 新建技能的参考模板
├── memory/               # 记忆目录
│   ├── core.md           # 核心记忆（长期）
│   └── daily/            # 流水记忆（按日期）
│       └── 2026-04-05.md
├── .env                  # 本地配置（不提交到 Git）
├── .env.example          # 配置模板
├── requirements.txt      # pip 依赖
├── pyproject.toml        # 项目元数据
└── .gitignore
```
