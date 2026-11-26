"""Small compatible prediction API with class names and RF/DT confidence."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mlflow.sklearn
import numpy as np
import pandas as pd
import joblib


FEATURE_COLUMNS = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
    "sepal area (cm^2)",
    "petal area (cm^2)",
    "sepal ratio",
    "petal ratio",
    "total length (cm)",
    "total width (cm)",
]
SPECIES_NAMES = ["Iris setosa", "Iris versicolor", "Iris virginica"]
TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://mlflow.mlops.svc.cluster.local:5000"
)
MODEL_URI = os.environ.get("MODEL_URI", "models:/iris-model@production")
MODEL = None


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._write_json(200, {"status": "ok", "model": MODEL_URI})
        return self._write_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/invocations":
            return self._write_json(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            rows = payload.get("inputs")
            if not isinstance(rows, list) or not rows:
                raise ValueError("'inputs' must contain at least one row of 10 values.")
            if any(not isinstance(row, list) or len(row) != len(FEATURE_COLUMNS) for row in rows):
                raise ValueError("Each input row must contain exactly 10 features in documented order.")
            values = np.asarray(rows, dtype=float)
            if not np.isfinite(values).all():
                raise ValueError("Input values must be finite numbers.")
            frame = pd.DataFrame(values, columns=FEATURE_COLUMNS)
            predictions = MODEL.predict(frame).astype(int).tolist()
            probabilities = MODEL.predict_proba(frame)
            confidence = probabilities.max(axis=1).astype(float).tolist()
            return self._write_json(
                200,
                {
                    "predictions": predictions,
                    "species": [SPECIES_NAMES[label] for label in predictions],
                    "confidence": confidence,
                    "probabilities": probabilities.astype(float).tolist(),
                },
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            return self._write_json(400, {"error": str(error)})
        except Exception as error:
            return self._write_json(500, {"error": f"Prediction failed: {error}"})


if __name__ == "__main__":
    if MODEL_URI.startswith("models:/"):
        mlflow.set_tracking_uri(TRACKING_URI)
        MODEL = mlflow.sklearn.load_model(MODEL_URI)
    else:
        # A local joblib path supports offline smoke checks and local demos.
        MODEL = joblib.load(MODEL_URI)
    print(f"Loaded {MODEL_URI}; serving on 0.0.0.0:8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
