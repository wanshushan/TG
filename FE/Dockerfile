FROM node:22-bookworm-slim AS builder

WORKDIR /app

RUN corepack enable

ARG PNPM_REGISTRY=https://registry.npmmirror.com
ARG PNPM_FETCH_RETRIES=8
ARG PNPM_FETCH_RETRY_MIN_TIMEOUT=10000
ARG PNPM_FETCH_RETRY_MAX_TIMEOUT=120000
ARG PNPM_FETCH_TIMEOUT=120000

RUN pnpm config set registry ${PNPM_REGISTRY} \
    && pnpm config set fetch-retries ${PNPM_FETCH_RETRIES} \
    && pnpm config set fetch-retry-mintimeout ${PNPM_FETCH_RETRY_MIN_TIMEOUT} \
    && pnpm config set fetch-retry-maxtimeout ${PNPM_FETCH_RETRY_MAX_TIMEOUT} \
    && pnpm config set fetch-timeout ${PNPM_FETCH_TIMEOUT}

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prefer-offline

COPY . .
RUN pnpm build

FROM node:22-bookworm-slim AS runner

WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=4321

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

EXPOSE 4321

CMD ["node", "./dist/server/entry.mjs"]
