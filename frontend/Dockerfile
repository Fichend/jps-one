FROM node:22-bookworm-slim AS build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm install && npm install --no-save @rollup/rollup-linux-x64-gnu@4.57.1

COPY frontend ./
RUN npm run build

FROM nginx:1.27-bookworm

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
