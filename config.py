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

    # 图片上传配置（日报图片托管）
    # 默认使用 sm.ms 免费图床，也可配置自有图床
    IMAGE_UPLOAD_URL = os.getenv('IMAGE_UPLOAD_URL', '')
    IMAGE_UPLOAD_TOKEN = os.getenv('IMAGE_UPLOAD_TOKEN', '')

    # R2 存储配置（日报 HTML/图片托管，钉钉内嵌图片与完整版链接）
    R2_ENDPOINT = os.getenv('R2_ENDPOINT', '')  # 如 https://<account_id>.r2.cloudflarestorage.com
    R2_API_TOKEN = os.getenv('R2_API_TOKEN', '')  # Cloudflare API Token（R2 对象读写权限）
    R2_BUCKET = os.getenv('R2_BUCKET', 'phoss-lab')
    R2_PUBLIC_URL = os.getenv('R2_PUBLIC_URL', '')  # 如 https://pub-xxxxx.r2.dev

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
