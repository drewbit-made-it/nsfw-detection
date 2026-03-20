import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import onnxruntime as ort
import aiohttp
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

API_KEY = os.environ.get("API_KEY", "")

# Labels from Falconsai/nsfw_image_detection
LABELS = ["normal", "nsfw"]
_MAX_IMAGE_MB = min(float(os.environ.get("MAX_IMAGE_MB", 10)), 50)  # default 10 MB, ceiling 50 MB
MAX_IMAGE_BYTES = int(_MAX_IMAGE_MB * 1024 * 1024)
IS_SERVERLESS = os.environ.get("SERVERLESS", "true").lower() in ("true", "1", "yes")
USE_INT8 = os.environ.get("USE_INT8", "false").lower() in ("true", "1", "yes")

_MODEL_PATH = "model_int8.onnx" if USE_INT8 else "model.onnx"

if not os.path.exists(_MODEL_PATH):
    raise RuntimeError(
        f"{_MODEL_PATH} not found. "
        + ("Run quantize.py (or setup.sh) to generate it first." if USE_INT8 else "Run setup.sh first.")
    )

print(f"Using {'INT8' if USE_INT8 else 'FP32'} model: {_MODEL_PATH}")

# Load ONNX model once at startup
_opts = ort.SessionOptions()
_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

if IS_SERVERLESS:
    _opts.intra_op_num_threads = 1
    _opts.inter_op_num_threads = 1
    _opts.enable_cpu_mem_arena = False  # return memory to OS between calls
    _opts.enable_mem_pattern = False    # don't pre-allocate for fixed patterns
    print("Starting ONNX in SERVERLESS mode (low RAM, 1 thread)")
else:
    _opts.intra_op_num_threads = 0      # auto-detect all cores
    _opts.inter_op_num_threads = 0
    _opts.enable_cpu_mem_arena = True   # keep RAM pooled for the next request
    _opts.enable_mem_pattern = True     # pre-allocate for faster math
    print("Starting ONNX in PERFORMANCE mode (high RAM, multi-core)")

session = ort.InferenceSession(_MODEL_PATH, sess_options=_opts, providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_UA   = {"User-Agent": "Mozilla/5.0"}

# HTTP clients and executor — created in lifespan, one per mode
_httpx_client: httpx.AsyncClient | None = None
_aiohttp_session: aiohttp.ClientSession | None = None
_executor: ThreadPoolExecutor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _httpx_client, _aiohttp_session, _executor
    if IS_SERVERLESS:
        # Single connection is enough; keep a small pool for warm reuse
        _httpx_client = httpx.AsyncClient(
            headers=_UA,
            timeout=10,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )
        print("HTTP client: httpx (serverless)")
    else:
        # Large pool, DNS caching, proactive cleanup for high concurrency
        _aiohttp_session = aiohttp.ClientSession(
            headers=_UA,
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(
                limit=200,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            ),
        )
        # One thread per core — lets the event loop pipeline downloads while
        # inference runs. ONNX already parallelises internally per call.
        _executor = ThreadPoolExecutor(max_workers=os.cpu_count())
        print(f"HTTP client: aiohttp (performance), executor: {os.cpu_count()} workers")
    yield
    if _httpx_client:
        await _httpx_client.aclose()
    if _aiohttp_session:
        await _aiohttp_session.close()
    if _executor:
        _executor.shutdown(wait=True)


app = FastAPI(lifespan=lifespan)
_bearer = HTTPBearer()


def preprocess(data: bytes) -> tuple[np.ndarray, float, float, float]:
    t0 = time.perf_counter()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR uint8
    if img is None:
        raise ValueError("Could not decode image")
    decode_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224), interpolation=cv2.INTER_LINEAR)
    resize_ms = (time.perf_counter() - t1) * 1000

    t2 = time.perf_counter()
    arr = img.astype(np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    arr = arr.transpose(2, 0, 1)
    tensor = np.expand_dims(arr, axis=0)
    normalize_ms = (time.perf_counter() - t2) * 1000

    return tensor, decode_ms, resize_ms, normalize_ms


def predict(data: bytes, download_ms: float) -> dict:
    tensor, decode_ms, resize_ms, normalize_ms = preprocess(data)

    t0 = time.perf_counter()
    outputs = session.run(None, {input_name: tensor})
    inference_ms = (time.perf_counter() - t0) * 1000

    logits = outputs[0][0]
    logits = logits - logits.max()  # numerical stability
    probs = np.exp(logits) / np.exp(logits).sum()
    label = LABELS[int(np.argmax(probs))]

    timing = {
        "download_ms":   round(download_ms, 2),
        "decode_ms":     round(decode_ms, 2),
        "resize_ms":     round(resize_ms, 2),
        "normalize_ms":  round(normalize_ms, 2),
        "inference_ms":  round(inference_ms, 2),
    }
    print(
        f"[{'INT8' if USE_INT8 else 'FP32'}|{'httpx' if IS_SERVERLESS else 'aiohttp'}] "
        + "  ".join(f"{k}={v}ms" for k, v in timing.items())
    )
    return {"label": label, "scores": {l: float(p) for l, p in zip(LABELS, probs)}, "timing_ms": timing}


async def _fetch(url: str) -> tuple[bytes, float]:
    t0 = time.perf_counter()
    if IS_SERVERLESS:
        try:
            async with _httpx_client.stream("GET", url) as resp:
                resp.raise_for_status()
                chunks, total = [], 0
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail=f"Image exceeds {_MAX_IMAGE_MB:g} MB limit")
                    chunks.append(chunk)
                return b"".join(chunks), (time.perf_counter() - t0) * 1000
        except HTTPException:
            raise
        except httpx.HTTPError as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image: {e}")
    else:
        try:
            async with _aiohttp_session.get(url) as resp:
                resp.raise_for_status()
                chunks, total = [], 0
                async for chunk in resp.content.iter_chunked(65536):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail=f"Image exceeds {_MAX_IMAGE_MB:g} MB limit")
                    chunks.append(chunk)
                return b"".join(chunks), (time.perf_counter() - t0) * 1000
        except HTTPException:
            raise
        except aiohttp.ClientError as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image: {e}")


class ClassifyRequest(BaseModel):
    url: str


def check_api_key(credentials: HTTPAuthorizationCredentials = Security(_bearer)):
    if not API_KEY or credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.post("/classify")
async def classify(req: ClassifyRequest, _: None = Security(check_api_key)):
    t_start = time.perf_counter()
    data, download_ms = await _fetch(req.url)
    try:
        if IS_SERVERLESS:
            result = predict(data, download_ms)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(_executor, predict, data, download_ms)
    except ValueError:
        raise HTTPException(status_code=400, detail="Could not decode image")
    result["timing_ms"]["total_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
