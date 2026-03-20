# ── Stage 1: quantize ──────────────────────────────────────────────────────────
# Full deps including onnx; produces model_int8.onnx then is discarded.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS quantizer

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra quantize

COPY quantize.py model.onnx ./
RUN uv run python quantize.py

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
# No onnx, no quantize tooling — just what's needed to serve.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py model.onnx ./
COPY --from=quantizer /app/model_int8.onnx ./

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
