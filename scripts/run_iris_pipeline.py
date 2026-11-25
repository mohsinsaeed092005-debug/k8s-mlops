"""Submit the compiled Iris pipeline to a reachable Kubeflow Pipelines API."""

import argparse
from pathlib import Path

import kfp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://127.0.0.1:8888")
    parser.add_argument(
        "--pipeline", default=str(Path(__file__).resolve().parents[1] / "pipeline" / "pipeline.yaml")
    )
    parser.add_argument("--experiment", default="iris")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    client = kfp.Client(host=args.host)
    run = client.create_run_from_pipeline_package(
        pipeline_file=args.pipeline,
        experiment_name=args.experiment,
        run_name="iris-end-to-end",
        enable_caching=False,
    )
    print(f"run_id: {run.run_id}")
    print(f"run_url: {args.host.rstrip('/')}/#/runs/details/{run.run_id}")
    result = client.wait_for_run_completion(run.run_id, timeout=args.timeout)
    print(f"status: {result.state}")
    if result.state != "SUCCEEDED":
        raise SystemExit(f"Pipeline run finished with state {result.state}")


if __name__ == "__main__":
    main()
