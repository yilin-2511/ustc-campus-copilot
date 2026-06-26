# 🎓 校园 Copilot — USTC Campus Copilot

> **面向科大新生的校园生活智能助手**  
> "一〇七杯" 智能体赛道参赛项目  
> **队伍**：CloseClaw | **成员**：张义临、钟华杰

---

## 项目简介

校园 Copilot 是一个 **Function-Calling 驱动的智能路由助手**，帮助 USTC 学生（尤其是大一新生）解决校园生活中遇到的各类问题。

核心理念：**做导航员，不做搬运工。**

- 科大有 44+ 个校园平台（教务系统、评课社区、图书馆、校医院……），但新生不知道哪个问题该去哪个平台
- Copilot 负责**理解用户意图 → 路由到正确的信息源 → 合成回答**
- 有现成平台的 → 引导到平台（附 URL + 使用技巧）
- 没有现成平台的 → 搜索南七茶馆论坛 RAG 知识库（学长学姐的真实经验）

---

## 当前进度

| 模块 | 状态 |
|------|------|
| 南七茶馆 RAG 知识库 | ✅ 1,215 条 Q&A（m3e-base + ChromaDB） |
| 校园平台路由数据 | ✅ 44 个平台（keywords + routeRules + tips） |
| Function-Calling Router | ✅ 3 tools + 多轮记忆 |
| 多智能体架构 | ⬜ 规划中 |
| 其他数据源接入 | ⬜ 待开发 |
| Web UI | ⬜ 未开始 |

---

## 快速开始

### 环境要求

- Python 3.10+（推荐用 venv 或 conda 创建虚拟环境，非必须）

### 1. 克隆并安装

```bash
git clone https://github.com/yilin-2511/ustc-campus-copilot.git
cd ustc-campus-copilot
python scripts/setup.py
```

`setup.py` 自动完成：安装依赖 → 下载 m3e-base 模型 → 构建 ChromaDB 向量库。

### 2. 启动 Agent

```powershell
# Windows PowerShell
$env:PYTHONIOENCODING="utf-8"
python scripts/router_agent.py
```

```bash
# Linux / macOS / Git Bash
PYTHONIOENCODING=utf-8 python scripts/router_agent.py
```

### 3. 首次配置

首次运行会提示配置 API Key，三个选项都可以自定义，直接回车使用默认值：

```
=======================================================
  首次配置 — 直接回车使用默认值
  API 申请: https://llm.ustc.edu.cn/llmService
=======================================================
  API Key: sk-xxxxxxxxxxxxx              ← 粘贴你的 Key（必填）
  API Base [https://api.llm.ustc.edu.cn/v1]:  ← 回车用科大网关
  Model [deepseek-v4-pro]:                ← 回车用默认模型
  Saved to .env
```

> API Key 在 https://llm.ustc.edu.cn/llmService 申请（校内访问）。  
> 配置自动保存到 `.env`，下次运行无需再输。

### 4. 可用模型

| 模型 | 特点 |
|------|------|
| `deepseek-v4-pro` | 默认，最稳定 |
| `deepseek-v4-flash-ascend` | 速度快 |
| `qwen3.6-chat` | 轻量 |
| `glm-5.2` | 智谱 |
| `qwen-reasoner` | 推理强 |
| `smart/reasoning` | 智能推理 |

### 5. 交互命令

| 输入 | 功能 |
|------|------|
| 直接输入问题 | 与 Agent 对话 |
| `q` / `exit` | 退出 |
| `/clear` | 清空对话历史 |
| `/history` | 查看对话历史 |

### 修改配置

编辑项目根目录的 `.env` 文件：

```env
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_API_BASE=https://api.llm.ustc.edu.cn/v1
ROUTER_MODEL=deepseek-v4-flash-ascend
```

也支持任何 OpenAI 兼容的 API（如 DeepSeek 官方、OpenAI）：

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_API_BASE=https://api.openai.com/v1
ROUTER_MODEL=gpt-4o
```

### 测试 RAG 检索（无需 LLM）

```bash
PYTHONIOENCODING=utf-8 python scripts/build_knowledge_base.py --query "保研需要什么条件"
```

### 常见问题

| 问题 | 解决 |
|------|------|
| `403 model access denied` | 模型名写错了，检查 `ROUTER_MODEL` 拼写 |
| `Loading weights` 出现 | 仅在进程启动后首次 RAG 查询时加载一次，之后复用 |
| `ModuleNotFoundError` | 重新运行 `python scripts/setup.py` 安装依赖 |
| API 超时 | 确认在科大校园网内访问 |

---

## 架构

```
用户提问
  │
  ▼
┌──────────────────────────────────┐
│     router_agent.py              │
│  Function-Calling Router         │
│                                  │
│  工具1: search_forum_knowledge   │──→ rag_tools.py ──→ ChromaDB (1,215条)
│  工具2: navigate_to_platform     │──→ platform_tools.py ──→ platform_routing.json (44平台)
│  工具3: search_course_info       │──→ catalog.ustc.edu.cn (开发中)
│                                  │
│  多轮记忆: conversation_memory.py │
└──────────────────────────────────┘
  │
  ▼
合成回答（附带平台链接 + 使用技巧 + 免责声明）
```

### 路由逻辑

| 用户意图 | 路由目标 | 示例 |
|---------|---------|------|
| 经验/评价类 | RAG 知识库 | "保研失败了怎么办"、"数分哪个老师好" |
| 办事/查询类 | 平台导航 | "怎么查成绩"、"教室设备坏了去哪里报修" |
| 常识类 | 直接回答 | "图书馆几点关门" |
| 非校园类 | 礼貌拒答 | "今天天气怎么样" |

---

## 项目结构

```
ustc-campus-copilot/
├── README.md
├── scripts/
│   ├── router_agent.py           # Function-Calling Router（核心入口）
│   ├── rag_tools.py              # ChromaDB 知识库查询
│   ├── platform_tools.py         # 44 平台关键词匹配路由
│   ├── conversation_memory.py    # 多轮对话记忆
│   ├── scrape_n7teahouse.py      # 南七茶馆 3 阶段 Pipeline
│   ├── build_knowledge_base.py   # ChromaDB 构建 + 检索测试
│   ├── chat_kb.py                # 旧版 RAG 交互查询（测试用）
│   ├── scraper.py                # 通用抓取工具
│   └── _archived/                # 已归档的旧脚本
├── data/
│   ├── platform_routing.json     # 44 个校园平台路由数据
│   ├── ustc_campus_platforms.txt # 校园平台目录（可读文本）
│   └── raw/n7teahouse/
│       └── n7_qa_knowledge.json  # 1,215 条 Q&A 知识条目
├── chroma_db/                    # ChromaDB 持久化向量库（不提交 git）
├── models/                       # m3e-base 嵌入模型（不提交 git）
└── docs/                         # 设计文档（需求分析/技术架构/竞品调研/数据源调查）
```

---

## 数据源

### 南七茶馆论坛（RAG 知识库核心）

- 9 个高价值标签，1,247 条候选帖子
- 3 阶段 Pipeline：爬取 → 筛选 → LLM 合成
- 最终产出 1,215 条 Q&A（97% 产出率）
- 嵌入：m3e-base（768 维），语义去重阈值 0.88

### 校园平台路由（44 个平台）

覆盖教务、课程、图书馆、生活、技术、医疗、升学等 14 个分类。详见 [ustc_campus_platforms.txt](data/ustc_campus_platforms.txt)

---

## 技术栈

| 层级 | 方案 |
|------|------|
| Agent 编排 | 原生 OpenAI Function Calling（无 LangChain 依赖） |
| LLM | deepseek-v4-pro / qwen3.5（通过 USTC API 网关） |
| 向量数据库 | ChromaDB + SentenceTransformer |
| 嵌入模型 | m3e-base（768维，中文检索专用） |
| HTTP 客户端 | httpx + urllib |
| HTML 解析 | BeautifulSoup4 |

### 为什么不用 LangChain？

- 8 周赛程紧，避免学习曲线和依赖冲突
- 项目已全部使用原生 `openai` SDK
- Function Calling 循环不到 100 行，完全可控
- 学校部署平台（107.ustc.edu.cn）兼容性更好

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [需求分析](需求分析_头脑风暴.md) | 用户痛点、功能需求 |
| [技术架构设计](技术架构设计.md) | 系统分层、技术选型、数据流 |
| [竞品调研](竞品调研与技术分析.md) | SJTU Agent 等竞品分析 |
| [数据源调查](数据源调查报告.md) | 科大 14 个平台实测 + 接入方案 |
| [论坛疑惑分析](科大生疑惑分析_南七茶馆.md) | 基于求助帖的用户真实痛点 |
| [Pipeline 测试记录](南七茶馆Pipeline测试记录.md) | 阈值实验、模型横评、参数调优 |
| [项目开发流程](项目开发流程记录.md) | 开发进度追踪 |
| [比赛通知](比赛通知_一〇七杯.md) | 赛程时间线、评审标准 |

---

## License

MIT
