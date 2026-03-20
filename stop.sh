#!/bin/bash

CONTAINER="nsfw-detection"

if docker ps -q --filter "name=^${CONTAINER}$" | grep -q .; then
  echo "==> Stopping container..."
  docker stop "$CONTAINER"
  echo "==> Done."
else
  echo "Container is not running."
fi
