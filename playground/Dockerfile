# The Playground (BFF + built UI) as one image. Built from the repo root:
#   docker build -f playground/Dockerfile -t inji-playground .
# integration/stack.py builds and starts it; see playground/docker-compose.yaml.

FROM node:22-slim AS web
WORKDIR /web
COPY playground/web/package.json playground/web/package-lock.json ./
RUN npm ci
COPY playground/web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY certify/scripts/requirements.txt certify/scripts/requirements.txt
COPY verify/scripts/requirements.txt verify/scripts/requirements.txt
COPY playground/bff/requirements.txt playground/bff/requirements.txt
RUN pip install --no-cache-dir -r playground/bff/requirements.txt
COPY --from=web /web/dist /opt/playground-web
# The repo itself is mounted at /app at run time, so identity edits reach Certify's CSV and
# runs are kept in playground/.data on the host.
ENV PLAYGROUND_WEB_DIST=/opt/playground-web \
    PLAYGROUND_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
EXPOSE 5050
CMD ["python", "playground/bff/main.py"]
