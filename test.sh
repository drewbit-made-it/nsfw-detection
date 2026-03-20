#!/bin/bash

[ -f .env ] && source .env

HOST="${HOST:-http://localhost:8080}"
API_KEY="${API_KEY:-}"

# Add image URLs here to test the classifier
IMAGES=(
  "https://images.pexels.com/photos/21033429/pexels-photo-21033429.jpeg"
  "https://images.pexels.com/photos/17413623/pexels-photo-17413623.jpeg"
  "https://images.pexels.com/photos/36520426/pexels-photo-36520426.jpeg"
  "https://images.pexels.com/photos/5012457/pexels-photo-5012457.jpeg"
  "https://images.pexels.com/photos/1890403/pexels-photo-1890403.jpeg"
  "https://images.pexels.com/photos/36435133/pexels-photo-36435133.jpeg"
)

echo "Testing ${HOST}/classify"
echo "-------------------------------------------"

for url in "${IMAGES[@]}"; do
  response=$(curl -sf -X POST "${HOST}/classify" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_KEY}" \
    -d "{\"url\":\"${url}\"}")

  if [ $? -ne 0 ]; then
    echo "FAIL  $url"
    echo "      (is the server running?)"
    continue
  fi

  label=$(echo "$response" | grep -o '"label":"[^"]*"' | cut -d'"' -f4)
  normal=$(echo "$response" | grep -o '"normal":[0-9.]*' | cut -d: -f2)
  nsfw=$(echo "$response" | grep -o '"nsfw":[0-9.]*' | cut -d: -f2)

  printf "%-8s  normal=%.4f  nsfw=%.4f  %s\n" "$label" "$normal" "$nsfw" "$url"
done
