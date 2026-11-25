"""Upload, list, and download a small artifact through the MLflow server."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:5000")
    parser.add_argument("--experiment", default="iris")
    args = parser.parse_args()

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment)
    client = MlflowClient()

    with tempfile.TemporaryDirectory(prefix="mlflow-artifact-check-") as temp_dir:
        source = Path(temp_dir) / "round-trip.txt"
        source.write_text("MLflow artifact round-trip verification\n", encoding="utf-8")

        with mlflow.start_run(run_name="artifact-roundtrip-verification") as run:
            run_id = run.info.run_id
            mlflow.log_artifact(str(source), artifact_path="verification")

        artifacts = client.list_artifacts(run_id, "verification")
        expected_path = "verification/round-trip.txt"
        if not any(item.path == expected_path for item in artifacts):
            raise RuntimeError(f"Artifact not listed: {expected_path}")

        downloaded_path = client.download_artifacts(run_id, expected_path)
        downloaded = Path(downloaded_path).read_text(encoding="utf-8")
        if downloaded != source.read_text(encoding="utf-8"):
            raise RuntimeError("Downloaded artifact content does not match upload")

    print(f"tracking_uri: {args.tracking_uri}")
    print(f"experiment: {args.experiment}")
    print(f"run_id: {run_id}")
    print(f"artifact: {expected_path}")
    print("upload/list/download: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
