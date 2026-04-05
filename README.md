# SimpleClaw Agent

基于火山方舟 SDK 的 Web Agent 对话工具。AI 可以自主执行终端命令来完成你的任务。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制模板并填入你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```
ARK_API_KEY=你的火山方舟API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=deepseek-v3-2-251201
```

> 也可以在 Web 界面的设置面板中直接修改。

### 3. 启动

```bash
python app.py
```

浏览器打开 http://127.0.0.1:5001

## 项目结构

```
simpleClaw/
├── app.py              # Flask 后端
├── templates/
│   └── index.html      # Web 前端
├── .env                # 本地配置（不提交到 Git）
├── .env.example        # 配置模板
├── requirements.txt    # pip 依赖
├── pyproject.toml      # 项目元数据
└── .gitignore
```
