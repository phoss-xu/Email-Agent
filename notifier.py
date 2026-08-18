"""通知模块 - 钉钉群机器人推送"""
import datetime
import requests
from config import Config


def _escape_md(text: str) -> str:
    """转义用户内容中的 *，避免破坏钉钉 ** 粗体配对（钉钉不支持反斜杠转义时也安全）"""
    if not text:
        return ''
    return text.replace('*', '＊')


class Notifier:
    """钉钉群机器人通知器"""

    KEYWORD = "Email"  # 钉钉机器人安全关键词

    def _send(self, title: str, content: str) -> bool:
        """向钉钉群推送 Markdown 消息"""
        try:
            # 不加 ### 标题前缀：钉钉会把 ### 开头行渲染成消息卡片头（图标+标题），挤占第一行；标题保留在 title 字段
            md_text = content
            if self.KEYWORD not in md_text:
                md_text = f"{md_text}\n\n[{self.KEYWORD}]"

            response = requests.post(
                Config.DINGTALK_WEBHOOK,
                json={
                    "msgtype": "markdown",
                    "markdown": {
                        "title": f"[{self.KEYWORD}] {title}",
                        "text": md_text
                    }
                },
                timeout=10
            )
            result = response.json()
            if result.get('errcode') == 0:
                print(f"  -> 推送成功: {title}")
                return True
            else:
                print(f"  -> 推送失败: {result.get('errmsg', '未知错误')}")
                return False
        except Exception as e:
            print(f"  -> 推送异常: {e}")
            return False

    def send_daily_report(self, analysis_result: dict):
        """发送日报汇总：优先 R2 图片+链接方案，失败或空态回退纯 Markdown 文本"""
        total = len(analysis_result['total'])
        if total > 0 and self._try_send_r2_report(analysis_result):
            return
        self._send_text_daily_report(analysis_result)

    def _try_send_r2_report(self, analysis_result: dict) -> bool:
        """尝试 R2 方案：生成 HTML/图片 → 上传 R2 → 钉钉发图片+完整版链接"""
        try:
            from report_generator import ReportGenerator
            from r2_uploader import R2Uploader

            uploader = R2Uploader()
            if not uploader.available:
                print("  -> R2 未配置完整，回退纯 Markdown")
                return False

            generator = ReportGenerator()
            # 文件名带时间：同名覆盖会撞钉钉/浏览器缓存，且钉钉图片不支持 query 参数，故用唯一文件名防缓存
            ts_str = datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
            image_path = generator.generate_image(analysis_result)
            html_path = generator.generate_html(analysis_result)
            if not image_path or not html_path:
                print("  -> HTML/图片生成失败，回退纯 Markdown")
                return False

            img_url = uploader.upload(image_path, f'reports/{ts_str}.png')
            html_url = uploader.upload(html_path, f'reports/{ts_str}.html')
            if not img_url or not html_url:
                print("  -> R2 上传失败，回退纯 Markdown")
                return False

            self._send_image_report(analysis_result, img_url, html_url)
            return True
        except Exception as e:
            print(f"  -> R2 方案异常: {e}，回退纯 Markdown")
            return False

    def _send_image_report(self, analysis_result: dict, img_url: str, html_url: str):
        """发送钉钉日报：内嵌图片 + 重要/发票邮件链接列表 + 完整版链接"""
        important_emails = analysis_result['important']
        invoice_emails = analysis_result['invoice']
        spam_emails = analysis_result['spam']

        stats = f"共收到 **{len(analysis_result['total'])}** 封邮件"
        parts = self._overview_stats(analysis_result)
        if parts:
            stats += " ｜ " + " ｜ ".join(parts)

        lines = []
        # 标题用 ####（钉钉对 ### 开头渲染卡片头图标，#### 只渲染普通标题行，无图标）
        lines.append("#### 📧 邮件日报")
        lines.append("")
        # alt 内嵌关键词 Email（钉钉安全设置要求），避免消息末尾出现 [Email] 行
        lines.append(f"![Email 邮件日报]({img_url})")
        lines.append("")
        lines.append(f"> {stats}")
        lines.append("")

        # 外部重要邮件：主题链接到日报 HTML 锚点定位（IMAP 邮件无公开直达 URL，锚点可快速定位该封邮件）
        if important_emails:
            lines.append("**外部重要邮件**")
            lines.append("")
            for i, e in enumerate(important_emails[:5], 1):
                link_text = self._short_subject(e.subject).replace('[', '［').replace(']', '］')
                lines.append(f"**{i}. [{link_text}]({html_url}#imp-{i})** · 来自 {self._short_sender(e.sender)}")
                lines.append("")
            if len(important_emails) > 5:
                lines.append(f"…还有 **{len(important_emails) - 5}** 封未展示")
                lines.append("")

        # 发票邮件：同上（锚点 inv-N）
        if invoice_emails:
            lines.append("**发票邮件**")
            lines.append("")
            for i, e in enumerate(invoice_emails[:3], 1):
                link_text = self._short_subject(e.subject).replace('[', '［').replace(']', '］')
                lines.append(f"**{i}. [{link_text}]({html_url}#inv-{i})** · 来自 {self._short_sender(e.sender)}")
                lines.append("")
            if len(invoice_emails) > 3:
                lines.append(f"…还有 **{len(invoice_emails) - 3}** 封未展示")
                lines.append("")

        # CTA：完整日报 + 邮箱
        lines.append(f"**📄 [查看完整日报]({html_url}) · 📧 [点击查看邮箱](https://qiye.aliyun.com/alimail/)**")

        self._send("📧 邮件日报", '\n'.join(lines))

    def _send_text_daily_report(self, analysis_result: dict):
        """发送日报汇总（钉钉友好版 Markdown，R2 不可用时的回退方案）"""
        total = len(analysis_result['total'])
        internal_emails = [
            e for key in ('internal_meeting', 'internal_hr', 'internal_reply', 'internal_other')
            for e in analysis_result[key]
        ]
        important_emails = analysis_result['important']
        invoice_emails = analysis_result['invoice']
        spam_emails = analysis_result['spam']
        now = datetime.datetime.now()

        lines = []

        # ── 空状态：0 封时只走空态分支 ──
        if total == 0:
            lines.append("#### ✨ 今日无新邮件")
            lines.append("")
            lines.append("> 邮箱很安静，享受这一天吧 ☕")
            lines.append("")
        else:
            # ── 数据概览（钉钉会把无空行分隔的连续行合并为一段，因此每个段落之后必须空行）──
            lines.append(f"#### 📬 **{now.month}月{now.day}日**（{self._weekday_cn(now.weekday())}）· 今日概览")
            lines.append("")
            lines.append(f"> 共收到 **{total}** 封邮件")
            lines.append("")
            stats = self._overview_stats(analysis_result)
            if stats:
                lines.append(" ｜ ".join(stats))
                lines.append("")

            # ── 内部邮件（每封：粗体主题 + 类型标注 + 摘要引用块）──
            if internal_emails:
                lines.append(f"#### 🏢 内部邮件（**{len(internal_emails)}**）")
                lines.append("")
                for i, e in enumerate(internal_emails[:5], 1):
                    type_name = self._internal_type_name(e.category)
                    line = f"**{i}. {self._short_subject(e.subject)}**"
                    if type_name:
                        line += f" · {type_name}"
                    lines.append(line)
                    lines.append("")
                    summary = self._short_summary(getattr(e, 'summary', ''))
                    if summary:
                        lines.append(f"> {summary}")
                        lines.append("")
                if len(internal_emails) > 5:
                    lines.append(f"…还有 **{len(internal_emails) - 5}** 封未展示")
                    lines.append("")

            # ── 外部重要邮件（每封两段：粗体主题 + 详情；段间空行防止钉钉合并成一行）──
            if important_emails:
                lines.append(f"#### ⭐ 外部重要邮件（**{len(important_emails)}**）")
                lines.append("")
                for i, e in enumerate(important_emails[:5], 1):
                    lines.append(f"**{i}. {self._short_subject(e.subject)}**")
                    lines.append("")
                    detail = f"来自 {self._short_sender(e.sender)}"
                    reason = getattr(e, 'match_reason', '')
                    if reason:
                        detail += f" · 原因：{reason}"
                    lines.append(detail)
                    lines.append("")
                    summary = self._short_summary(getattr(e, 'summary', ''))
                    if summary:
                        lines.append(f"> {summary}")
                        lines.append("")
                if len(important_emails) > 5:
                    lines.append(f"…还有 **{len(important_emails) - 5}** 封未展示")
                    lines.append("")

            # ── 发票邮件（单行式：粗体主题 + 发件人）──
            if invoice_emails:
                lines.append(f"#### 🧾 发票邮件（**{len(invoice_emails)}**）")
                lines.append("")
                for i, e in enumerate(invoice_emails[:3], 1):
                    lines.append(
                        f"**{i}. {self._short_subject(e.subject)}** · 来自 {self._short_sender(e.sender)}"
                    )
                    lines.append("")
                if len(invoice_emails) > 3:
                    lines.append(f"…还有 **{len(invoice_emails) - 3}** 封未展示")
                    lines.append("")

            # ── 垃圾邮件（单行引用块，弱化展示）──
            if spam_emails:
                lines.append(f"#### 🗑️ 已拦截垃圾（**{len(spam_emails)}**）")
                lines.append("")
                spam_senders = [self._short_sender(e.sender) for e in spam_emails[:5]]
                extra = f" · …等 **{len(spam_emails)}** 封" if len(spam_emails) > 5 else ""
                lines.append(f"> {' · '.join(spam_senders)}{extra}")
                lines.append("")

        # ── 底部 CTA（独立段落；不用分割线，钉钉不渲染）──
        lines.append("**📧 [点击查看邮箱](https://qiye.aliyun.com/alimail/) · 自动推送 by Email Agent**")

        self._send("📧 邮件日报", '\n'.join(lines))

    @staticmethod
    def _overview_stats(analysis_result: dict) -> list:
        """构建概览统计：内部 N（会议 x · HR x · 需回复 x）｜ 外部 N（重要 x · 发票 x · 垃圾 x）"""
        internal_total = sum(len(analysis_result[k]) for k in
                             ('internal_meeting', 'internal_hr', 'internal_reply', 'internal_other'))
        stats = []
        if internal_total:
            sub = ' · '.join(
                f'{name} {len(analysis_result[key])}'
                for key, name in (('internal_meeting', '会议'), ('internal_hr', 'HR'), ('internal_reply', '需回复'))
                if analysis_result[key]
            )
            stats.append(f"🏢 内部 **{internal_total}**" + (f"（{sub}）" if sub else ""))
        external_total = len(analysis_result['total']) - internal_total
        if external_total:
            sub = ' · '.join(
                f'{name} {len(analysis_result[key])}'
                for key, name in (('important', '重要'), ('invoice', '发票'), ('spam', '垃圾'))
                if analysis_result[key]
            )
            stats.append(f"🌐 外部 **{external_total}**" + (f"（{sub}）" if sub else ""))
        return stats

    @staticmethod
    def _internal_type_name(category: str) -> str:
        """内部邮件子类型显示名"""
        names = {
            'internal_meeting': '会议记录',
            'internal_hr': 'HR',
            'internal_reply': '需回复',
            'internal_other': '其他',
        }
        return names.get(category, '')

    @staticmethod
    def _short_summary(summary: str, max_len: int = 100) -> str:
        """摘要截断并转义 *，防止破坏钉钉粗体配对"""
        if not summary:
            return ''
        text = summary if len(summary) <= max_len else summary[:max_len] + '…'
        return _escape_md(text)

    @staticmethod
    def _short_sender(sender: str, max_len: int = 20) -> str:
        """截断过长发件人并转义 *，保证手机端单行显示"""
        name = sender.split('<')[0].strip().strip('"')
        if name:
            name = name if len(name) <= max_len else name[:max_len] + '…'
            return _escape_md(name)
        local = sender.split('@')[0]
        local = local if len(local) <= max_len else local[:max_len] + '…'
        return _escape_md(local)

    @staticmethod
    def _short_subject(subject: str, max_len: int = 25) -> str:
        """截断过长主题并转义 *，防止移动端锯齿换行与格式破坏"""
        if not subject:
            return '(无主题)'
        text = subject.strip().replace('\n', ' ')
        text = text if len(text) <= max_len else text[:max_len] + '…'
        return _escape_md(text)

    @staticmethod
    def _weekday_cn(weekday: int) -> str:
        """返回中文星期"""
        names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        return names[weekday]

    def send_internal_alert(self, emails):
        """发送内部邮件即时提醒：数量 + 类型分布（会议记录/HR/需回复）+ 主题列表"""
        type_names = {
            'internal_meeting': '会议记录',
            'internal_hr': 'HR',
            'internal_reply': '需回复',
            'internal_other': '其他',
        }
        counts = {}
        for e in emails:
            name = type_names.get(e.category, '其他')
            counts[name] = counts.get(name, 0) + 1
        dist = ' · '.join(f'{name} {n}' for name, n in counts.items())

        lines = []
        lines.append(f"#### 📬 收到 {len(emails)} 封内部邮件（{dist}）")
        lines.append("")
        for i, e in enumerate(emails[:5], 1):
            type_name = self._internal_type_name(e.category)
            line = f"**{i}. {self._short_subject(e.subject)}**"
            if type_name:
                line += f" · {type_name}"
            line += f" · 来自 {self._short_sender(e.sender)}"
            lines.append(line)
            lines.append("")
            summary = self._short_summary(getattr(e, 'summary', ''))
            if summary:
                lines.append(f"> {summary}")
                lines.append("")
        if len(emails) > 5:
            lines.append(f"…还有 **{len(emails) - 5}** 封未展示")
            lines.append("")
        lines.append("**📧 [点击查看邮箱](https://qiye.aliyun.com/alimail/)**")

        self._send("📬 内部邮件提醒", '\n'.join(lines))

    def send_important_alert(self, email_msg):
        """发送重要邮件提醒：R2 图片版优先，失败回退纯文本"""
        if self._try_send_r2_alert(email_msg):
            return

        lines = []
        # 主题置顶；发件人普通行；时间+原因合并单行（钉钉会合并无空行分隔的连续行）；预览用单行引用块
        lines.append(f"#### 📌 {self._short_subject(email_msg.subject, max_len=30)}")
        lines.append("")
        lines.append(f"来自 {self._short_sender(email_msg.sender)}")
        lines.append("")
        detail = f"⏰ **{email_msg.date.strftime('%Y-%m-%d %H:%M')}**"
        if email_msg.match_reason:
            detail += f" · 原因：{_escape_md(email_msg.match_reason)}"
        lines.append(detail)
        if email_msg.body:
            body_preview = _escape_md(email_msg.body[:200].replace('\n', ' ').strip())
            lines.append("")
            lines.append(f"> {body_preview}…")
        lines.append("")
        lines.append("**📧 [点击查看邮箱](https://qiye.aliyun.com/alimail/)**")

        self._send("⭐ 重要邮件提醒", '\n'.join(lines))

    def _try_send_r2_alert(self, email_msg) -> bool:
        """尝试 R2 方案：生成提醒图片 → 上传 R2 → 钉钉发图片版；失败回退纯文本"""
        try:
            from report_generator import ReportGenerator
            from r2_uploader import R2Uploader

            uploader = R2Uploader()
            if not uploader.available:
                print("  -> R2 未配置完整，回退纯文本")
                return False

            generator = ReportGenerator()
            # 文件名带时间：同名覆盖会撞钉钉/浏览器缓存，且钉钉图片不支持 query 参数，故用唯一文件名防缓存
            ts_str = datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
            output_dir = generator.OUTPUT_DIR
            output_dir.mkdir(parents=True, exist_ok=True)
            image_path = generator.generate_alert_image(email_msg, str(output_dir / f'alert_{ts_str}.png'))
            if not image_path:
                print("  -> 提醒图片生成失败，回退纯文本")
                return False

            img_url = uploader.upload(image_path, f'alerts/{ts_str}.png')
            if not img_url:
                print("  -> R2 上传失败，回退纯文本")
                return False

            self._send_image_alert(email_msg, img_url)
            return True
        except Exception as e:
            print(f"  -> R2 方案异常: {e}，回退纯文本")
            return False

    def _send_image_alert(self, email_msg, img_url: str):
        """发送重要邮件提醒：内嵌图片 + 摘要引用 + 邮箱链接"""
        lines = []
        lines.append("#### 📌 重要邮件提醒")
        lines.append("")
        # alt 内嵌关键词 Email（钉钉安全设置要求），避免消息末尾出现 [Email] 行
        lines.append(f"![Email 重要邮件]({img_url})")
        lines.append("")
        summary = f"> ⏰ **{email_msg.date.strftime('%m月%d日 %H:%M')}** · 来自 {self._short_sender(email_msg.sender)}"
        if email_msg.match_reason:
            summary += f" · 原因：{_escape_md(email_msg.match_reason)}"
        lines.append(summary)
        lines.append("")
        lines.append("**📧 [打开邮箱处理](https://qiye.aliyun.com/alimail/)**")

        self._send("⭐ 重要邮件提醒", '\n'.join(lines))

    def send_invoice_alert(self, email_msg):
        """发送发票邮件提醒"""
        lines = []
        lines.append(f"#### 🧾 {self._short_subject(email_msg.subject, max_len=30)}")
        lines.append("")
        lines.append(f"来自 {self._short_sender(email_msg.sender)}")
        lines.append("")
        lines.append(f"⏰ **{email_msg.date.strftime('%Y-%m-%d %H:%M')}**")
        lines.append("")
        lines.append("**📧 [点击查看邮箱](https://qiye.aliyun.com/alimail/)**")

        self._send("🧾 发票邮件提醒", '\n'.join(lines))
