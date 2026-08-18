FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_BASE defaults to /api, which nginx.conf proxies to the backend
# service — matches the same relative-path convention the Vite dev proxy
# uses, so no frontend code needs to change between dev and production.
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
