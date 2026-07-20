# KritiFin frontend (Next.js 14). Multi-stage: full build, then a slim runtime
# that ships only the standalone server bundle.

# ---- deps + build ---------------------------------------------------------
FROM node:20-slim AS build
WORKDIR /app

# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time, so they
# must be present now — passed as build args from docker-compose.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_SUPABASE_URL=
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY=
ARG NEXT_PUBLIC_SENTRY_DSN=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_TELEMETRY_DISABLED=1

# Install with the lockfile for reproducible builds (needs dev deps to build).
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ---- runtime --------------------------------------------------------------
FROM node:20-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output includes a minimal server + traced node_modules; static
# assets and public/ are copied alongside as Next expects.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# Run as the built-in unprivileged node user.
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
