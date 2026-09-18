FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home paper \
    && mkdir /data && chown paper:paper /data
COPY --chown=paper:paper backend/ ./
USER paper
ENV DATABASE_URL=sqlite:////data/paper.db TRADING_MODE=paper LIVE_TRADING_ENABLED=false
CMD ["python", "-m", "app.runtime.worker", "--database", "/data/paper.db", "status"]
