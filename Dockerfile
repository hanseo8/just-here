# 그냥여기 — production image
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY web /app/web
COPY data /app/data
COPY scripts/restore-rewards.py scripts/restore-storage.py scripts/merge-storage.py scripts/apply-storage-recovery.py scripts/sanitize-deletion-backup.py /app/scripts/

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1

# Render/Railway inject PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8010}"]
