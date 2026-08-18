# 邮件监控系统 · 云端部署指南（Docker）

> 本文档供执行 agent 按步骤完成部署。所有决策点已定，直接执行即可，无需向用户追问。
> 若部署细节与代码不一致，以代码为准，并同步更新本文档。

## 1. 系统概述

常驻进程（APScheduler 后台调度），非 Web 服务。功能链路：

```
IMAP 拉取邮件 (email_client.py)
  → 分类 (analyzer.py)：内部/外部、会议记录/HR/需回复、重要/垃圾/发票
  → 钉钉推送 (notifier.py)：
      实时提醒（外部重要邮件、发票邮件，随时到达）
      日报（每天 09:00，图片版优先，失败回退纯文本 Markdown）
  → 日报图片 (report_generator.py)：HTML 模板 + Playwright 截图
  → 托管 (r2_uploader.py)：Cloudflare R2，钉钉内嵌图片 + 完整版 HTML 链接
```

入口 `main.py` → `scheduler.EmailScheduler.start()`（首次启动立即执行一次重要邮件检测；之后 **IMAP IDLE 长连接实时监听**为主——新邮件到达服务器秒级推送通知立即检测，`CHECK_INTERVAL` 轮询仅作兜底防通知丢失）。

> IDLE 实现要点：阿里企业邮箱（imap.qiye.aliyun.com）支持 IDLE；命令必须带 tag（`A3 IDLE`，无 tag 会返回 `IDLE BAD invalid command or parameters`）；用独立 IMAP 连接监听，不干扰 EmailClient 的 fetch 连接；单次 IDLE 20 分钟超时后 DONE 重新进入以保活；异常 5 秒自动重连。

## 2. 前置条件

### 2.1 服务器要求
- Linux（x86_64 或 arm64 均可），2 核 2G 起步即可
- Docker 24+ 与 Docker Compose v2（`docker compose` 子命令可用）
- 出站网络放行：`imap.qiye.aliyun.com:993`（IMAP）、`oapi.dingtalk.com:443`（钉钉）、R2 上传端点（`*.r2.cloudflarestorage.com`）、`pub-*.r2.dev`（图片回源）
- 无需公网入站端口、无需域名

### 2.2 凭证（部署时从本仓库 `.env.docker` 或用户本地 `.env` 获取，勿向用户索要）
| 变量 | 用途 | 备注 |
|---|---|---|
| `EMAIL_USER` / `EMAIL_PASSWORD` | 企业邮箱 IMAP 登录 | **必须与要监控的邮箱一致**（历史问题：`deploy.sh` 与 `.env` 曾出现账号不一致，部署前务必确认） |
| `DINGTALK_WEBHOOK` | 钉钉群机器人 | 机器人安全设置关键词为 `Email`，notifier 已自动处理 |
| `R2_*` | 日报图片托管 | 缺失或失效时系统自动回退纯文本，不阻塞部署 |

## 3. 部署步骤

### 3.1 服务器安装 Docker（如未安装）
```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
# 国内加速（可选但推荐）
mkdir -p /etc/docker && cat > /etc/docker/daemon.json <<'EOF'
{"registry-mirrors": ["https://docker.m.daocloud.io"]}
EOF
systemctl restart docker
```

### 3.2 传输项目文件
从本仓库所在机器执行（`<SERVER>` 为服务器地址）：
```bash
rsync -avz --delete --exclude venv --exclude __pycache__ --exclude data \
  --exclude .git --exclude '.env' \
  --exclude design-demos --exclude 'test_*.py' \
  ./ <SERVER>:/opt/email_observer/
```
必须包含：`Dockerfile`、`docker-compose.yml`、`requirements.txt`、`config.py`、`email_client.py`、`analyzer.py`、`notifier.py`、`scheduler.py`、`main.py`、`r2_uploader.py`、`report_generator.py`、`domains.json`、`templates/`。
注意：若通过 expect 包裹 rsync 传参，exclude 模式必须用 Tcl 花括号 `{}` 包裹（单引号会被当作字面字符导致排除失效）；被排除文件残留需在服务器上手动 `rm`。**禁止用 `--exclude '*.html'`/`--exclude '*.png'` 这类通配排除**（曾因此漏传 `templates/report.html` 导致日报占位符残留），需排除设计演示文件时直接排除 `design-demos` 目录。

### 3.3 准备环境变量
```bash
cd /opt/email_observer
cp .env.docker .env.docker.bak   # 若服务器上已有备份则跳过
# 若服务器上还没有 .env.docker，从本地传输后：
chmod 600 .env.docker
```
**安全约束：agent 不得在文档、命令、日志、对话中输出 `.env.docker` 的密码/令牌内容**；如缺文件，请用户从本地直接传输，不要复制粘贴明文。

### 3.4 构建并启动
```bash
cd /opt/email_observer
docker compose up -d --build
docker compose ps        # 期望 STATUS: Up
```
镜像构建含 Playwright Chromium（清华 apt/pip 源 + npmmirror），首次构建约 5–10 分钟。

## 4. 验证

1. **日志确认启动**：`docker compose logs -f email-observer`
   - 应看到「邮件监控系统已启动」+「执行首次检测...」+「检查新邮件...」（首次启动立即检测）
2. **实时提醒**：向监控邮箱发一封外部测试邮件（或等待真实邮件），日志出现「发现 N 封新重要邮件」且钉钉群收到提醒
3. **日报**：等待 `DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE`（默认 09:00）或手动触发：
   ```bash
   docker compose exec email-observer python -c "from scheduler import EmailScheduler; EmailScheduler().daily_report()"
   ```
   钉钉群应收到日报（图片版；R2 不可用时为纯文本版，属正常回退）
4. **分类抽查**：日报中内部邮件（会议/HR/需回复）与外部邮件（重要/垃圾/发票）分区应显示摘要

## 5. 运维

| 操作 | 命令 |
|---|---|
| 查看日志 | `docker compose logs -f email-observer` |
| 重启 | `docker compose restart` |
| 停止 | `docker compose down`（数据保留在 `./data`） |
| 升级代码 | 重新 rsync 后 `docker compose up -d --build` |
| 备份 | `./data/`（含 `notified_cache.json` 已通知缓存）+ `.env.docker` |

- **时区**：`TZ=Asia/Shanghai` 已在 compose 配置，日报时间按北京时间
- **重复提醒防护**：`./data/notified_cache.json` 记录当日已通知邮件 ID，每日自然日重置；`data/` 已挂载 volume 持久化
- **注意**：日报统计窗口为自然日（0–24 点），非滚动 24 小时

## 6. 分类规则与配置（agent 调整规则时的上下文）

配置集中在 `domains.json`，改后 `docker compose restart email-observer` 生效：

| 配置键 | 含义 |
|---|---|
| `internal_domains` | 内部域名（如 aqara.com、aqara.cn），发件人域名匹配即内部邮件 |
| `internal_meeting_keywords` / `internal_hr_keywords` / `internal_reply_keywords` | 内部子类型关键词，优先级 会议 > HR > 需回复 |
| `important_domains` / `important_keywords` | 外部重要邮件判定（域名 或 关键词） |
| `spam_keywords` | 垃圾判定，**命中 ≥2 个关键词**才算垃圾 |
| `invoice_keywords` | 发票判定，优先级最高 |
| `no_reply_keywords` | 无需回复的通知类排除（验证码/系统通知/订阅等），命中任一即不判重要 |

分类优先级（`analyzer.py`）：内部域名 → 子类型；外部 → 发票 > 垃圾 > 通知类排除（`no_reply_keywords`，验证码/密码提醒/订阅等）> 重要（域名/关键词）> 单独发送给我（To 只有本账号且无抄送、非通知类）> 普通（只计数）。

匹配规则：中文关键词子串匹配；英文关键词**单词边界**匹配（`\b`），勿加 `minutes`、`free` 等易误伤单词，用 `meeting minutes`、`free gift` 等短语。

## 7. 常见问题排查

| 现象 | 原因与处理 |
|---|---|
| 钉钉收不到消息 | 检查 webhook 是否有效；消息必须含关键词 `Email`（notifier 已处理）；`notifier.py` 日志出现「推送失败/异常」则为 webhook 问题 |
| 日报是纯文本无图片 | R2 凭证缺失/失效，自动回退（设计行为）；检查 `.env.docker` 的 `R2_*` 四项是否齐全 |
| IMAP 连接失败 | 日志「连接邮箱失败」：检查 `EMAIL_USER` 密码是否错误、企业邮箱是否开启 IMAP 服务 |
| 邮件重复提醒 | `data/notified_cache.json` 被删除或跨日；正常行为是每日自然日重置 |
| 日报时间不对 | 容器时区：确认 `TZ=Asia/Shanghai` 生效（`docker compose exec email-observer date`） |
| 分类不符合预期 | 调整 `domains.json` 关键词后重启；英文关键词用单词边界短语 |

## 8. 安全注意事项

- 凭证仅存在于 `.env.docker`（已被 `.gitignore` 忽略，不会进 git）；服务器上 `chmod 600`
- **禁止使用 `deploy.sh`**：它是旧的 systemd 部署脚本，内含明文密码且方案已被 Docker 取代（该文件同样被 `.gitignore` 忽略）
- agent 在任何输出中不得泄露 `.env.docker` / `.env` 中的密码、令牌、webhook 地址
- 服务器建议：仅开放必要的出站端口，不开放 SSH 密码登录（用密钥）
