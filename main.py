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
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

# Load model once at startup — tuned for low RAM in serverless
_opts = ort.SessionOptions()
_opts.intra_op_num_threads = 1
_opts.inter_op_num_threads = 1
_opts.enable_cpu_mem_arena = False          # return memory to OS between calls
_opts.enable_mem_pattern = False            # don't pre-allocate for fixed patterns
_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
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
                        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")
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
