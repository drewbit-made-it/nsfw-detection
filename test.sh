#!/bin/bash

[ -f .env ] && source .env

HOST="${HOST:-http://localhost:${PORT:-8080}}"
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
  response=$(curl -s -X POST "${HOST}/classify" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_KEY}" \
    -d "{\"url\":\"${url}\"}")

  if [ $? -ne 0 ] || [ -z "$response" ]; then
    echo "FAIL  could not reach server — is it running?"
    continue
  fi

  if echo "$response" | grep -q '"detail"'; then
    detail=$(echo "$response" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4)
    echo "ERROR $detail"
    echo "      $url"
    continue
  fi

  label=$(echo "$response" | grep -o '"label":"[^"]*"' | cut -d'"' -f4)
  normal=$(echo "$response" | grep -o '"normal":[0-9.]*' | cut -d: -f2)
  nsfw=$(echo "$response" | grep -o '"nsfw":[0-9.]*' | cut -d: -f2)
  download_ms=$(echo "$response" | grep -o '"download_ms":[0-9.]*' | cut -d: -f2)
  decode_ms=$(echo "$response" | grep -o '"decode_ms":[0-9.]*' | cut -d: -f2)
  resize_ms=$(echo "$response" | grep -o '"resize_ms":[0-9.]*' | cut -d: -f2)
  normalize_ms=$(echo "$response" | grep -o '"normalize_ms":[0-9.]*' | cut -d: -f2)
  inference_ms=$(echo "$response" | grep -o '"inference_ms":[0-9.]*' | cut -d: -f2)
  total_ms=$(echo "$response" | grep -o '"total_ms":[0-9.]*' | cut -d: -f2)

  printf "%-8s  normal=%.4f  nsfw=%.4f\n" "$label" "$normal" "$nsfw"
  printf "         dl=%-8s dec=%-8s resize=%-8s norm=%-8s inf=%-8s total=%s ms\n" \
    "$download_ms" "$decode_ms" "$resize_ms" "$normalize_ms" "$inference_ms" "$total_ms"
  printf "         %s\n" "$url"
done
