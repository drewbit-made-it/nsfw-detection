"""
One-time script to produce model_int8.onnx from model.onnx.
Run via setup.sh or manually: uv run python quantize.py
Requires: onnx, onnxruntime (both only needed here, not at inference time)
"""
import os
from onnxruntime.quantization import quantize_dynamic, QuantType
from onnxruntime.quantization.shape_inference import quant_pre_process

SRC = "model.onnx"
PRE = "model_preprocessed.onnx"
DST = "model_int8.onnx"

if not os.path.exists(SRC):
    raise FileNotFoundError(f"{SRC} not found — run setup.sh first")

print("==> Running pre-processing (shape inference)...")
quant_pre_process(SRC, PRE)

print("==> Quantizing to int8...")
quantize_dynamic(PRE, DST, weight_type=QuantType.QInt8)

os.remove(PRE)
print(f"==> Done. Wrote {DST}")
