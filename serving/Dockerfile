FROM ghcr.io/mlflow/mlflow:latest

RUN python -m pip install --no-cache-dir scikit-learn==1.5.2

ENV MLFLOW_TRACKING_URI=http://mlflow.mlops.svc.cluster.local:5000

CMD ["mlflow", "models", "serve", "--model-uri", "models:/iris-model@production", "--host", "0.0.0.0", "--port", "8080", "--env-manager", "local"]
