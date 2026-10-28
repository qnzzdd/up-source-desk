# UP源台 / UP Source Desk

一个面向个人的 B 站关注信息源管理工具。首版计划作为**本地 Web 应用**运行：在浏览器里整理关注 UP 主的分组，查看新增投稿和动态，并按分组生成可导出的日报。

> 当前是**只读交互 Demo**：账号、分组、关注、视频和动态均为合成数据。尚未读取真实 B 站登录态、关注列表或内容，也没有 AI 总结和写操作。

## 计划能力

- 同步关注列表，维护工具内分组；AI 可建议标签，但由用户确认。
- 增量监控投稿和动态，优先基于字幕或正文生成简短摘要。
- 定时生成按分组聚合的日报，支持 Markdown/HTML 导出与历史查看。
- 在预览和人工确认后，对选中 UP 主执行受限的批量操作。

## 产品边界

首版只在本机运行，不提供云端账号或公开访问。登录凭据、Cookie、数据库和生成的日报均应留在本机，不提交到 Git 仓库。采集和写操作需遵守平台规则，采用增量同步、限速与失败退避；无法获得内容文本时，不让 AI 猜测视频内容。

## 运行 Demo

需要 Python 3.11+ 和 Node.js 20+。

```powershell
# 首次安装
uv venv --python 3.11 --no-cache .venv
uv pip install --python .venv/Scripts/python.exe --no-cache -r backend/requirements.txt
npm --prefix frontend install

# 一键构建并启动
.\scripts\run-demo.ps1
```

浏览器打开 http://127.0.0.1:8766 。Stop with `Ctrl+C`.

演示数据保存在被 Git 忽略的 `data/demo.sqlite3`。点击「检查真实接口」会显示 `LIVE_NOT_CONNECTED`，这不是登录或真实同步。

## 下一阶段

先确认可以在受支持的登录态下读取当前账号、全部关注、B 站分组及首位 UP 的投稿与动态，再把只读数据源适配器接入现有 API。不得用演示数据掩盖登录失效、分页不完整或接口失败。

## 文档

- 当前 Demo 的 API 契约、审查边界和验收条件：[`docs/DEMO_CONTRACT.md`](docs/DEMO_CONTRACT.md)
- 整体架构、采集安全与实施阶段：[`docs/PLAN.md`](docs/PLAN.md)

临时项目名与技术选型均可在实现前调整。

## Console verification

The white/light-blue console provides overview, followings and read-only groups. Search, filtering, pagination and video/dynamic tabs operate on synthetic data. The real-interface check returns LIVE_NOT_CONNECTED; QR login, live sync, AI and reports are not implemented. See [UI acceptance](docs/UI_ACCEPTANCE.md) for evidence and walkthrough.
