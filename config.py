"""配置管理模块 - 从 .env 文件加载配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)


class Config:
    """应用配置"""

    # 邮箱配置
    EMAIL_USER = os.getenv('EMAIL_USER', '')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
    IMAP_SERVER = os.getenv('IMAP_SERVER', 'imap.qiye.aliyun.com')
    IMAP_PORT = int(os.getenv('IMAP_PORT', 993))

    # 钉钉群机器人 Webhook
    DINGTALK_WEBHOOK = os.getenv('DINGTALK_WEBHOOK', '')

    # 调度配置
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 5))
    DAILY_REPORT_HOUR = int(os.getenv('DAILY_REPORT_HOUR', 9))
    DAILY_REPORT_MINUTE = int(os.getenv('DAILY_REPORT_MINUTE', 0))

    @classmethod
    def validate(cls) -> bool:
        """验证配置"""
        if not cls.EMAIL_USER:
            print("缺少配置: EMAIL_USER")
            return False
        if not cls.EMAIL_PASSWORD:
            print("缺少配置: EMAIL_PASSWORD")
            return False
        if not cls.DINGTALK_WEBHOOK:
            print("缺少配置: DINGTALK_WEBHOOK")
            return False
        return True
