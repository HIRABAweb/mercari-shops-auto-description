FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/yahuoku-to-mercarishops:/app/review-ui

WORKDIR /app

COPY review-ui/requirements.txt /app/review-ui/requirements.txt
RUN pip install --no-cache-dir -r /app/review-ui/requirements.txt

COPY yahuoku-to-mercarishops /app/yahuoku-to-mercarishops
COPY review-ui /app/review-ui

WORKDIR /app/review-ui

CMD exec gunicorn --bind :${PORT:-8080} --workers 2 --threads 8 app:app
