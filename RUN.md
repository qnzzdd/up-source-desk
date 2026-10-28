# 上手运行（回家后的验证清单）

## 0. 需要什么

- Python 3.11+
- 一个已登录的 B 站账号（用于导出 Cookie）
- 网络能访问 `api.bilibili.com`

## 1. 安装

```bash
cd up-source-desk
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
```

## 2. 放 Cookie

浏览器登录 bilibili.com → `F12` → Application → Cookies → `https://www.bilibili.com`
复制 `SESSDATA` 与 `bili_jct` 的值，在项目根目录建 `cookie.txt`：

```
SESSDATA=xxxx; bili_jct=xxxx
```

`cookie.txt` 已在 `.gitignore` 中，不会被提交。也可以改用环境变量 `BILI_COOKIE`。

## 3. 验证顺序（每步都能独立失败，别跳）

```bash
# ① 建表
python -m scripts.sync_follows --init-db

# ② 鉴权自检：只读，不采集
python -m scripts.check_auth

# ③ 拉关注列表（先 20 个试水）
python -m scripts.sync_follows --limit 20

# ④ 看结果：这些全在「未分组」，一个内容请求都不会发
python -m scripts.manage stats
python -m scripts.manage ungrouped --limit 20
```

第 ③ 步成功后你应该看到类似：

```
登录账号 mid = 12345678
完成：共 20 人，新增未分组 20，改名 0，取关 0
```

## 4. 建分组并归组

```bash
# 建一个「每日必看」：6 小时一次，拉元数据+热评，图片只分类
python -m scripts.manage create "每日必看" --frequency 6h --depth L2 --comment top10 --image-mode classify

# 把某个 mid 归进去（mid 从 ungrouped 输出里拿）
python -m scripts.manage assign 12345 --group 1

# 查看分组当前状态
python -m scripts.manage show 1
```

**关键**：`assign` 之前，这个 UP 永远不采集；`assign` 之后才开始。想退回去：

```bash
python -m scripts.manage assign 12345     # 不写 --group 即退回未分组
```

## 5. 跑采集

```bash
# 只跑投稿，先看 5 个源
python -m scripts.sync_videos --limit 5 --max-pages 1

# 只跑动态
python -m scripts.sync_dynamics --limit 5 --max-pages 1

# 按频率自动判断哪些分组该跑
python -m scripts.run_cycle --force
```

每次都会打印：新增多少、失败几个、自动暂停几个、发了多少次请求。
`--dry-run` 会跑完再回滚，不留数据。

## 6. 定时（Windows）

任务计划程序 → 新建任务 → 触发器「每天，重复间隔 5 分钟」→ 操作：

```
程序:   <项目路径>\.venv\Scripts\python.exe
参数:   -m scripts.run_cycle
起始于: <项目路径>
```

因为 `run_cycle` 自己判断频率，5 分钟触发不会导致重复采集。

## 7. 常见错误对照

| 现象 | 含义 | 处理 |
|---|---|---|
| `[auth] code=-101 账号未登录` | Cookie 失效 | 重新导出 SESSDATA |
| `code=-352 风控校验` | 请求太快或 IP 异常 | 调大 `UPSD_INTERVAL`（默认 1.0 秒） |
| `code=-412` | 被限流 | 停一段时间，降低并发 |
| `可采集 source: 0` | 没有归组的 UP | 先 `assign` |
| 某 UP 连续失败 3 次自动暂停 | 达 `fail_threshold` | `assign` 重新归组即可恢复 |

## 8. 还没做的部分（别指望它现在能用）

- Web 界面（当前只有 CLI）
- AI 摘要（`UPSD_LLM_BASE/KEY/MODEL` 配置后才启用，否则一律返回「信息不足」）
- 图片视觉分析（`analyze` 档位目前只到「下载」）
- 日报生成
- 批量操作
