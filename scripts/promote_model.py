"""Assign MLflow staging and production aliases to a registered model version."""

import argparse

import mlflow
from mlflow.tracking import MlflowClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_name", nargs="?", default="iris-model")
    parser.add_argument("--version", help="Version to promote; defaults to latest")
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:5000")
    args = parser.parse_args()

    mlflow.set_tracking_uri(args.tracking_uri)
    client = MlflowClient()
    versions = client.search_model_versions(f"name='{args.model_name}'")
    if not versions:
        raise SystemExit(f"No registered versions for {args.model_name}")
    version = args.version or str(max(int(item.version) for item in versions))

    client.set_registered_model_alias(args.model_name, "staging", version)
    client.set_registered_model_alias(args.model_name, "production", version)
    print(f"{args.model_name} version {version}: staging and production aliases assigned")


if __name__ == "__main__":
    main()
