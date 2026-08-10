"""调度器模块 - 定时任务管理"""
import json
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
    """邮件调度器"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.client = EmailClient()
        self.analyzer = EmailAnalyzer()
        self.notifier = Notifier()
        self.notified_ids = self._load_notified_ids()
    
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
        
        emails = self.client.fetch_today_emails()
        
        if not emails:
            print("今天没有新邮件")
            return
        
        analysis_result = self.analyzer.analyze_emails(emails)
        self.notifier.send_daily_report(analysis_result)
        
        print(f"日报已发送: 共 {len(emails)} 封邮件")
    
    def check_important_emails(self):
        """检查重要邮件和发票邮件（实时检测）"""
        print(f"[{datetime.now()}] 检查新邮件...")
        
        try:
            emails = self.client.fetch_today_emails()
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
            
            if has_new:
                self._save_notified_ids()
            else:
                print("没有新的重要/发票邮件")
                
        except Exception as e:
            print(f"检查邮件异常: {e}")
    
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
        
        self.scheduler.add_job(
            self.check_important_emails,
            IntervalTrigger(minutes=Config.CHECK_INTERVAL),
            id='check_important',
            name='重要邮件实时检测'
        )
        
        report_time = f"{Config.DAILY_REPORT_HOUR:02d}:{Config.DAILY_REPORT_MINUTE:02d}"
        print("=" * 50)
        print("📧 邮件监控系统已启动")
        print(f"⏰ 日报时间: 每天 {report_time}")
        print(f"🔄 检测间隔: {Config.CHECK_INTERVAL} 分钟")
        print(f"📮 邮箱: {Config.EMAIL_USER}")
        print(f"🔔 推送: 钉钉群机器人")
        print("=" * 50)
        
        print("\n执行首次检测...")
        self.check_important_emails()
        
        self.scheduler.start()
        
        try:
            import time
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.stop()
    
    def stop(self):
        """停止调度器"""
        print("\n正在关闭监控系统...")
        self.client.disconnect()
        self.scheduler.shutdown()
        print("已停止")
