"""Print models and the selected version aliases in an MLflow registry."""

import argparse

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    mlflow.set_tracking_uri(args.tracking_uri)

    client = MlflowClient()
    models = client.search_registered_models()
    if not models:
        print("No registered models found")
        return

    for model in models:
        print(f"model: {model.name}")
        for version in model.latest_versions or []:
            print(
                f"  version={version.version} stage={version.current_stage} "
                f"aliases={version.aliases} status={version.status}"
            )
        for alias in ("staging", "production"):
            try:
                version = client.get_model_version_by_alias(model.name, alias)
                print(f"  alias {alias} -> version {version.version}")
            except MlflowException:
                print(f"  alias {alias}: not set")


if __name__ == "__main__":
    main()
