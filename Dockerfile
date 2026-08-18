FROM python:3.10-slim

WORKDIR /app

# 换清华 apt 源加速；中文字体 + emoji 字体 + chromium 系统库（playwright --with-deps 在 slim 上不生效，显式安装）
RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources; \
    apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk fonts-noto-color-emoji libxfixes3 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

# pip 走清华源、playwright 浏览器走 npmmirror（默认 CDN 国内下载极慢）
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
    # --with-deps 走清华 apt 源装全 chromium 系统依赖；libxfixes/libxkbcommon 已在 apt 层显式安装兑底
    && playwright install --with-deps chromium

COPY config.py email_client.py analyzer.py notifier.py scheduler.py main.py r2_uploader.py domains.json ./
COPY report_generator.py ./
COPY templates/ ./templates/

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
