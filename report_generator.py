"""日报图片生成模块 - HTML模板渲染 + Playwright截图"""
import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class ReportGenerator:
    """日报图片生成器"""

    TEMPLATE_PATH = Path(__file__).parent / 'templates' / 'report.html'
    ALERT_TEMPLATE_PATH = Path(__file__).parent / 'templates' / 'alert.html'
    OUTPUT_DIR = Path(__file__).parent / 'data' / 'reports'

    # 分类 → (标记色, 行标签样式, 标签文字, 锚点前缀, 图标)
    SECTION_STYLES = {
        'important': ('var(--red)', 'tag-imp', '重要', 'imp', '⭐'),
        'invoice': ('var(--orange)', 'tag-inv', '发票', 'inv', '🧾'),
        'spam': ('var(--gray)', 'tag-spm', '垃圾', 'spm', '🗑️'),
    }

    # 内部邮件子类型 → (子标题, 行标签样式, 标签文字, 锚点前缀, 图标)
    INTERNAL_STYLES = {
        'internal_meeting': ('会议记录', 'tag-mtg', '会议', 'int-m', '📝'),
        'internal_hr': ('HR', 'tag-hr', 'HR', 'int-h', '👤'),
        'internal_reply': ('需回复', 'tag-reply', '需回复', 'int-r', '✉️'),
    }

    @staticmethod
    def _sender_name(sender: str) -> str:
        """从 From 头提取显示名称：'name <email>' → 'name'；无名称时退回邮箱前缀"""
        if '<' in sender:
            name = sender.split('<')[0].strip().strip('"')
            if name:
                return name
            email = sender[sender.find('<') + 1:sender.find('>')]
            return email.split('@')[0] if email else sender
        if '@' in sender:
            return sender.split('@')[0]
        return sender

    def _build_email_section(self, emails: List[Any], title: str, style_key: str,
                             show_summary: bool = False) -> str:
        """构建 Tufte 分组区块：分组小标题 + 分栏表格（主题/发件人/类）；
        show_summary=True 时每行追加摘要（用于外部重要邮件）"""
        if not emails:
            return ''

        _, tag_cls, tag_text, anchor_prefix, icon = self.SECTION_STYLES[style_key]
        is_spam = style_key == 'spam'
        group_cls = 'group spam-g' if is_spam else 'group'
        row_cls = 'trow spam-row' if is_spam else 'trow'

        html_parts = []
        html_parts.append(f'<div class="{group_cls}">')
        html_parts.append(f'  <span class="gname"><span class="icon">{icon}</span>{title}</span>')
        html_parts.append(f'  <span class="gcount">共 <b>{len(emails)}</b> 封</span>')
        html_parts.append(f'</div>')
        html_parts.append(f'<div class="table">')
        html_parts.append(f'  <div class="table-head">')
        html_parts.append(f'    <span class="c-subject">主题</span>')
        html_parts.append(f'    <span class="c-from">发件人</span>')
        html_parts.append(f'    <span class="c-tag">类</span>')
        html_parts.append(f'  </div>')

        # 每行带锚点 id（如 imp-1），供钉钉消息链接跳转到具体邮件
        for i, e in enumerate(emails[:10], 1):
            html_parts.append(f'  <div class="{row_cls}" id="{anchor_prefix}-{i}">')
            html_parts.append(f'    <span class="c-subject">{self._escape(e.subject)}</span>')
            html_parts.append(f'    <span class="c-from">{self._escape(self._sender_name(e.sender))}</span>')
            html_parts.append(f'    <span class="c-tag {tag_cls}">{tag_text}</span>')
            html_parts.append(f'  </div>')
            if show_summary and getattr(e, 'summary', ''):
                html_parts.append(f'  <div class="c-summary">{self._escape(e.summary)}</div>')

        if len(emails) > 10:
            html_parts.append(f'  <div class="empty-hint">… 还有 {len(emails) - 10} 封</div>')

        html_parts.append(f'</div>')
        return '\n'.join(html_parts)

    def _build_internal_section(self, analysis_result: Dict) -> str:
        """构建内部邮件区块：总标题 + 各子类型小节（主题/发件人 + 摘要）"""
        internal_keys = ('internal_meeting', 'internal_hr', 'internal_reply')
        emails_by_type = {key: analysis_result.get(key, []) for key in internal_keys}
        other_emails = analysis_result.get('internal_other', [])
        total = sum(len(v) for v in emails_by_type.values()) + len(other_emails)
        if total == 0:
            return ''

        html_parts = []
        html_parts.append(f'<div class="group">')
        html_parts.append(f'  <span class="gname"><span class="icon">🏢</span>内部邮件</span>')
        html_parts.append(f'  <span class="gcount">共 <b>{total}</b> 封</span>')
        html_parts.append(f'</div>')

        for key, (sub_title, tag_cls, tag_text, anchor_prefix, icon) in self.INTERNAL_STYLES.items():
            emails = emails_by_type[key]
            if not emails:
                continue
            html_parts.append(f'<div class="subgroup">')
            html_parts.append(f'  <span class="sname"><span class="icon">{icon}</span>{sub_title}</span>')
            html_parts.append(f'  <span class="scount">共 <b>{len(emails)}</b> 封</span>')
            html_parts.append(f'</div>')
            html_parts.append(f'<div class="table">')
            for i, e in enumerate(emails[:10], 1):
                html_parts.append(f'  <div class="trow" id="{anchor_prefix}-{i}">')
                html_parts.append(f'    <span class="c-subject">{self._escape(e.subject)}</span>')
                html_parts.append(f'    <span class="c-from">{self._escape(self._sender_name(e.sender))}</span>')
                html_parts.append(f'    <span class="c-tag {tag_cls}">{tag_text}</span>')
                html_parts.append(f'  </div>')
                if getattr(e, 'summary', ''):
                    html_parts.append(f'  <div class="c-summary">{self._escape(e.summary)}</div>')
            if len(emails) > 10:
                html_parts.append(f'  <div class="empty-hint">… 还有 {len(emails) - 10} 封</div>')
            html_parts.append(f'</div>')

        return '\n'.join(html_parts)

    @staticmethod
    def _build_overview_items(analysis_result: Dict) -> str:
        """构建概览明细：内部 N（会议 x · HR x · 需回复 x）｜ 外部 N（重要 x · 发票 x · 垃圾 x）"""
        internal_total = sum(len(analysis_result.get(k, [])) for k in
                             ('internal_meeting', 'internal_hr', 'internal_reply', 'internal_other'))
        external_total = len(analysis_result.get('total', [])) - internal_total

        parts = []
        if internal_total:
            sub = ' · '.join(
                f'{name} {len(analysis_result.get(key, []))}'
                for key, name in (('internal_meeting', '会议'), ('internal_hr', 'HR'), ('internal_reply', '需回复'))
                if analysis_result.get(key)
            )
            parts.append(f'<span class="k">🏢 内部</span> <b>{internal_total}</b>' + (f'（{sub}）' if sub else ''))
        if external_total:
            sub = ' · '.join(
                f'{name} {len(analysis_result.get(key, []))}'
                for key, name in (('important', '重要'), ('invoice', '发票'), ('spam', '垃圾'))
                if analysis_result.get(key)
            )
            parts.append(f'<span class="k">🌐 外部</span> <b>{external_total}</b>' + (f'（{sub}）' if sub else ''))
        return ' ｜ '.join(parts)

    def _escape(self, text: str) -> str:
        """HTML转义"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def _render_html(self, analysis_result: Dict) -> str:
        """将分析结果渲染为HTML"""
        template = self.TEMPLATE_PATH.read_text(encoding='utf-8')

        total = len(analysis_result['total'])
        important = analysis_result['important']
        invoice = analysis_result['invoice']
        spam = analysis_result['spam']

        now = datetime.now()
        weekday_map = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        weekday = weekday_map[now.weekday()]
        date_str = f'{now.year}年{now.month}月{now.day}日 {weekday}'
        time_str = now.strftime('%H:%M')

        # 构建分类区块（空分类不渲染）
        internal_section = self._build_internal_section(analysis_result)
        important_section = self._build_email_section(important, '外部重要邮件', 'important', show_summary=True)
        invoice_section = self._build_email_section(invoice, '发票邮件', 'invoice')
        spam_section = self._build_email_section(spam, '已拦截垃圾', 'spam')

        # 替换模板占位符
        html = template.replace('{{TITLE}}', '邮件日报')
        html = html.replace('{{DATE}}', date_str)
        html = html.replace('{{TIME}}', time_str)
        html = html.replace('{{TOTAL_COUNT}}', str(total))
        html = html.replace('{{SPAM_COUNT}}', str(len(spam)))
        html = html.replace('{{OVERVIEW_ITEMS}}', self._build_overview_items(analysis_result))
        html = html.replace('{{REPORT_URL}}', '#')
        html = html.replace('{{INTERNAL_SECTION}}', internal_section)
        html = html.replace('{{IMPORTANT_SECTION}}', important_section)
        html = html.replace('{{INVOICE_SECTION}}', invoice_section)
        html = html.replace('{{SPAM_SECTION}}', spam_section)

        return html

    async def _screenshot_async(self, html_content: str, output_path: Path) -> bool:
        """异步截图"""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                # 3x 分辨率截图：覆盖手机 Retina 屏最高物理像素密度（iPhone 3x），钉钉展示极限清晰
                page = await browser.new_page(
                    viewport={'width': 480, 'height': 800},
                    device_scale_factor=3,
                )
                await page.set_content(html_content, wait_until='networkidle')

                # 获取页面实际高度（Tufte 版无卡片容器，直接截 body）
                body = await page.query_selector('body')
                if body:
                    box = await body.bounding_box()
                    if box:
                        await page.set_viewport_size({
                            'width': 480,
                            'height': int(box['height'])
                        })
                        await body.screenshot(path=str(output_path))
                    else:
                        await page.screenshot(path=str(output_path), full_page=True)
                else:
                    await page.screenshot(path=str(output_path), full_page=True)

                await browser.close()
                return True

        except Exception as e:
            print(f"  -> 截图失败: {e}")
            return False

    def _render_alert_html(self, email_msg: Any) -> str:
        """渲染单封重要邮件提醒 HTML（Tufte 系列：刊头 + 主题 + 发件人信息 + 红字批注原因 + 正文预览）"""
        template = self.ALERT_TEMPLATE_PATH.read_text(encoding='utf-8')
        now = datetime.now()

        subject = self._escape(email_msg.subject) if email_msg.subject else '（无主题）'
        sender_name = self._escape(self._sender_name(email_msg.sender)) if email_msg.sender else '未知发件人'
        domain = self._escape(email_msg.sender_domain) if email_msg.sender_domain else ''

        if email_msg.date:
            date_time = f'{email_msg.date.month}月{email_msg.date.day}日 {email_msg.date.strftime("%H:%M")}'
        else:
            date_time = '时间未知'

        reason = self._escape(email_msg.match_reason) if email_msg.match_reason else '重要邮件规则匹配'

        # 正文预览：前 200 字符，换行转 <br>（模板内已转义过 HTML 特殊字符）
        body = ''
        if email_msg.body:
            body = self._escape(email_msg.body[:200].strip())
            body = body.replace('\n', '<br>')

        html = template.replace('{{TIME}}', now.strftime('%H:%M'))
        html = html.replace('{{SUBJECT}}', subject)
        html = html.replace('{{SENDER_NAME}}', sender_name)
        html = html.replace('{{SENDER_DOMAIN}}', domain)
        html = html.replace('{{DATE_TIME}}', date_time)
        html = html.replace('{{REASON}}', reason)
        html = html.replace('{{BODY_PREVIEW}}', body)
        html = html.replace('{{MAILBOX_URL}}', 'https://qiye.aliyun.com/alimail/')
        return html

    def generate_alert_image(self, email_msg: Any, output_path: str) -> Optional[str]:
        """
        生成单封重要邮件提醒图片，返回图片路径。
        失败返回 None。
        """
        try:
            html_content = self._render_alert_html(email_msg)
            success = asyncio.run(self._screenshot_async(html_content, Path(output_path)))
            if success and Path(output_path).exists():
                print(f"  -> 提醒图片已生成: {output_path}")
                return str(output_path)
            return None
        except Exception as e:
            print(f"  -> 提醒图片生成失败: {e}")
            return None

    def generate_html(self, analysis_result: Dict) -> Optional[str]:
        """
        渲染并保存日报 HTML，返回文件路径。
        失败返回 None。
        """
        try:
            self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            html_content = self._render_html(analysis_result)
            html_path = self.OUTPUT_DIR / 'latest_report.html'
            html_path.write_text(html_content, encoding='utf-8')
            return str(html_path)
        except Exception as e:
            print(f"  -> HTML 生成失败: {e}")
            return None

    def generate_image(self, analysis_result: Dict) -> Optional[str]:
        """
        生成日报图片，返回图片路径。
        失败返回 None。
        """
        html_path = self.generate_html(analysis_result)
        if not html_path:
            return None

        # 截图
        output_path = self.OUTPUT_DIR / 'daily_report.png'
        html_content = Path(html_path).read_text(encoding='utf-8')
        success = asyncio.run(self._screenshot_async(html_content, output_path))

        if success and output_path.exists():
            print(f"  -> 日报图片已生成: {output_path}")
            return str(output_path)
        return None
