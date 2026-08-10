FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py email_client.py analyzer.py notifier.py scheduler.py main.py domains.json ./

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
