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
  },
  "timing_ms": {
    "download_ms": 1820.54,
    "decode_ms": 8.12,
    "resize_ms": 1.43,
    "normalize_ms": 0.81,
    "inference_ms": 42.17,
    "total_ms": 1873.07
  }
}
```

**Example**
```bash
curl -X POST http://localhost:8080/classify -H "Authorization: Bearer your-secret-key" -H "Content-Type: application/json" -d '{"url":"https://example.com/image.jpg"}'
```

All requests to `/classify` require a bearer token. Requests without a valid token are rejected with `401`.

**Limits:** Images over 10 MB are rejected with `413`. Override via `MAX_IMAGE_MB` in `.env` (default: `10`, hard ceiling: `50`). Decimals are supported — e.g. `0.5` for 500 KB.

**Performance tip:** Prefer JPEG or WebP over PNG. PNG decompression is CPU-intensive and can add 150–250 ms to decode time. JPEG and WebP decode in 10–30 ms for the same image dimensions, making them significantly faster through the pipeline.

### `GET /health`

Returns `{"status": "ok"}`. No auth required. Use this as your container health check.

---

## Quick demo (one command)

If you just want to try the API without cloning the repo, pull the pre-built image and run it with your key, size limit, and port inline:

```bash
docker run --rm --name nsfw-detection-demo \
  -p 8080:8080 \
  -e API_KEY=your-secret-key \
  -e MAX_IMAGE_MB=10 \
  -e SERVERLESS=true \
  -e USE_INT8=false \
  -e LOG_LEVEL=info \
  drewbitmadeit/nsfw-detection:latest
```
| Flag | Purpose |
|---|---|
| `-e API_KEY=...` | Bearer token required on every `/classify` request |
| `-e MAX_IMAGE_MB=10` | Max image size in MB (default `10`, ceiling `50`) |
| `-e SERVERLESS=true` | `true` (default): 1 thread, low RAM, httpx; `false`: multi-core, pooled RAM, aiohttp |
| `-e USE_INT8=false` | `true`: use pre-quantized int8 model — faster CPU inference, ~4x smaller model; `false` (default): float32 |
| `-e LOG_LEVEL=info` | `info`: per-request timing + access logs. `warning`: warnings/errors only — recommended for high traffic. |
| `-p 8080:8080` | Map host port → container port (`-p <host>:<container>`) |

Change `-p 9090:8080` to expose on a different host port. The container always listens on `8080` internally.

Then hit the endpoint:

```bash
curl -s -X POST http://localhost:8080/classify \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://images.pexels.com/photos/45201/kitty-cat-kitten-pet-45201.jpeg"}' | jq
```

Expected response:
```json
{
  "label": "normal",
  "scores": { "normal": 0.9990, "nsfw": 0.0010 },
  "timing_ms": { "download_ms": 1820.54, "decode_ms": 8.12, "resize_ms": 1.43, "normalize_ms": 0.81, "inference_ms": 42.17, "total_ms": 1873.07 }
}
```
---

## Quickstart (Docker — recommended)

Requires Docker. Run `./setup.sh` once to download and convert the model (~500 MB).

**1. Configure your environment:**
```bash
cp .env.example .env
# Edit .env and set API_KEY to a secret value
```

**2. Start and stop:**
```bash
./setup.sh   # first time only
./run.sh     # build image and start on port 8080
./stop.sh    # stop the container
```

Override the port in `.env` or inline:
```bash
PORT=9090 ./run.sh
```

## Testing

With the server running, run the test script to classify a set of sample images:

```bash
./test.sh
```

Output:
```
Testing http://localhost:8080/classify
-------------------------------------------
normal    normal=0.9990  nsfw=0.0010
         dl=167.23   dec=20.45   resize=7.35   norm=0.34   inf=33.95   total=229.32 ms
         https://images.pexels.com/...
```

Add or swap image URLs by editing the `IMAGES` array in `test.sh`.

## Local dev (no Docker)

Requires `uv`.

```bash
cp .env.example .env  # set API_KEY in .env
./setup.sh
```

Serverless mode (default):
```bash
API_KEY=your-secret-key MAX_IMAGE_MB=10 SERVERLESS=true USE_INT8=false LOG_LEVEL=info \
  uv run uvicorn main:app --port 8080 --reload
```

Performance mode:
```bash
API_KEY=your-secret-key MAX_IMAGE_MB=10 SERVERLESS=false USE_INT8=true LOG_LEVEL=warning \
  uv run uvicorn main:app --port 8080 --log-level warning
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | *(none)* | Bearer token required on every `/classify` request. Leave unset to disable auth (not recommended in production). |
| `MAX_IMAGE_MB` | `10` | Max image fetch size in MB. Hard ceiling is `50`. Supports decimals (e.g. `0.5` for 500 KB). |
| `SERVERLESS` | `true` | `true`: 1 thread, no memory pooling — optimized for low-RAM serverless environments. `false`: auto-detect all CPU cores and pool memory — optimized for VPS or dedicated hosts. |
| `USE_INT8` | `false` | `true`: use the pre-quantized int8 model (`model_int8.onnx`), generated by `setup.sh` or the Docker build. Typically 20–40% faster inference on CPU with ~2-4x smaller model. `false`: standard float32. |
| `LOG_LEVEL` | `info` | `info`: per-request timing logs + uvicorn access logs. `warning`: warnings and errors only — recommended for high-traffic deployments. |

---

## Benchmarks

Load tested with `hey -n 100 -c 10` (100 requests, 10 concurrent) classifying the same JPEG image.

| Environment | Mode | Avg latency | Req/sec |
|---|---|---|---|
| MacBook Air M2 | `SERVERLESS=true` + float32 | 3.77s | 2.5 |
| MacBook Air M2 | `SERVERLESS=false` + INT8 | 1.68s | 5.7 |
| VPS (x86, 4-core) | `SERVERLESS=false` + float32 | 0.78s | 12.4 |
| VPS (x86, 4-core) | `SERVERLESS=false` + INT8 | **0.40s** | **24.3** |

INT8 is consistently ~2x faster than float32. The VPS gains an additional 4x over Mac due to AVX-512 VNNI — x86 server CPUs have dedicated silicon for INT8 dot products, and with `SERVERLESS=false` all cores are used. At 24 req/sec with sub-400ms median latency, a single VPS node handles production traffic comfortably before needing to scale.

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
    image: drewbitmadeit/nsfw-detection:latest
    expose:
      - "8080"
    environment:
      - API_KEY=your-secret-key
      - SERVERLESS=false  # false = multi-core + aiohttp for VPS; true (default) = low-RAM serverless
      - MAX_IMAGE_MB=10
      - USE_INT8=false    # true = pre-quantized int8 model (faster CPU inference)
      - LOG_LEVEL=warning # warning = errors only; info = per-request timing logs
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
