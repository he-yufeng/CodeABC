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
- **阅读地图** 不等 AI 返回，先告诉你从哪个文件开始、接着看什么
- **怎么跑起来** 一步步的操作指南
- **快捷提示** "如果你只想改配置，直接去 config.py"

### 悬停批注

点击任何文件进入代码视图。鼠标悬停在代码上，就能看到中文批注：

- **粒度细**：每 1-3 行一个批注，不是笼统地说"这一段在做什么"
- **说人话**：不用任何编程术语，用日常生活类比解释（比如 for 循环 = 点名）
- **有缓存**：批注会存在本地，再次查看同一个文件不用等

### 更干净的项目扫描

码上懂会在调用 LLM 前跳过构建产物、包缓存、压缩 bundle、生成出来的前端 chunk，以及仓库 `.gitignore` 已经忽略的路径。它也会跳过真实 `.env`、凭证 JSON、API key 笔记、私钥等敏感文件，但保留 `.env.example` 这种安全示例。这样项目说明书会聚焦源代码，不会被 `dist/`、`node_modules`、本地临时文件、一整行的压缩 JavaScript 或私人凭证干扰。

### 不等 AI，先找到入口

项目上传完成后，码上懂会先根据 README、程序入口、依赖清单、核心源码目录和测试，生成一条确定性的阅读路线。即使还没配置 API Key，也能立刻知道第一步该看哪里，不会面对几百个文件无从下手。

### 一眼看出核心模块

码上懂会从扫描到的文件里建一张轻量的导入关系图，按"被多少个文件引用"（fan-in）排序。被引用最多的文件，往往就是真正放核心逻辑的地方：公共工具、数据模型、核心服务。这些文件会和阅读地图并排显示成"核心模块"，并标出有多少个文件依赖它。它能解析 Python 导入（含相对导入和包导入）和 JavaScript/TypeScript 导入（相对路径，自动补全后缀和 index 文件），第三方库和标准库的导入会被忽略，因为它们指向的不是项目里的文件。和阅读地图一样，这步不调用 LLM，没配 API Key 也能用。

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
export OPENAI_API_KEY=<OPENAI_API_KEY>
# 或者用其他服务商：
# export ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY>
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

### 桌面端（Tauri）

同一套界面通过 [Tauri](https://tauri.app) 打包成原生桌面窗口——一层很薄的 Rust 外壳包住 Web 前端，没有 Electron 那么臃肿。而且开箱即用：应用把 FastAPI 后端作为 sidecar 一起打包、启动时自动拉起，不用手动起任何东西。构建需要先装好 [Rust 工具链](https://www.rust-lang.org/tools/install)。

```bash
# 1. 把后端打包成 sidecar 二进制（用只装了项目依赖的干净 venv + pyinstaller，
#    在臃肿环境里打包会产出超大文件）
pip install -e . pyinstaller
python scripts/build_desktop_sidecar.py

# 2. 构建桌面应用（会把这个 sidecar 一起打进去）
cd frontend
npm install
npm run tauri:build    # 安装包在 src-tauri/target/release/bundle/ 下
```

发布版应用启动时会在 127.0.0.1:8000 拉起后端、退出时关掉它。开发时自己起后端（`uvicorn backend.app:app --reload`）再用热重载窗口即可——`npm run tauri:dev` 不会启动 sidecar：

```bash
npm run tauri:dev
```

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
- [x] 术语词典（鼠标悬停关键词弹出解释）
- [x] 自然语言编辑（"把分析的股票从茅台换成比亚迪"）
- [x] 提问模式（选中代码随时问）
- [x] 英文界面
- [x] 测试覆盖地图（哪些文件有测试；未覆盖的核心文件按风险排序）
- [x] Git 历史洞察（变更热点、协同变更耦合、代码归属 / 知识孤岛）
- [x] 技术债地图（汇总代码里作者自留的 TODO/FIXME/HACK/XXX 标记，按文件排序）
- [x] 环境变量清单（项目读取的环境变量，区分必填与可选）
- [x] 入口点检测（程序从哪开始运行：`__main__` 脚本、声明的命令行命令、按惯例的入口文件）
- [x] 一键启动（`run.py` / `start.bat`：自动构建、起服务、打开应用）
- [x] 单进程服务（后端直接托管构建好的界面，一个地址搞定，无需另起开发服务器）
- [x] 桌面端（Tauri —— `npm run tauri:build` 把同一套界面包成原生窗口）

## 贡献

欢迎提 Issue 和 PR。项目处于早期开发阶段。

## 许可证

MIT
