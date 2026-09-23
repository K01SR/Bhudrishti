FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

RUN npm run build

FROM nginx:1.27-alpine

ENV NODE_ENV=production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf

EXPOSE 3000

# Serve the prebuilt static bundle with SPA fallback and proxy /api to the
# backend container so the browser stays on a single origin.
CMD ["nginx", "-g", "daemon off;"]