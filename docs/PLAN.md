# UP 源台：架构与实施计划

## 1. 首版定义

首版是单用户、本机运行的 Web 应用。它负责把关注列表变成可管理的信息源，把新增内容变成按分组聚合的日报，并让用户在确认后处理低价值信息源。

首版必须完成：

1. 同步关注列表并保存到本地数据库。
2. 允许人工维护分组，AI 只提供建议。
3. 增量获取关注者的视频投稿与动态，避免重复处理。
4. 对字幕或正文生成简短摘要；内容文本缺失时保留原链接并明确标注。
5. 按设定时间生成分组的 Markdown 日报，并在 Web 页面查看。
6. 对分组内 UP 主生成批量操作预览；首版不自动执行取关。

首版明确不做：多用户与云端账号、公开内容分享、移动 App、跨平台安装包、无人值守的自动取关。

## 2. 环境检查结论

已检查本机命令和环境，未安装或调用第三方业务依赖：

| 项目 | 当前状态 | 对首版的影响 |
| --- | --- | --- |
| Git | 可用，已配置用户名和邮箱 | 可初始化仓库、提交本地代码 |
| GitHub CLI | 已安装，但登录凭据失效 | 需要重新授权后才能创建公开仓库 |
| Python | 3.14.3，pip 可用 | 可做后端；需逐项验证第三方库是否支持 3.14 |
| SQLite | 本机 Python 自带 3.50.4 | 足以承载首版本地数据 |
| Node.js / npm | v24.14.1 / 11.11.0，可用 | 可做前端构建；首版可先用模板减少复杂度 |
| uv | 命令存在，但缓存目录访问被拒绝 | 不作为默认工具，优先使用 venv + pip |
| Docker | CLI 存在，Docker daemon 未运行 | 暂不作为首发部署路径 |
| Windows 任务计划 | `schtasks.exe` 可用 | 可用作本机定时触发备选 |
| 外网与 B 站 API | 当前受限环境内连接失败 | 需在正常网络下做采集能力和登录要求验证 |

最需要优先验证的是 `bilibili-api-python` 在当前 Python 版本下的兼容性、登录态要求、关注/投稿/动态/字幕接口的实际返回范围，以及高频拉取下的限制。不能把 3000+ 账号的一次性全量处理当作已成立的前提。

## 3. 架构

```text
Browser
  |
  v
FastAPI + server-rendered templates
  |-- Auth/session: local only
  |-- Group and source management
  |-- Report browsing and export
  |-- Batch-operation preview and confirmation
  |
  v
Application services
  |-- Sync service: profile, follows, videos, dynamics
  |-- Scheduler: incremental polling and report jobs
  |-- Summary service: LLM adapter, prompt/versioning, cache
  |-- Report service: group aggregation and Markdown rendering
  |-- Operation service: validation, rate limiting, audit log
  |
  v
SQLite + local files
  |-- normalized source/group/content records
  |-- job checkpoints and error logs
  |-- generated reports and local settings
```

### 关键数据模型

- `source`：B 站账号标识、昵称、头像、最近同步信息。
- `group`：工具内分组；支持排序和启停，不与 B 站原生分组强绑定。
- `source_group`：UP 主与分组的关联，允许一个来源属于多个分组。
- `content`：投稿或动态，保存平台内容 ID、类型、发布时间和原始链接。
- `content_text`：字幕/正文可用状态及来源，区分“抓取到”“确实没有”“暂未获取”。
- `summary`：摘要文本、模型、提示词版本和生成时间，便于重跑和成本核算。
- `sync_cursor`：每个来源/接口类型的增量游标。
- `job_run`：任务状态、重试次数、失败原因，避免静默漏报。
- `report`：日报所属日期、分组快照、文件位置和生成状态。
- `operation_plan` / `operation_log`：批量操作预览、确认、执行结果与审计记录。

B 站原生分组只作为可选导入来源；工具内分组才是日报和操作的稳定主线。

## 4. 采集与安全策略

1. 使用官方开放接口或受支持客户端；所有凭据仅存本机，不写入代码库。
2. 同步采用低频、串行/小并发、指数退避、断点续跑；先做全量关注同步，再按分组轮询新增内容。
3. 不重复抓取已存在内容；摘要只对新增且有可用文本的内容生成。
4. 任务日志要能区分“没有新内容”“接口失败”“限流/验证要求”“文本缺失”，日报不能把失败伪装成没有更新。
5. 写操作必须经过预览、确认和频率限制；取关类操作默认关闭自动执行。

## 5. 分阶段实现

### 阶段 A：真实性验证

- 在正常网络下验证登录态、关注列表、投稿、动态、字幕的接口能力。
- 用少量账号测量一次请求成本、失败率和限流表现。
- 用 50、300、1000 个关注做分级同步实验，记录耗时与错误。

**出口条件**：明确哪些数据首版能稳定获得，哪些需要降级处理。

### 阶段 B：数据骨架

- 初始化 FastAPI 项目、SQLite 迁移、配置与本地登录。
- 实现来源、分组、内容、同步游标和任务日志的数据模型。
- 提供关注列表同步、分组增删改、增量内容入库的最小测试。

### 阶段 C：日报 MVP

- 接入可替换的 AI 摘要适配器，先支持一个 OpenAI 兼容端点。
- 实现按分组聚合日报、Markdown 导出和 Web 历史查看。
- 实现定时任务，并把失败状态显示在界面上。

### 阶段 D：批量操作

- 先实现分组内操作预览和任务清单。
- 再加入人工确认、限速执行、日志和失败重试。
- 在充分验证前不开放自动取关。

## 6. 待决策项

- AI 端点、模型与每日/每月预算上限。
- 首版日报的三个验收指标：生成时间、监控覆盖率、摘要可读性。
- 是否保留工具内多分组归属，还是首版仅允许单分组。
- 定时任务优先采用应用内调度还是 Windows 任务计划。
- 公开仓库是否只放代码与文档，以及是否明确声明项目仅供个人学习使用。
