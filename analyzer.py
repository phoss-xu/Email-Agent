"""邮件分析模块 - 分类邮件"""
import json
from pathlib import Path
from typing import List, Dict
from email_client import EmailMessage


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
                'important_domains': [],
                'spam_keywords': [],
                'invoice_keywords': []
            }
    
    def analyze_emails(self, emails: List[EmailMessage]) -> Dict[str, List[EmailMessage]]:
        """分析并分类邮件"""
        result = {
            'total': emails,
            'spam': [],
            'important': [],
            'invoice': [],
            'normal': []
        }
        
        for email_msg in emails:
            category = self._classify_email(email_msg)
            email_msg.category = category
            result[category].append(email_msg)
        
        return result
    
    def _classify_email(self, email_msg: EmailMessage) -> str:
        """分类单封邮件"""
        subject = email_msg.subject.lower()
        body = email_msg.body.lower()
        domain = email_msg.sender_domain.lower()
        
        # 检查是否为发票邮件（优先级最高）
        if self._is_invoice(subject, body):
            email_msg.match_reason = '发票关键词匹配'
            return 'invoice'
        
        # 检查是否为重要邮件（域名匹配 或 关键词匹配）
        reason = self._is_important(domain, subject, body)
        if reason:
            email_msg.match_reason = reason
            return 'important'
        
        # 检查是否为垃圾邮件
        if self._is_spam(subject, body):
            email_msg.match_reason = '垃圾关键词匹配'
            return 'spam'
        
        return 'normal'
    
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
        """检查是否为垃圾邮件"""
        keywords = [k.lower() for k in self.config.get('spam_keywords', [])]
        text = f"{subject} {body}"
        
        # 如果匹配到3个以上垃圾关键词，判定为垃圾邮件
        match_count = sum(1 for keyword in keywords if keyword in text)
        return match_count >= 2
    
    def generate_report(self, analysis_result: Dict) -> str:
        """生成日报汇总"""
        total = len(analysis_result['total'])
        spam_count = len(analysis_result['spam'])
        important_emails = analysis_result['important']
        invoice_emails = analysis_result['invoice']
        
        report = []
        report.append(f"📊 邮件日报汇总")
        report.append(f"━━━━━━━━━━━━━━━━━━")
        report.append(f"")
        report.append(f"📬 总邮件数: {total}")
        report.append(f"🗑️ 垃圾邮件: {spam_count}")
        report.append(f"⭐ 重要邮件: {len(important_emails)}")
        report.append(f"🧾 发票邮件: {len(invoice_emails)}")
        report.append(f"")
        
        if important_emails:
            report.append(f"⭐ 重要邮件详情:")
            for email_msg in important_emails[:10]:  # 最多显示10封
                report.append(f"  • {email_msg.sender}")
                report.append(f"    主题: {email_msg.subject}")
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
