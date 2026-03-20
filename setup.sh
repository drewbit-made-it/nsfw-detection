#!/bin/bash
set -e

if [ -f model.onnx ]; then
  echo "==> model.onnx already exists, skipping export."
else
  echo "==> Exporting ONNX model..."
  uvx --with torch --with transformers --with "optimum[onnxruntime]" python -c "
from optimum.onnxruntime import ORTModelForImageClassification
model = ORTModelForImageClassification.from_pretrained('Falconsai/nsfw_image_detection', export=True)
model.save_pretrained('nsfw_model')
"
  mv nsfw_model/model.onnx .
  rm -rf nsfw_model
fi

echo "==> Installing dependencies..."
uv sync

if [ ! -f model_int8.onnx ]; then
  echo "==> Generating int8 model..."
  uv run --extra quantize python quantize.py
else
  echo "==> model_int8.onnx already exists, skipping quantization."
fi

echo "==> Done. Start the server with:"
echo "    uv run uvicorn main:app --port 8080 --reload"
echo "    USE_INT8=true uv run uvicorn main:app --port 8080 --reload"
