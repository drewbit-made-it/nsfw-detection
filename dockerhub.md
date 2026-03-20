# nsfw-detection

Lightweight image classification API using [Falconsai/nsfw_image_detection](https://huggingface.co/Falconsai/nsfw_image_detection) (ViT-base) exported to ONNX. No PyTorch at runtime. Designed to run as an internal Docker Compose service or a standalone serverless container.

**[👾 View the source code and local development instructions on GitHub](https://github.com/drewbit-made-it/nsfw-detection)**

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
  },
  "timing_ms": {
    "download_ms": 167.23,
    "decode_ms": 20.45,
    "resize_ms": 7.35,
    "normalize_ms": 0.34,
    "inference_ms": 33.95,
    "total_ms": 229.32
  }
}
```

**Example**

```bash
curl -X POST http://localhost:8080/classify \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/image.jpg"}'
```

*Note: All requests to `/classify` require a bearer token. Requests without a valid token are rejected with `401`.*

### `GET /health`

Returns `{"status": "ok"}`. No auth required. Use this as your container health check.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | *(none)* | **Required.** Bearer token for `/classify`. All requests are rejected if this is unset. |
| `SERVERLESS` | `true` | `true`: 1 thread, low RAM, `httpx` HTTP client — optimized for serverless environments.<br>`false`: all CPU cores, pooled memory, `aiohttp` HTTP client with connection pooling — optimized for VPS or dedicated hosts. |
| `USE_INT8` | `false` | `true`: use the pre-quantized int8 model. Typically 20–40% faster inference on CPU with a ~4x smaller model file. `false`: standard float32. |
| `MAX_IMAGE_MB` | `10` | Max image download size in MB. Hard ceiling is `50`. Decimals supported (e.g. `0.5` for 500 KB). |

---

## Quick Demo (One Command)

To try the pre-built image immediately, run it with your key, size limit, and port mapped inline.

*(Tip: Generate a secure key by running `openssl rand -hex 32` in your terminal.)*

```bash
docker run --rm --name nsfw-detection-demo \
  -p 8080:8080 \
  -e API_KEY=your-secret-key \
  -e MAX_IMAGE_MB=10 \
  -e SERVERLESS=true \
  -e USE_INT8=false \
  drewbitmadeit/nsfw-detection:latest
```

Then hit the endpoint using a sample image:

```bash
curl -s -X POST http://localhost:8080/classify \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://images.pexels.com/photos/45201/kitty-cat-kitten-pet-45201.jpeg"}' | jq
```

---

## Docker Compose (Internal Service)

The safest way to run this in production is as an internal service with **no public port exposure**. Services on the same Docker network can reach it at `http://nsfw-detection:8080/classify`.

```yaml
services:
  your-main-app:
    build: .
    environment:
      - ML_API_URL=http://nsfw-detection:8080/classify
      - ML_API_KEY=your-secret-key
    networks:
      - backend

  nsfw-detection:
    image: drewbitmadeit/nsfw-detection:latest
    expose:
      - "8080"
    environment:
      - API_KEY=your-secret-key
      - SERVERLESS=false  # false = multi-core + connection pooling for VPS; true = low-RAM serverless
      - MAX_IMAGE_MB=10
      - USE_INT8=false    # true = faster CPU inference using pre-quantized int8 model
    networks:
      - backend

networks:
  backend:
    driver: bridge
```

---

## Standalone Deployment (Google Cloud Run, Fly.io, etc.)

When deploying as a public standalone container, the `API_KEY` environment variable is your only line of defense against unauthorized compute usage.

1. Set `API_KEY` as an encrypted secret via your hosting platform's UI.
2. Set `SERVERLESS=true` to keep RAM usage optimized for low-resource environments.
3. Send the key from your main application as a request header:

```
Authorization: Bearer <your-secret-key>
```
