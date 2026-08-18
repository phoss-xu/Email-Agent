"""邮件客户端模块 - IMAP 连接与邮件读取"""
import imaplib
import email.message
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime, getaddresses
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import re

from config import Config


@dataclass
class EmailMessage:
    """邮件消息数据结构"""
    message_id: str
    subject: str
    sender: str
    sender_domain: str
    date: datetime
    body: str
    is_read: bool = False
    recipients: List[str] = field(default_factory=list)  # To 收件人邮箱地址（小写）
    cc: List[str] = field(default_factory=list)          # Cc 抄送邮箱地址（小写）
    # 分类取值：internal_meeting / internal_hr / internal_reply / internal_other（内部），
    # important / invoice / spam / external_normal（外部，external_normal 只计数不展示明细）
    category: str = 'external_normal'
    match_reason: str = ''    # 匹配原因
    summary: str = ''         # 摘要（内部邮件与外部重要邮件，截取正文开头）
    
    def __str__(self) -> str:
        return f"[{self.sender}] {self.subject}"


class EmailClient:
    """IMAP 邮件客户端"""
    
    def __init__(self):
        self.config = Config
        self.connection: Optional[imaplib.IMAP4_SSL] = None
    
    def connect(self) -> bool:
        """连接到 IMAP 服务器"""
        try:
            self.connection = imaplib.IMAP4_SSL(
                self.config.IMAP_SERVER,
                self.config.IMAP_PORT
            )
            self.connection.login(
                self.config.EMAIL_USER,
                self.config.EMAIL_PASSWORD
            )
            return True
        except Exception as e:
            print(f"连接邮箱失败: {e}")
            self.connection = None
            return False
    
    def _ensure_connected(self) -> bool:
        """确保连接可用，断开则自动重连"""
        if self.connection:
            try:
                # 发送 NOOP 检测连接是否存活
                self.connection.noop()
                return True
            except Exception:
                print("  -> IMAP 连接已断开，尝试重连...")
                self.disconnect()
                self.connection = None
        return self.connect()
    
    def disconnect(self):
        """断开连接"""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
            except:
                pass
    
    def _decode_header(self, header_value: str) -> str:
        """解码邮件头"""
        if not header_value:
            return ''
        
        decoded_parts = []
        for content, charset in decode_header(header_value):
            if isinstance(content, bytes):
                try:
                    decoded_parts.append(content.decode(charset or 'utf-8', errors='ignore'))
                except:
                    decoded_parts.append(content.decode('utf-8', errors='ignore'))
            else:
                decoded_parts.append(content)
        
        return ''.join(decoded_parts)
    
    def _extract_email_domain(self, email_addr: str) -> str:
        """从邮箱地址提取域名"""
        match = re.search(r'<(.+?)>', email_addr)
        if match:
            email_addr = match.group(1)
        
        if '@' in email_addr:
            return email_addr.split('@')[1].lower()
        return ''
    
    def _get_body(self, msg: email.message.Message) -> str:
        """提取邮件正文"""
        body = ''
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='ignore')
                        break
                    except:
                        pass
                elif content_type == 'text/html' and not body:
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        html = part.get_payload(decode=True).decode(charset, errors='ignore')
                        # 简单去除 HTML 标签
                        body = re.sub(r'<[^>]+>', '', html)
                    except:
                        pass
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='ignore')
            except:
                pass
        
        return body[:2000]  # 限制正文长度
    
    def fetch_recent_emails(self, hours: int = 24) -> List[EmailMessage]:
        """获取过去 N 小时收到的邮件（含断线重连）
    
        策略：IMAP SINCE 按天粗筛（取昨天，覆盖 24h 窗口起点之前的邮件），
        再用服务器接收时间 INTERNALDATE 精确过滤，避免邮件头 Date 不可靠的问题。
        """
        if not self._ensure_connected():
            return []
    
        since_date = date.today() - timedelta(days=1)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
        try:
            return self._do_fetch(since_date, min_received_time=cutoff)
        except Exception as e:
            print(f"获取邮件失败: {e}，尝试重连...")
            self.disconnect()
            self.connection = None
            if self._ensure_connected():
                try:
                    return self._do_fetch(since_date, min_received_time=cutoff)
                except Exception as e2:
                    print(f"重试仍失败: {e2}")
            return []
    
    @staticmethod
    def _extract_internaldate(msg_data) -> Optional[datetime]:
        """从 IMAP fetch 响应解析服务器接收时间（INTERNALDATE），解析失败返回 None"""
        for item in msg_data:
            if isinstance(item, tuple) and item[0]:
                m = re.search(rb'INTERNALDATE "([^"]+)"', item[0])
                if m:
                    try:
                        return parsedate_to_datetime(m.group(1).decode())
                    except:
                        return None
        return None
    
    def _do_fetch(self, since_date: date, min_received_time: Optional[datetime] = None) -> List[EmailMessage]:
        """实际执行邮件拉取；min_received_time 非空时按服务器接收时间过滤（UTC aware）"""
        self.connection.select('INBOX')
    
        # 搜索指定日期后的邮件
        date_str = since_date.strftime('%d-%b-%Y')
        status, messages = self.connection.search(None, f'(SINCE {date_str})')
    
        if status != 'OK':
            return []
    
        email_list = []
        msg_ids = messages[0].split()
    
        for msg_id in msg_ids:
            try:
                # 带 INTERNALDATE：获取服务器接收时间，用于 24h 精确过滤
                status, msg_data = self.connection.fetch(msg_id, '(RFC822 INTERNALDATE)')
                if status != 'OK':
                    continue
    
                # 24h 过滤：INTERNALDATE 解析失败时保留（宽松处理，宁可多显示）
                if min_received_time is not None:
                    received = self._extract_internaldate(msg_data)
                    if received is not None and received.astimezone(timezone.utc) < min_received_time:
                        continue
                
                raw_email = msg_data[0][1]
                msg = message_from_bytes(raw_email)
                
                # 解析邮件头
                subject = self._decode_header(msg.get('Subject', ''))
                sender = self._decode_header(msg.get('From', ''))
                sender_domain = self._extract_email_domain(sender)
                message_id = msg.get('Message-ID', '')
                if not message_id:
                    # 部分邮件（如 SMTP 测试邮件）无 Message-ID 头：用 IMAP 序号作回退唯一标识（当日稳定，供去重）
                    message_id = f'uid-{msg_id.decode()}'
                
                # 解析收件人/抄送（仅取邮箱地址，小写归一）
                recipients = [addr.lower() for _, addr in getaddresses([msg.get('To', '')]) if addr]
                cc = [addr.lower() for _, addr in getaddresses([msg.get('Cc', '')]) if addr]
                
                # 解析日期
                date_str = msg.get('Date', '')
                try:
                    email_date = parsedate_to_datetime(date_str)
                except:
                    email_date = datetime.now()
                
                # 提取正文
                body = self._get_body(msg)
                
                email_msg = EmailMessage(
                    message_id=message_id,
                    subject=subject,
                    sender=sender,
                    sender_domain=sender_domain,
                    date=email_date,
                    body=body,
                    recipients=recipients,
                    cc=cc,
                )
                email_list.append(email_msg)
                
            except Exception as e:
                print(f"解析邮件失败: {e}")
                continue
        
        return email_list
