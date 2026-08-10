"""通知模块 - 钉钉群机器人推送"""
import requests
from config import Config


class Notifier:
    """钉钉群机器人通知器"""

    KEYWORD = "Email"  # 钉钉机器人安全关键词

    def _send(self, title: str, content: str) -> bool:
        """向钉钉群推送 Markdown 消息"""
        try:
            # 钉钉 Markdown 格式
            md_text = f"### {title}\n\n{content}"
            # 确保消息包含关键词
            if self.KEYWORD not in md_text:
                md_text = f"[{self.KEYWORD}]\n{md_text}"

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
        """发送日报汇总"""
        total = len(analysis_result['total'])
        spam_emails = analysis_result['spam']
        important_emails = analysis_result['important']
        invoice_emails = analysis_result['invoice']
        normal_emails = analysis_result['normal']

        lines = []
        lines.append(f"- **总邮件数:** {total}")
        lines.append(f"- **垃圾邮件:** {len(spam_emails)}")
        lines.append(f"- **重要邮件:** {len(important_emails)}")
        lines.append(f"- **发票邮件:** {len(invoice_emails)}")
        lines.append(f"- **普通邮件:** {len(normal_emails)}")

        if important_emails:
            lines.append("")
            lines.append("**⭐ 重要邮件:**")
            for e in important_emails[:10]:
                lines.append(f"- {e.sender} | {e.subject}")
            if len(important_emails) > 10:
                lines.append(f"- ...还有 {len(important_emails) - 10} 封")

        if invoice_emails:
            lines.append("")
            lines.append("**🧾 发票邮件:**")
            for e in invoice_emails[:5]:
                lines.append(f"- {e.sender} | {e.subject}")

        if spam_emails:
            lines.append("")
            lines.append(f"**🗑️ 垃圾邮件({len(spam_emails)}封):**")
            for e in spam_emails[:10]:
                lines.append(f"- {e.sender} | {e.subject}")
            if len(spam_emails) > 10:
                lines.append(f"- ...还有 {len(spam_emails) - 10} 封")

        if normal_emails:
            lines.append("")
            lines.append(f"**📧 普通邮件({len(normal_emails)}封):**")
            for e in normal_emails[:10]:
                lines.append(f"- {e.sender} | {e.subject}")
            if len(normal_emails) > 10:
                lines.append(f"- ...还有 {len(normal_emails) - 10} 封")

        import datetime
        lines.append("")
        lines.append(f"⏰ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

        self._send("📊 邮件日报汇总", '\n'.join(lines))

    def send_important_alert(self, email_msg):
        """发送重要邮件提醒"""
        lines = []
        lines.append(f"- **发件人:** {email_msg.sender}")
        lines.append(f"- **主题:** {email_msg.subject}")
        lines.append(f"- **时间:** {email_msg.date.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"- **重要原因:** {email_msg.match_reason}")
        if email_msg.body:
            body_preview = email_msg.body[:150].replace('\n', ' ').strip()
            lines.append(f"- **内容摘要:** {body_preview}...")
        lines.append("")
        lines.append(f"[📧 点击查看邮箱](https://qiye.aliyun.com/alimail/)")

        self._send("⭐ 重要邮件提醒", '\n'.join(lines))

    def send_invoice_alert(self, email_msg):
        """发送发票邮件提醒"""
        lines = []
        lines.append(f"- **发件人:** {email_msg.sender}")
        lines.append(f"- **主题:** {email_msg.subject}")
        lines.append(f"- **时间:** {email_msg.date.strftime('%Y-%m-%d %H:%M')}")

        self._send("🧾 发票邮件提醒", '\n'.join(lines))
