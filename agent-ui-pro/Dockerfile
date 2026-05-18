FROM node:20-alpine AS builder
WORKDIR /app
# Use pnpm to match local/CI installs and honor pnpm.overrides in package.json.
# Corepack ships with Node 20 and respects the `packageManager` field.
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ASSISTANT_ID
ARG NEXT_PUBLIC_LANGGRAPH_API_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_ASSISTANT_ID=$NEXT_PUBLIC_ASSISTANT_ID
ENV NEXT_PUBLIC_LANGGRAPH_API_KEY=$NEXT_PUBLIC_LANGGRAPH_API_KEY
RUN pnpm build && mkdir -p /app/public

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3002
ENV PORT=3002
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
