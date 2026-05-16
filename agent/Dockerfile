FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

COPY . .

EXPOSE 8123

CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "8123", "--no-browser"]
