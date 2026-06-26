# AGENTS.md — AI 编码助手工作指引

> **你是来帮我们开发"校园 Copilot"的 AI 助手，不是我们要开发的 Agent 本身。**
> 这个文件告诉你：我们在做什么、做到哪了、你该怎么帮。

---

## 我们在做什么

**校园 Copilot** — 面向 USTC 大一新生的校园生活智能助手，参加"一〇七杯"智能体赛道比赛。

- **队伍**: CloseClaw | **队员**: 张义临、钟华杰 (2人)
- **赛道**: 智能体赛道 | **方向**: 校园生活场景
- **评审维度**: 创新性、实用性、技术难度、完成度

### 核心文档（需要了解项目全貌时先读这些）

| 文档 | 用途 |
|------|------|
| [比赛通知_一〇七杯.md](./比赛通知_一〇七杯.md) | 赛程时间线、评审标准、奖项 |
| [需求分析_头脑风暴.md](./需求分析_头脑风暴.md) | 用户痛点、功能需求、科大现有平台清单 |
| [技术架构设计.md](./技术架构设计.md) | 系统分层架构、技术选型、数据流 |
| [竞品调研与技术分析.md](./竞品调研与技术分析.md) | SJTU Agent 等竞品参考 |
| [数据源调查报告.md](./数据源调查报告.md) | 科大各平台实测可访问性与接入方案 |
| [科大生疑惑分析_南七茶馆.md](./科大生疑惑分析_南七茶馆.md) | 基于论坛求助帖的用户真实痛点分析 |
| [项目开发流程记录.md](./项目开发流程记录.md) | 开发进度追踪 |

---

## 当前阶段：数据采集 + 知识库构建（Phase 2）

**已经进入编码阶段。** 你的协助重点是：

- ✅ 基于南七茶馆论坛数据构建 RAG 知识库
- ✅ 优化数据 Pipeline 的参数和提示词
- ✅ 开发其他数据源的爬取脚本
- ✅ 准备多智能体架构的 Router Prompt
- ❌ **不要**偏离"校园 Copilot"这个产品方向
- ❌ **不要**对已完成的脚本做无意义的重复工作

### 当前进度（2026-06-26）

| 模块 | 状态 | 备注 |
|------|------|------|
| 南七茶馆 Pipeline | ✅ **全量完成** | 1247→1215 条(97%)，qwen3.5，4 并发 |
| RAG 知识库构建 | ✅ **1215 条** | m3e-base 嵌入 + 双重去重 |
| 校园平台目录 | ✅ **44 个平台** | data/platform_routing.json + 科大校园平台目录.txt |
| 教务系统 API 探测 | ✅ 已探明 | catalog.ustc.edu.cn 8 个 REST 端点 |
| **Function-Calling Router** | ✅ **开发完成** | router_agent.py，3 tool，多轮记忆 |
| 其他数据源爬虫 | ⬜ 待开发 | 迎新网/图书馆/校医院等 |
| 多智能体架构 | ⬜ 未开始 | |

### 🆕 Router Agent 架构（2026-06-26）

基于原生 OpenAI Function Calling，三个工具：
- `search_forum_knowledge` → ChromaDB RAG（论坛经验）
- `navigate_to_platform` → 44 平台关键词匹配路由
- `search_course_info` → 教务查询（占位）

启动：`$env:PYTHONIOENCODING="utf-8"; D:/conda/envs/campus-copilot/python.exe scripts/router_agent.py` 

### 🆕 南七茶馆标签全量（2026-06-25）

论坛共 60+ 个标签，已确认高价值标签 9 个：

| 优先级 | 标签 | Slug | 帖子数 | 说明 |
|--------|------|------|--------|------|
| 🔴 P0 | 求助&答疑 | `help` | 1016 | 通用求助帖（已分析 300 条） |
| 🔴 P0 | 生涯规划 | `career` | 387 | 保研/考研/就业/出国 |
| 🔴 P0 | 课程/学术 | `academic` | 291 | 课程、学术研究 |
| 🟡 P1 | 校园生活 | `campus` | 625 | 生活琐事、吐槽 |
| 🟡 P1 | 信息发布 | `information` | 224 | 招生、工作、内推 |
| 🟡 P1 | 技术 | `technology` | 95 | 编程、数码 |
| 🟢 P2 | 校园攻略 | `guide` | 9 | 攻略、经验分享 |
| 🟢 P2 | 已解决 | `solved` | 10 | 高质量已解决问题 |
| 🟢 P2 | 校园动态 | `activities` | 49 | 校园活动 |

> 预计全量数据：~2700 条帖子，按 52% 产出率可产出 ~1400 条 Q&A 知识条目

---

## 已确定的技术决策

| 领域 | 选型 | 备注 |
|------|------|------|
| 后端框架 | FastAPI | API 网关 |
| 大模型 | qwen3.6-chat（默认）/ 多模型可用 | 比赛提供，12 模型横评后选定 |
| 部署平台 | 107.ustc.edu.cn | 学校本科生算力平台 |
| Agent 框架 | **待定** | 倾向 LangGraph，需进一步评估 |
| RAG 引擎 | **待定** | 需选型 |
| 前端 | **待定** | Web UI / 微信 Bot 等 |

---

## 产品架构（开发时要实现的目标）

```
用户 → FastAPI 网关 → Router Agent → 学习助手 / 生活助手 / 社交助手 → Synthesizer → 回复
                              ↕
                      RAG 知识库 + 工具层
```

- **Router Agent**: 意图识别、任务分发
- **学习助手**: 课表/成绩、图书馆/自习室
- **生活助手**: 食堂/导航、报修/快递
- **社交助手**: 活动/社团、推荐/融入
- **Synthesizer Agent**: 结果整合、个性化输出

---

## 关键约束

- ⏰ **8 周开发周期**，9 月 6 日提交截止
- 👥 **只有 2 人**，技术选型要务实，别过度设计
- 🏫 部署在**学校算力平台**，注意兼容性
- 📋 初评看**设计文档 + 演示视频**，文档质量很重要
- 🔑 重要参考: [SJTU Agent](https://github.com/kuan-er/sjtu-agent) (Python + Playwright + Flask)

### 🆕 数据源优先级（基于论坛需求分析）

| 优先级 | 平台 | 用途 | 理由 |
|--------|------|------|------|
| 🔴 P0 | **南七茶馆 API** | RAG知识库核心数据源 | 唯一有公开API，6标签~2191条求助帖 |
| 🔴 P0 | **评课社区** (icourse.club) | 课程/导师评价 | 42,470条点评，保研选课核心数据 |
| 🔴 P0 | **教务系统公共查询** | 课程、考试、教室 | 无需登录，2520个课堂数据 |
| 🔴 P0 | **图书馆** | 开放时间、服务 | 完全公开 |
| 🟡 P1 | **校园地图** (map.ustc.edu.cn) | 地图功能 | 6校区瓦片地图现成可用 |
| 🟡 P1 | **迎新网** | 新生FAQ | 报到流程、校园导览 |
| 🟡 P1 | **校医院** | 门诊排班 | 完全公开 |
| 🟢 P2 | 第二课堂、蜗壳学社 | 活动、社区 | 需CAS登录，难度高 |

---

## 你的工作原则

1. **先理解再行动** — 不确定时先读相关文档，别凭猜测
2. **紧扣产品方向** — 所有建议都围绕"帮新生用好校园资源"这个核心
3. **务实优先** — 2 人 8 周，选成熟方案，别追新
4. **阶段性推进** — 当前在数据采集阶段，先跑通南七茶馆再扩展其他数据源

---

## 开发环境

| 项目 | 详情 |
|------|------|
| Python | `D:/conda/envs/campus-copilot/python.exe` |
| 环境激活 | `conda activate campus-copilot` |
| LLM API | `https://api.llm.ustc.edu.cn/v1`，每个用户需在 .env 配置自己的 Key（申请: https://llm.ustc.edu.cn/llmService） |
| 默认模型 | `deepseek-v4-pro` |
| 编码问题 | Windows 终端不支持 UTF-8 中文，脚本执行需加 `PYTHONIOENCODING=utf-8` |

## 关键脚本

| 脚本 | 功能 | 用法 |
|------|------|------|
| `scripts/scrape_n7teahouse.py` | 南七茶馆 3 阶段 Q&A 提取 | `python scripts/scrape_n7teahouse.py` |
| `scripts/build_knowledge_base.py` | Q&A JSON → ChromaDB | `python scripts/build_knowledge_base.py` |
| `scripts/scraper.py` | 通用抓取工具（fetch_json, save_json 等） | 被其他脚本 import |

### Pipeline 参数（scrape_n7teahouse.py）

| 参数 | 值 | 含义 |
|------|-----|------|
| `MIN_REPLIES` | 3 | 帖子至少 3 条回复 |
| `MIN_LIKES_FOR_VALUE` | **1** | 回复至少 1 赞算有价值（经实验验证，原为 2） |
| `MAX_REPLIES_PER_POST` | 6 | 每条帖子保留 top-6 条回复 |
| `MAX_SYNTHESIS_CHARS` | 8000 | 单次 LLM 调用最大输入 |

### 数据文件

| 文件 | 内容 |
|------|------|
| `data/raw/n7teahouse/n7_qa_knowledge.json` | 最终 Q&A 知识条目 |
| `data/raw/n7teahouse/threshold_experiment_report.json` | 阈值对照试验完整数据（58 条） |
| `chroma_db/` | ChromaDB 持久化向量库 |