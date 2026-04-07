# 码上懂 CodeABC

**不用学编程，也能读懂代码。** 一款面向零编程基础用户的 AI 代码阅读工具。

[English README](README.md)

Cursor/VS Code 是给程序员用的瑞士军刀，码上懂是给普通人用的放大镜 -- 让你像读文章一样读代码，像批注文章一样理解代码。

## 解决什么问题

越来越多非程序员需要和代码打交道：

| 你是谁 | 你的痛点 |
|--------|---------|
| 文科研究生 | 导师给了 Python 数据分析脚本，要改参数但看不懂代码 |
| 产品经理 | 想知道开发写了什么，但看代码像看天书 |
| 创业者 | 外包交付了代码，无法判断质量 |
| 数据分析师 | 同事给了个 Python 脚本让你跑，不知道从哪开始 |
| 编程入门者 | 在学 Python，但课程代码看不懂 |

**AI 已经能完美解释代码了，缺的是一款把这个能力包装成好用体验的产品。**

## 功能

### 项目说明书

拖入项目文件夹，或粘贴 GitHub 链接。码上懂自动扫描文件，生成一份大白话的"项目说明书"：

- **这个项目是什么？** 一句话概括，不用任何术语
- **文件指南** 每个文件用大白话解释作用，按重要性排序
- **怎么跑起来** 一步步的操作指南
- **快捷提示** "如果你只想改配置，直接去 config.py"

### 悬停批注

点击任何文件进入代码视图。鼠标悬停在代码上，就能看到中文批注：

- **粒度细**：每 1-3 行一个批注，不是笼统地说"这一段在做什么"
- **说人话**：不用任何编程术语，用日常生活类比解释（比如 for 循环 = 点名）
- **有缓存**：批注会存在本地，再次查看同一个文件不用等

## 技术栈

| 层 | 选择 | 理由 |
|---|------|------|
| 前端 | React 19 + Vite + TailwindCSS 4 | 快速开发，纯交互应用不需要 SSR |
| 代码高亮 | Shiki | VS Code 级别的语法高亮质量 |
| 状态管理 | Zustand | 轻量好用 |
| 后端 | FastAPI + uvicorn | 异步 Python，适合流式返回 LLM 结果 |
| LLM | litellm | 多模型支持（OpenAI、Claude、DeepSeek、Kimi 等） |
| 缓存 | SQLite | 简单够用 |

## 快速开始

### 前提条件

- Python 3.10+
- Node.js 18+
- 一个 LLM API Key（OpenAI、Claude、DeepSeek 或其他 litellm 支持的）

### 启动后端

```bash
cd CodeABC
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 设置 API Key
export OPENAI_API_KEY=sk-xxx
# 或者用其他服务商：
# export ANTHROPIC_API_KEY=sk-ant-xxx
# export DEEPSEEK_API_KEY=xxx

# 可选：修改默认模型
# export CODEABC_MODEL=deepseek/deepseek-chat

uvicorn backend.app:app --reload
```

### 启动前端

```bash
cd CodeABC/frontend
npm install
npm run dev
```

打开浏览器访问 http://localhost:5173

### 使用方式

1. **本地文件夹**：把项目文件夹拖到上传区域，或点击选择
2. **GitHub 仓库**：粘贴链接如 `https://github.com/user/repo`，点击"分析"
3. 浏览生成的项目说明书
4. 点击任何文件，鼠标悬停查看批注

### API Key 配置

码上懂支持两种模式：

- **免费模式**（默认）：每天 20 次调用
- **自带 Key 模式**：点击右上角齿轮图标，填入你自己的 API Key，无限使用。Key 只存在浏览器本地，不会上传。

## 路线图

- [x] 项目说明书生成
- [x] 悬停批注（优先支持 Python）
- [ ] 术语词典（鼠标悬停关键词弹出解释）
- [ ] 自然语言编辑（"把分析的股票从茅台换成比亚迪"）
- [ ] 提问模式（选中代码随时问）
- [ ] 英文界面
- [ ] 桌面端（Tauri）

## 贡献

欢迎提 Issue 和 PR。项目处于早期开发阶段。

## 许可证

MIT
