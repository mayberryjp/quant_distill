FROM python:3.12-alpine3.21

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apk upgrade --no-cache \
    && apk add --no-cache supervisor

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN python -m pip install --upgrade pip \
    && python -m pip install .

COPY supervisord.conf /app/supervisord.conf

EXPOSE 8021

CMD ["supervisord", "-c", "/app/supervisord.conf"]
