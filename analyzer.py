"""邮件分析模块 - 分类邮件"""
import json
import re
from pathlib import Path
from typing import List, Dict
from email_client import EmailMessage
from config import Config


class EmailAnalyzer:
    """邮件分析器"""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """加载域名和关键词配置"""
        config_path = Path(__file__).parent / 'domains.json'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return {
                'internal_domains': [],
                'internal_meeting_keywords': [],
                'internal_hr_keywords': [],
                'internal_reply_keywords': [],
                'important_domains': [],
                'important_keywords': [],
                'spam_keywords': [],
                'invoice_keywords': []
            }
    
    # 内部邮件子类型：分类键 → (配置键, 类型名)，优先级按此顺序（会议 > HR > 需回复）
    INTERNAL_TYPES = [
        ('internal_meeting', 'internal_meeting_keywords', '会议记录'),
        ('internal_hr', 'internal_hr_keywords', 'HR'),
        ('internal_reply', 'internal_reply_keywords', '需回复'),
    ]

    def analyze_emails(self, emails: List[EmailMessage]) -> Dict[str, List[EmailMessage]]:
        """分析并分类邮件：先分内外（发件人域名），内部再按类型细分；
        内部邮件与外部重要邮件生成摘要"""
        result = {
            'total': emails,
            'internal_meeting': [],
            'internal_hr': [],
            'internal_reply': [],
            'internal_other': [],
            'important': [],
            'invoice': [],
            'spam': [],
            'external_normal': []
        }
        
        for email_msg in emails:
            category = self._classify_email(email_msg)
            email_msg.category = category
            # 内部邮件与外部重要邮件需要摘要
            if category.startswith('internal') or category == 'important':
                email_msg.summary = self._make_summary(email_msg.body)
            result[category].append(email_msg)
        
        return result
    
    def _classify_email(self, email_msg: EmailMessage) -> str:
        """分类单封邮件：内部域名 → 子类型；外部 → 发票 > 垃圾 > 重要"""
        subject = email_msg.subject.lower()
        body = email_msg.body.lower()
        domain = email_msg.sender_domain.lower()
        
        # 内部邮件（域名匹配 internal_domains）
        if self._is_internal(domain):
            for category, keywords_key, type_name in self.INTERNAL_TYPES:
                if self._match_keywords(subject, body, keywords_key):
                    email_msg.match_reason = f'内部-{type_name}关键词匹配'
                    return category
            email_msg.match_reason = '内部邮件'
            return 'internal_other'
        
        # 外部邮件：发票（优先级最高）→ 垃圾 → 重要
        if self._is_invoice(subject, body):
            email_msg.match_reason = '发票关键词匹配'
            return 'invoice'
        
        if self._is_spam(subject, body):
            email_msg.match_reason = '垃圾关键词匹配'
            return 'spam'
        
        reason = self._is_important(domain, subject, body)
        if reason:
            email_msg.match_reason = reason
            return 'important'
        
        # 外部邮件单独发送给本人（To 只有本账号、无抄送）→ 重要
        if self._is_solo_to_me(email_msg):
            email_msg.match_reason = '单独发送给我'
            return 'important'
        
        return 'external_normal'
    
    def _is_solo_to_me(self, email_msg: EmailMessage) -> bool:
        """检查外部邮件是否只单独发送给本人：To 只有本账号邮箱且无抄送"""
        my_email = Config.EMAIL_USER.lower()
        if not my_email:
            return False
        recipients = [r.lower() for r in getattr(email_msg, 'recipients', [])]
        cc = [c.lower() for c in getattr(email_msg, 'cc', [])]
        # 有抄送说明不是单独发送；To 为空或包含其他人则不算
        if cc or not recipients:
            return False
        return set(recipients) == {my_email}
    
    def _is_internal(self, domain: str) -> bool:
        """检查发件人域名是否为内部域名"""
        internal_domains = [d.lower() for d in self.config.get('internal_domains', [])]
        return any(domain == d or domain.endswith(f'.{d}') for d in internal_domains)
    
    def _match_keywords(self, subject: str, body: str, keywords_key: str) -> bool:
        """关键词匹配：中文关键词子串匹配；英文关键词单词边界匹配（避免 hr 误伤 share 等）"""
        keywords = self.config.get(keywords_key, [])
        text = f"{subject} {body}"
        for kw in keywords:
            kw = str(kw).lower()
            if not kw:
                continue
            if kw.isascii():
                if re.search(rf'\b{re.escape(kw)}\b', text):
                    return True
            elif kw in text:
                return True
        return False
    
    @staticmethod
    def _make_summary(body: str, max_len: int = 150) -> str:
        """生成摘要：截取正文开头并压缩空白"""
        text = ' '.join(body.split())
        if not text:
            return ''
        return text[:max_len] + ('…' if len(text) > max_len else '')
    
    def _is_invoice(self, subject: str, body: str) -> bool:
        """检查是否为发票邮件"""
        keywords = [k.lower() for k in self.config.get('invoice_keywords', [])]
        text = f"{subject} {body}"
        
        return any(keyword in text for keyword in keywords)
    
    def _is_important(self, domain: str, subject: str = '', body: str = '') -> str:
        """检查是否为重要邮件（域名匹配 或 关键词匹配），返回匹配原因或空字符串"""
        # 域名匹配
        important_domains = [d.lower() for d in self.config.get('important_domains', [])]
        for imp_domain in important_domains:
            if domain == imp_domain or domain.endswith(f'.{imp_domain}'):
                return f'域名匹配: {imp_domain}'
        
        # 关键词匹配（主题 + 正文）
        important_keywords = [k.lower() for k in self.config.get('important_keywords', [])]
        text = f"{subject} {body}"
        matched = [k for k in important_keywords if k in text]
        if matched:
            return f'关键词匹配: {", ".join(matched[:3])}'
        
        return ''
    
    def _is_spam(self, subject: str, body: str) -> bool:
        """检查是否为垃圾邮件（中文子串 / 英文单词边界匹配）"""
        keywords = [k.lower() for k in self.config.get('spam_keywords', [])]
        text = f"{subject} {body}"
        
        # 命中 2 个以上垃圾关键词才判定，降低误报（英文用单词边界，避免 sale 误伤 sales 等）
        match_count = 0
        for kw in keywords:
            if not kw:
                continue
            if kw.isascii():
                if re.search(rf'\b{re.escape(kw)}\b', text):
                    match_count += 1
            elif kw in text:
                match_count += 1
        return match_count >= 2
    
    def generate_report(self, analysis_result: Dict) -> str:
        """生成日报汇总"""
        total = len(analysis_result['total'])
        internal_emails = [
            e for key in ('internal_meeting', 'internal_hr', 'internal_reply', 'internal_other')
            for e in analysis_result[key]
        ]
        important_emails = analysis_result['important']
        invoice_emails = analysis_result['invoice']
        spam_count = len(analysis_result['spam'])
        
        report = []
        report.append(f"📊 邮件日报汇总")
        report.append(f"━━━━━━━━━━━━━━━━━━")
        report.append(f"")
        report.append(f"📬 总邮件数: {total}")
        report.append(f"🏢 内部邮件: {len(internal_emails)}")
        report.append(f"🗑️ 垃圾邮件: {spam_count}")
        report.append(f"⭐ 外部重要邮件: {len(important_emails)}")
        report.append(f"🧾 发票邮件: {len(invoice_emails)}")
        report.append(f"")
        
        if internal_emails:
            report.append(f"🏢 内部邮件详情:")
            for email_msg in internal_emails[:10]:  # 最多显示10封
                report.append(f"  • {email_msg.sender}")
                report.append(f"    主题: {email_msg.subject}")
                report.append(f"    摘要: {email_msg.summary}")
            if len(internal_emails) > 10:
                report.append(f"  ... 还有 {len(internal_emails) - 10} 封")
            report.append(f"")
        
        if important_emails:
            report.append(f"⭐ 外部重要邮件详情:")
            for email_msg in important_emails[:10]:  # 最多显示10封
                report.append(f"  • {email_msg.sender}")
                report.append(f"    主题: {email_msg.subject}")
                report.append(f"    摘要: {email_msg.summary}")
            if len(important_emails) > 10:
                report.append(f"  ... 还有 {len(important_emails) - 10} 封")
            report.append(f"")
        
        if invoice_emails:
            report.append(f"🧾 发票邮件详情:")
            for email_msg in invoice_emails[:5]:  # 最多显示5封
                report.append(f"  • {email_msg.sender}")
                report.append(f"    主题: {email_msg.subject}")
            report.append(f"")
        
        report.append(f"━━━━━━━━━━━━━━━━━━")
        report.append(f"⏰ 报告生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        return '\n'.join(report)
    
    def format_important_alert(self, email_msg: EmailMessage) -> tuple:
        """格式化重要邮件提醒"""
        title = f"⭐ 重要邮件提醒"
        content = []
        content.append(f"收到重要邮件!")
        content.append(f"")
        content.append(f"发件人: {email_msg.sender}")
        content.append(f"主题: {email_msg.subject}")
        content.append(f"时间: {email_msg.date.strftime('%Y-%m-%d %H:%M')}")
        content.append(f"")
        if email_msg.body:
            # 截取前200字符作为预览
            preview = email_msg.body[:200].replace('\n', ' ')
            content.append(f"预览: {preview}...")
        
        return title, '\n'.join(content)
