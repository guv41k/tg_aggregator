FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --chown=app:app main.py config.py ./
COPY --chown=app:app admin_bot/ ./admin_bot/
COPY --chown=app:app collector/ ./collector/
COPY --chown=app:app db/ ./db/
COPY --chown=app:app utils/ ./utils/

RUN mkdir /app/media && chown app:app /app/media

USER app

CMD ["python", "main.py"]
