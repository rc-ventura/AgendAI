# Contract: Docker Compose Service — agent-ui-pro

**Feature**: 003-professional-chat-ui
**Date**: 2026-05-16

## New service to add to docker-compose.yml

```yaml
agent-ui-pro:
  build:
    context: ./agent-ui-pro
    args:
      NEXT_PUBLIC_API_URL: http://localhost:8080
      NEXT_PUBLIC_GRAPH_ID: agendai_agent
      NEXT_PUBLIC_LANGGRAPH_API_KEY: ${LANGGRAPH_AUTH_TOKEN}
  ports:
    - "3002:3002"
  depends_on:
    - nginx
  restart: unless-stopped
  networks:
    - agendai-network
```

## Dockerfile for agent-ui-pro

Standard Next.js 14 Dockerfile (same pattern as existing agent-ui):

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_GRAPH_ID
ARG NEXT_PUBLIC_LANGGRAPH_API_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_GRAPH_ID=$NEXT_PUBLIC_GRAPH_ID
ENV NEXT_PUBLIC_LANGGRAPH_API_KEY=$NEXT_PUBLIC_LANGGRAPH_API_KEY
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
RUN npm ci --production
EXPOSE 3002
CMD ["npm", "start"]
```

## Port assignments (post-feature)

| Service | Port | Notes |
|---------|------|-------|
| REST API | 3000 | Unchanged |
| LangGraph agent (internal) | 8123 | localhost only |
| nginx proxy | 8080 | Agent public endpoint |
| agent-ui (existing) | 3001 | Kept alive during transition |
| agent-ui-pro (new) | 3002 | Professional UI |
