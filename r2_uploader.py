"""R2 存储模块 - 上传日报 HTML/图片到 Cloudflare R2（Cloudflare API）"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote
import requests
from config import Config


class R2Uploader:
    """Cloudflare R2 上传器（Bearer Token 方式，无需 S3 凭证对）"""

    def __init__(self):
        self.token = Config.R2_API_TOKEN
        self.bucket = Config.R2_BUCKET
        self.public_url = Config.R2_PUBLIC_URL.rstrip('/')
        self.account_id = self._extract_account_id(Config.R2_ENDPOINT)

    @staticmethod
    def _extract_account_id(endpoint: str) -> str:
        """从 S3 端点 URL 提取 account_id（https://<account_id>.r2.cloudflarestorage.com）"""
        m = re.search(r'https?://([a-f0-9]{32})\.r2\.cloudflarestorage\.com', endpoint)
        return m.group(1) if m else ''

    @property
    def available(self) -> bool:
        """R2 配置是否完整可用"""
        return all([self.token, self.bucket, self.public_url, self.account_id])

    @staticmethod
    def _guess_content_type(file_path: str) -> str:
        """按扩展名推断 Content-Type"""
        ext = Path(file_path).suffix.lower()
        return {
            '.html': 'text/html; charset=utf-8',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
        }.get(ext, 'application/octet-stream')

    def upload(self, file_path: str, object_key: str) -> Optional[str]:
        """上传文件到 R2，成功返回公开 URL，失败返回 None"""
        try:
            url = (
                f'https://api.cloudflare.com/client/v4/accounts/{self.account_id}'
                f'/r2/buckets/{self.bucket}/objects/{quote(object_key, safe="/")}'
            )
            with open(file_path, 'rb') as f:
                data = f.read()
            resp = requests.put(
                url,
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': self._guess_content_type(file_path),
                    'Cache-Control': 'no-cache',  # 同名覆盖后强制 CDN 回源，避免旧图缓存
                },
                data=data,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"  -> R2 上传失败: HTTP {resp.status_code} {resp.text[:200]}")
                return None
            print(f"  -> 已上传 R2: {object_key}")
            return f"{self.public_url}/{object_key}"
        except Exception as e:
            print(f"  -> R2 上传异常: {e}")
            return None
