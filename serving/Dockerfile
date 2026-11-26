FROM ghcr.io/mlflow/mlflow:latest

RUN python -m pip install --no-cache-dir scikit-learn==1.5.2 pandas==2.2.3

WORKDIR /app
COPY app.py /app/app.py

ENV MLFLOW_TRACKING_URI=http://mlflow.mlops.svc.cluster.local:5000

CMD ["python", "/app/app.py"]
