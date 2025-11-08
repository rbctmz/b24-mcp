FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY mcp_server ./mcp_server

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

COPY tests ./tests
COPY mcp_server_spec.md ./
COPY .env.example ./

EXPOSE 8000

CMD ["uvicorn", "mcp_server.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
