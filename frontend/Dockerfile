FROM node:18-alpine AS build

WORKDIR /app

# Install deps first for layer caching
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

COPY . .
RUN npm run build

# Serve the built files with a lightweight static server
FROM node:18-alpine

WORKDIR /app
RUN npm install -g serve@14

COPY --from=build /app/dist ./dist

EXPOSE 5173

CMD ["serve", "-s", "dist", "-l", "5173"]
