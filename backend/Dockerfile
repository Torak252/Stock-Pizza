FROM python:3.12-slim
# libgl/glib: OpenCV runtime deps pulled in by ultralytics
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# CPU-only PyTorch first, so the vision extra doesn't pull multi-GB CUDA wheels
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml ./
COPY pizza_tracker ./pizza_tracker
RUN pip install --no-cache-dir ".[vision]"
EXPOSE 8000
CMD ["uvicorn", "pizza_tracker.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
