import io
import os
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from pydantic import BaseModel
import httpx

app = FastAPI()
_bearer = HTTPBearer()
API_KEY = os.environ.get("API_KEY", "")

# Labels from Falconsai/nsfw_image_detection
LABELS = ["normal", "nsfw"]
_MAX_IMAGE_MB = min(float(os.environ.get("MAX_IMAGE_MB", 10)), 50)  # default 10 MB, ceiling 50 MB
MAX_IMAGE_BYTES = int(_MAX_IMAGE_MB * 1024 * 1024)
IS_SERVERLESS = os.environ.get("SERVERLESS", "true").lower() in ("true", "1", "yes")

# Load model once at startup
_opts = ort.SessionOptions()
_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

if IS_SERVERLESS:
    # Optimized for low RAM / 1 vCPU (serverless default)
    _opts.intra_op_num_threads = 1
    _opts.inter_op_num_threads = 1
    _opts.enable_cpu_mem_arena = False      # return memory to OS between calls
    _opts.enable_mem_pattern = False        # don't pre-allocate for fixed patterns
    print("Starting ONNX in SERVERLESS mode (low RAM, 1 thread)")
else:
    # Optimized for maximum throughput on multi-core machines
    _opts.intra_op_num_threads = 0          # auto-detect all cores
    _opts.inter_op_num_threads = 0
    _opts.enable_cpu_mem_arena = True       # keep RAM pooled for the next request
    _opts.enable_mem_pattern = True         # pre-allocate for faster math
    print("Starting ONNX in PERFORMANCE mode (high RAM, multi-core)")

session = ort.InferenceSession("model.onnx", sess_options=_opts, providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name


def preprocess(image: Image.Image) -> np.ndarray:
    image = image.convert("RGB").resize((224, 224))
    arr = np.array(image, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)  # HWC -> CHW
    return np.expand_dims(arr, axis=0)  # add batch dim


def predict(image: Image.Image) -> dict:
    tensor = preprocess(image)
    outputs = session.run(None, {input_name: tensor})
    logits = outputs[0][0]
    logits = logits - logits.max()  # numerical stability
    probs = np.exp(logits) / np.exp(logits).sum()
    label = LABELS[int(np.argmax(probs))]
    return {"label": label, "scores": {l: float(p) for l, p in zip(LABELS, probs)}}


class ClassifyRequest(BaseModel):
    url: str

def check_api_key(credentials: HTTPAuthorizationCredentials = Security(_bearer)):
    if not API_KEY or credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.post("/classify")
async def classify(req: ClassifyRequest, _: None = Security(check_api_key)):
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("GET", req.url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                resp.raise_for_status()
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail=f"Image exceeds {_MAX_IMAGE_MB:g} MB limit")
                    chunks.append(chunk)
                data = b"".join(chunks)
        except HTTPException:
            raise
        except httpx.HTTPError as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image: {e}")

    try:
        image = Image.open(io.BytesIO(data))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode image")

    return predict(image)


@app.get("/health")
def health():
    return {"status": "ok"}
