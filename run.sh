#!/bin/bash
set -e

[ -f .env ] && source .env

IMAGE="nsfw-detection"
CONTAINER="nsfw-detection"
PORT="${PORT:-8080}"

if [ ! -f model.onnx ]; then
  echo "Error: model.onnx not found. Run ./setup.sh first."
  exit 1
fi

if docker ps -q --filter "name=^${CONTAINER}$" | grep -q .; then
  echo "Already running. Stop it first with ./stop.sh"
  exit 1
fi

if [ -z "$API_KEY" ]; then
  echo "Warning: API_KEY is not set. All requests will be rejected with 401."
  echo "         Set API_KEY in .env or the environment before running."
fi

echo "==> Building image..."
docker build -t "$IMAGE" .

echo "==> Starting container on port ${PORT}..."
docker run -d --name "$CONTAINER" -p "${PORT}:8080" -e API_KEY="${API_KEY}" "$IMAGE"

echo "==> Done. API available at http://localhost:${PORT}"
echo "    Health check: curl http://localhost:${PORT}/health"
