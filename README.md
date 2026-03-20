# nsfw-detection

Lightweight image classification API using [Falconsai/nsfw_image_detection](https://huggingface.co/Falconsai/nsfw_image_detection) (ViT-base) exported to ONNX. No PyTorch at runtime. Designed to run locally or as a containerized serverless function.

## Endpoints

### `POST /classify`

Fetches an image from a URL and returns a label with confidence scores.

**Request**
```json
{ "url": "https://example.com/image.jpg" }
```

**Response**
```json
{
  "label": "normal",
  "scores": {
    "normal": 0.9989596605300903,
    "nsfw": 0.001040336093865335
  }
}
```

**Example**
```bash
curl -X POST http://localhost:8080/classify -H "Authorization: Bearer your-secret-key" -H "Content-Type: application/json" -d '{"url":"https://example.com/image.jpg"}'
```

All requests to `/classify` require a bearer token. Requests without a valid token are rejected with `401`.

**Limits:** Images over 10 MB are rejected with `413`. To change this, edit `MAX_IMAGE_BYTES` at the top of `main.py`.

### `GET /health`

Returns `{"status": "ok"}`. No auth required. Use this as your container health check.

---

## Quickstart (Docker — recommended)

Requires Docker. Run `./setup.sh` once to download and convert the model (~500 MB).

```bash
./setup.sh
API_KEY=your-secret-key ./run.sh    # start on port 8080
./stop.sh                           # stop and remove the container
```

Override the port if needed:
```bash
PORT=9090 API_KEY=your-secret-key ./run.sh
```

## Testing

With the server running, execute the test script to classify a set of sample images:

```bash
API_KEY=your-secret-key ./test.sh
```

Output:
```
Testing http://localhost:8080/classify
-------------------------------------------
normal    normal=0.9990  nsfw=0.0010  https://images.pexels.com/...
```

Add or swap image URLs by editing the `IMAGES` array in `test.sh`.

## Local dev (no Docker)

Requires `uv`.

```bash
./setup.sh
API_KEY=your-secret-key uv run uvicorn main:app --port 8080 --reload
```

---

## Integrating with Docker Compose

This image is designed to run as an internal service — not exposed to the public internet. Add it to your existing `docker-compose.yml` without a `ports:` mapping so only services on the same network can reach it:

```yaml
services:
  your-app:
    build: .
    environment:
      - ML_API_URL=http://nsfw-detection:8080/classify
      - ML_API_KEY=your-secret-key
    networks:
      - backend

  nsfw-detection:
    image: yourdockerhubuser/nsfw-detection:latest
    expose:
      - "8080"
    environment:
      - API_KEY=your-secret-key
    networks:
      - backend

networks:
  backend:
    driver: bridge
```

Your app calls `http://nsfw-detection:8080/classify` internally. No port is published to the host, so the classifier is never reachable from outside Docker.

---

## Standalone deployment (Cloudflare, Fly.io, etc.)

When deploying as a public standalone container, the `API_KEY` environment variable is your only line of defense. Set it to a long random string and keep it out of your repo:

```bash
openssl rand -hex 32
```

Pass it as a secret via your platform's environment variable UI, and send it from your main app as a request header:

```
Authorization: Bearer <your-secret-key>
```
