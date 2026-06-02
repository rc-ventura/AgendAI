# Este Dockerfile NÃO é usado em produção.
# Em produção e no docker-compose de dev, a imagem é construída via:
#   langgraph build -t agendai-agent --no-pull
# que produz a imagem oficial langchain/langgraph-server com o grafo embutido.
#
# Para construir manualmente:
#   cd agent
#   pip install -U langgraph-cli
#   langgraph build -t agendai-agent --no-pull
#
# O servidor escuta na porta 8123. Requer:
#   DATABASE_URI  — Postgres para checkpointing (agendai_lg)
#   REDIS_URI     — Upstash Redis para SSE streaming
#   LANGSMITH_API_KEY — license key (Developer plan)
#   OPENAI_API_KEY, API_BASE_URL

# Fallback para dev rápido sem langgraph build (só local, sem persistência):
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e "." && pip install --no-cache-dir "langgraph-cli[inmem]"

COPY . .

EXPOSE 8123

CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "8123", "--no-browser"]
