FROM node:22-alpine

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml /app/
COPY apps/web/package.json /app/apps/web/package.json
COPY packages/types/package.json /app/packages/types/package.json
COPY packages/ui/package.json /app/packages/ui/package.json

RUN pnpm install --frozen-lockfile

COPY apps/web /app/apps/web
COPY packages/types /app/packages/types
COPY packages/ui /app/packages/ui

WORKDIR /app/apps/web

ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
RUN pnpm build

# Production server, unprivileged user. For hot reload during development run `pnpm dev` locally.
USER node
CMD ["node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
