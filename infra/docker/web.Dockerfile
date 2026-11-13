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

CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
