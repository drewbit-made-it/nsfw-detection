#!/bin/bash
set -e

IMAGE="drewbitmadeit/nsfw-detection"

if [ ! -f model.onnx ]; then
  echo "Error: model.onnx not found. Run ./setup.sh first."
  exit 1
fi

# Create a multi-platform buildx builder if it doesn't exist yet
if ! docker buildx inspect multiplatform &>/dev/null; then
  echo "==> Creating multi-platform buildx builder..."
  docker buildx create --name multiplatform --driver docker-container --use
else
  docker buildx use multiplatform
fi

echo "==> Building and pushing linux/amd64..."
docker buildx build --platform linux/amd64 --tag "${IMAGE}:latest-amd64" --push .

echo "==> Building and pushing linux/arm64..."
docker buildx build --platform linux/arm64 --tag "${IMAGE}:latest-arm64" --push .

echo "==> Creating multi-arch manifest for :latest..."
docker buildx imagetools create \
  --tag "${IMAGE}:latest" \
  "${IMAGE}:latest-amd64" \
  "${IMAGE}:latest-arm64"

echo ""
echo "==> Published:"
echo "    ${IMAGE}:latest-amd64  (linux/amd64)"
echo "    ${IMAGE}:latest-arm64  (linux/arm64)"
echo "    ${IMAGE}:latest        (multi-arch manifest)"
