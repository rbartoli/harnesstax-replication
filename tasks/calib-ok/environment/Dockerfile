FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl bash ca-certificates git procps && rm -rf /var/lib/apt/lists/*
WORKDIR /app
