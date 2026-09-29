FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY pizza_tracker ./pizza_tracker
RUN pip install --no-cache-dir ".[vision]"
EXPOSE 8000
CMD ["uvicorn", "pizza_tracker.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
