"""调度器模块 - 定时任务管理 + IMAP IDLE 实时监听"""
import json
import time
import socket
import threading
import imaplib
from pathlib import Path
from datetime import datetime, date
from typing import Set
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import Config
from email_client import EmailClient, EmailMessage
from analyzer import EmailAnalyzer
from notifier import Notifier


class EmailScheduler:
    """邮件调度器：IMAP IDLE 实时监听为主，定时轮询为兜底，每日日报定时推送"""
    
    IDLE_TIMEOUT = 20 * 60  # IDLE 单次最长等待秒数（服务器空闲断开通常 30 分钟，保守 20 分钟重来）
    RECONNECT_DELAY = 5     # IDLE 连接异常后的重连间隔（秒）
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.client = EmailClient()
        self.analyzer = EmailAnalyzer()
        self.notifier = Notifier()
        self.notified_ids = self._load_notified_ids()
        self._stop_flag = False
    
    def _get_cache_path(self) -> Path:
        """获取缓存文件路径（优先使用 data 目录）"""
        data_dir = Path(__file__).parent / 'data'
        data_dir.mkdir(exist_ok=True)
        return data_dir / 'notified_cache.json'
    
    def _load_notified_ids(self) -> Set[str]:
        """加载已通知的邮件ID"""
        cache_file = self._get_cache_path()
        try:
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    today = date.today().isoformat()
                    if data.get('date') == today:
                        return set(data.get('ids', []))
        except:
            pass
        return set()
    
    def _save_notified_ids(self):
        """保存已通知的邮件ID"""
        cache_file = self._get_cache_path()
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'date': date.today().isoformat(),
                    'ids': list(self.notified_ids)
                }, f)
        except Exception as e:
            print(f"保存缓存失败: {e}")
    
    def daily_report(self):
        """执行日报任务"""
        print(f"\n[{datetime.now()}] 执行日报任务...")
        
        emails = self.client.fetch_recent_emails()
        
        if not emails:
            print("过去 24 小时没有新邮件")
            return
        
        analysis_result = self.analyzer.analyze_emails(emails)
        self.notifier.send_daily_report(analysis_result)
        
        print(f"日报已发送: 共 {len(emails)} 封邮件")
    
    def check_important_emails(self):
        """检查新邮件（实时检测）：外部重要/发票即时提醒 + 内部邮件数量/类型提醒"""
        print(f"[{datetime.now()}] 检查新邮件...")
        
        try:
            emails = self.client.fetch_recent_emails()
            analysis_result = self.analyzer.analyze_emails(emails)
            important_emails = analysis_result['important']
            invoice_emails = analysis_result['invoice']
            
            new_important = [
                e for e in important_emails 
                if e.message_id and e.message_id not in self.notified_ids
            ]
            new_invoice = [
                e for e in invoice_emails
                if e.message_id and e.message_id not in self.notified_ids
            ]
            # 内部邮件（会议记录/HR/需回复/其他）同样即时提醒，汇总数量与类型分布
            new_internal = [
                e for key in ('internal_meeting', 'internal_hr', 'internal_reply', 'internal_other')
                for e in analysis_result[key]
                if e.message_id and e.message_id not in self.notified_ids
            ]
            
            has_new = False
            
            if new_important:
                has_new = True
                print(f"发现 {len(new_important)} 封新重要邮件")
                for email_msg in new_important:
                    self.notifier.send_important_alert(email_msg)
                    if email_msg.message_id:
                        self.notified_ids.add(email_msg.message_id)
            
            if new_invoice:
                has_new = True
                print(f"发现 {len(new_invoice)} 封新发票邮件")
                for email_msg in new_invoice:
                    self.notifier.send_invoice_alert(email_msg)
                    if email_msg.message_id:
                        self.notified_ids.add(email_msg.message_id)
            
            if new_internal:
                has_new = True
                print(f"发现 {len(new_internal)} 封新内部邮件")
                # IDLE 模式：来一封发一封，每封邮件单独一条提醒
                for email_msg in new_internal:
                    self.notifier.send_internal_alert(email_msg)
                    if email_msg.message_id:
                        self.notified_ids.add(email_msg.message_id)
            
            if has_new:
                self._save_notified_ids()
            else:
                print("没有新的重要/发票邮件")
                
        except Exception as e:
            print(f"检查邮件异常: {e}")
    
    def _drain(self, conn) -> bool:
        """清空连接上积压的 untagged 通知并返回是否有邮件通知。
        DONE 后/检测期间服务器仍可能推送 * N EXISTS（IMAP 允许随时发送 untagged 响应），
        若不及时读取会积压导致服务器断开连接（实测 IDLE 响应异常 b''）。
        """
        has_notice = False
        conn.sock.settimeout(0.3)
        try:
            while True:
                try:
                    chunk = conn.sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break  # 连接已关闭（EOF），由外层重连逻辑处理
                if b'EXISTS' in chunk or b'RECENT' in chunk:
                    has_notice = True
        except OSError:
            pass
        finally:
            conn.sock.settimeout(30)
        return has_notice

    def _idle_listener(self):
        """IMAP IDLE 长连接监听：新邮件到达时服务器主动通知，立即触发检测（秒级响应）。
        使用独立连接，不干扰 EmailClient 的 fetch 连接；异常自动重连；
        定时轮询（IntervalTrigger）保留作为兜底，防止 IDLE 通知丢失。
        """
        while not self._stop_flag:
            conn = None
            try:
                conn = imaplib.IMAP4_SSL(Config.IMAP_SERVER, Config.IMAP_PORT, timeout=30)
                conn.login(Config.EMAIL_USER, Config.EMAIL_PASSWORD)
                conn.select('INBOX')
                print(f"[{datetime.now()}] 📡 IDLE 实时监听已建立（新邮件秒级触发）")
                
                while not self._stop_flag:
                    try:
                        # 进入 IDLE 前清空积压的 untagged 通知（避免连接状态错乱被服务器断开）
                        if self._drain(conn):
                            print(f"[{datetime.now()}] 📨 清空积压通知（检测期间有新邮件），立即检测")
                            self.check_important_emails()
                        
                        # 进入 IDLE（必须带 tag：RFC 2177，无 tag 会被解析为空命令返回 BAD）；
                        # 服务器在新邮件到达时推送 * N EXISTS 通知，并返回 '+ idling' 续行提示
                        idle_tag = conn._new_tag().decode('ascii')
                        conn.send(f'{idle_tag} IDLE\r\n'.encode())
                        # 服务器可能在 '+ idling' 之前先推送 untagged 通知（EXPUNGE/EXISTS 等），
                        # 需循环跳过直到出现续行提示，否则会被误判为响应异常断开连接
                        try:
                            resp = conn.readline()
                            while resp and b'+ idling' not in resp:
                                notice = resp.decode(errors='ignore').strip()
                                if notice:
                                    print(f"[{datetime.now()}] 📨 进入 IDLE 前收到通知: {notice}")
                                resp = conn.readline()
                        except socket.timeout:
                            resp = b''
                        if b'+ idling' not in resp:
                            print(f"IDLE 响应异常: {resp}")
                            break
                        
                        conn.sock.settimeout(self.IDLE_TIMEOUT)
                        try:
                            data = conn.readline()  # 阻塞等待服务器通知或超时
                        except socket.timeout:
                            # 单次 IDLE 超时：发送 DONE 后重新进入，保活连接
                            conn.send(b'DONE\r\n')
                            conn.readline()
                            conn.sock.settimeout(30)
                            continue
                        
                        # 收到通知（EXISTS/RECENT 等），结束本次 IDLE
                        conn.send(b'DONE\r\n')
                        conn.readline()
                        conn.sock.settimeout(30)
                        
                        if data:
                            notice = data.decode(errors='ignore').strip()
                            print(f"[{datetime.now()}] 📨 IDLE 收到通知: {notice}，立即检测")
                            try:
                                self.check_important_emails()
                            except Exception as e:
                                print(f"IDLE 触发检测异常: {e}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"IDLE 会话异常: {e}")
                        break
                
            except Exception as e:
                print(f"IDLE 连接异常: {e}")
            finally:
                if conn:
                    try:
                        conn.logout()
                    except Exception:
                        pass
            
            if not self._stop_flag:
                print(f"[{datetime.now()}] {self.RECONNECT_DELAY} 秒后重连 IDLE...")
                time.sleep(self.RECONNECT_DELAY)

    def start(self):
        """启动调度器"""
        if not Config.validate():
            return
        
        self.scheduler.add_job(
            self.daily_report,
            CronTrigger(hour=Config.DAILY_REPORT_HOUR, minute=Config.DAILY_REPORT_MINUTE),
            id='daily_report',
            name='每日邮件汇总'
        )
        
        # 定时轮询保留为兜底（IDLE 失效或通知丢失时仍有检测）
        self.scheduler.add_job(
            self.check_important_emails,
            IntervalTrigger(minutes=Config.CHECK_INTERVAL),
            id='check_important',
            name='重要邮件兜底检测'
        )
        
        report_time = f"{Config.DAILY_REPORT_HOUR:02d}:{Config.DAILY_REPORT_MINUTE:02d}"
        print("=" * 50)
        print("📧 邮件监控系统已启动")
        print(f"⏰ 日报时间: 每天 {report_time}")
        print(f"📡 实时监听: IMAP IDLE（新邮件秒级触发）")
        print(f"🔄 兜底轮询: {Config.CHECK_INTERVAL} 分钟")
        print(f"📮 邮箱: {Config.EMAIL_USER}")
        print(f"🔔 推送: 钉钉群机器人")
        print("=" * 50)
        
        print("\n执行首次检测...")
        self.check_important_emails()
        
        # 启动 IDLE 实时监听线程（守护线程，进程退出自动结束）
        idle_thread = threading.Thread(target=self._idle_listener, daemon=True, name='imap-idle')
        idle_thread.start()
        
        self.scheduler.start()
        
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.stop()
    
    def stop(self):
        """停止调度器"""
        print("\n正在关闭监控系统...")
        self._stop_flag = True
        self.client.disconnect()
        self.scheduler.shutdown()
        print("已停止")
