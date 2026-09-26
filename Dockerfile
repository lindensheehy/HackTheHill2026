# Northwind Triage: one container with the API, the built UI and the scheduled detector.
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine engine
COPY jobs jobs
COPY api api
COPY Northwind_Challenge_Data/data.db Northwind_Challenge_Data/data.db
COPY deploy/entrypoint.sh /entrypoint.sh
COPY --from=web /web/dist web/dist
EXPOSE 8000
CMD ["sh", "/entrypoint.sh"]
