# ── Stage 1: build the React / Vite app ──────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first for better layer caching
COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Stage 2: serve static files with nginx (non-root) ────────────────────────
FROM nginxinc/nginx-unprivileged:alpine AS final

# Copy built assets and nginx config
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
