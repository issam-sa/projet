FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline ./pipeline

ENTRYPOINT ["python", "-m", "pipeline.run_etl"]
CMD ["--mode", "sample", "--days", "14"]
