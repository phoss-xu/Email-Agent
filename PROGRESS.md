# PROGRESS.md — 项目进度交付文档

> 面向下一个 agent 的当前进度快照。最后更新：2026-09-09 11:06
> 详细部署文档见 [DEPLOYMENT.md](DEPLOYMENT.md)

## 项目是什么

邮件监控系统（Email Agent）：监听企业邮箱（阿里企业邮，IMAP），新邮件到达**秒级**检测分类，通过钉钉群机器人推送：
- **即时提醒**：重要/发票/内部邮件 → 图片版卡片推送（来一封发一封）
- **每日日报**：每天 09:00 推送完整日报（图片版 + HTML 链接）

## 架构与文件

| 文件 | 职责 |
|---|---|
| `main.py` | 入口：启动 scheduler |
| `scheduler.py` | APScheduler 日报定时 + **IMAP IDLE 长连接实时监听**（新邮件秒级触发）+ 兜底轮询（3 分钟） |
| `email_client.py` | IMAP 拉取/解析（EmailMessage 模型：subject/sender/domain/date/body/recipients/cc/message_id/summary） |
| `analyzer.py` | 分类：内部（会议/HR/需回复/其他）→ 外部（发票/垃圾/通知类排除/重要/单独发送给我/普通） |
| `report_generator.py` | HTML 模板渲染 + Playwright 截图（日报图、重要邮件提醒图、内部邮件提醒图） |
| `notifier.py` | 钉钉推送（日报、重要/发票/内部邮件提醒；R2 图片版优先 + 文本回退） |
| `templates/` | `report.html`（日报）、`alert.html`（重要提醒·红）、`internal_alert.html`（内部提醒·蓝） |
| `domains.json` | 内部域名、重要域名、各分类中英文关键词 |
| `r2_uploader.py` | Cloudflare R2 图片托管 |

## 分类规则要点

1. 内部域名（aqara.com/aqara.cn/lumiunited.com）→ 子类型：会议记录 > HR > 需回复 > 其他（关键词匹配，英文用词边界 \b）
2. 外部 → 发票 > 垃圾 > 通知类排除（验证码等 no_reply_keywords）> 重要（域名/关键词）> 单独发送给我（To 只有自己且无 cc）> 普通
3. 未匹配子类的内部邮件只计总数不展示明细；摘要 = 正文开头 150 字

## 即时提醒体系（IDLE 模式：来一封发一封）

- **重要邮件**：红■ `alert.html` 图片版（匹配原因红字批注）→ R2 → 钉钉，失败回退文本
- **发票邮件**：纯文本版（尚未做图片模板）
- **内部邮件**：蓝■ `internal_alert.html` 图片版（类型标签蓝字批注）→ R2 → 钉钉，失败回退文本
- 去重：`notified_ids`（按天缓存，含无 Message-ID 的 uid 回退标识）

## 部署状态

- 服务器：`172.16.200.141`（`/home/xzc/SI/test/Email-Agent`，Docker Compose 容器 `email-observer`）
- 本地分支 `dev` → GitHub `phoss-xu/Email-Agent`，**push 必须显式 `git push origin dev`**
- 最新 commit：`20b274e`（lumiunited.com 从 important_domains 迁为内部域名 + 修正 DEPLOYMENT.md 配置生效说明）
- ✅ 服务器已部署最新配置（2026-09-09 11:06 验证：容器 Up、容器内 internal_domains 含 lumiunited.com、首次检测捕获 1 封内部邮件并成功推送钉钉、IDLE 监听正常）
- 历史部署：`6d175a9`（2026-09-07 18:31，日报分类明细全量展示 + 单部件 HTML 转纯文本；顺带清理服务器遗留 start.sh / nginx-reports.conf / deploy.sh）

## 历史重要修复（已合入）

- **IMAP 序号去重撞车**：无 Message-ID 邮件的回退标识曾用 IMAP 序号（seq），邮件被删后序号重排导致新邮件顶替旧标识被误判已提醒；已改用 IMAP UID（`_extract_uid`，RFC 3501 永久唯一）
- **IDLE 进入被积压通知误伤**：重新进入 IDLE 时 `* N EXPUNGE` 等 untagged 通知可能抢在 `+ idling` 前到达；已改为循环跳过直到出现 `+ idling`
- **IDLE 连接被轮询并发断开**：进入 IDLE 前 `_drain()` 清空积压通知
- **单部件 HTML 邮件摘要暴露源码**：`_get_body` 非 multipart 分支原先不判 content-type，单部件 `text/html` 邮件（营销/系统邮件常见）原始 HTML 直接进 body，日报摘要显示 `<div style=...` 源码；已统一走 `_html_to_text`（去 style/script/head 块、块级标签转换行、还原实体）

## 关键坑（务必遵守）

- IDLE 命令必须带 tag（`conn._new_tag()`），无 tag 返回 BAD
- 进入 IDLE 前 `_drain()` 清空积压通知，否则与轮询并发时连接被服务器断开
- rsync 禁止 `--exclude '*.html'`（会漏传 templates 目录！）
- `domains.json` 由 Dockerfile COPY 进镜像（compose 只挂载 `./data`），改后必须 rsync + `docker compose up -d --build` 重建，单纯 `restart` 读不到宿主机新文件
- 钉钉图片不支持 query 参数防缓存 → 用时间戳文件名
- SMTP 测试邮件无 Message-ID → `email_client.py` 已加 `uid-{序号}` 回退
- 企业邮箱 SMTP 强制 From=认证账号，无法伪造外部发件人（外部链路测试需真实外部邮箱）

## 用户流程偏好（重要）

**任何改动：先本地验证 → 用户在钉钉确认实际效果 OK → 才 commit + 部署服务器。** 不要只凭日志"推送成功"就部署。

## 待办

- [ ] 等用户确认内部邮件图片版提醒效果
- [ ] 发票邮件提醒的图片模板（可选，目前纯文本）
- [ ] 观察明日 09:00 自动日报
