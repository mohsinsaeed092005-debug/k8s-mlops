"""Send one Iris record to a reachable MLflow pyfunc serving endpoint."""

import argparse
import json
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    request = Request(
        f"{args.url.rstrip('/')}/invocations",
        data=json.dumps({"inputs": [[5.1, 3.5, 1.4, 0.2]]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")

    predictions = payload.get("predictions")
    if predictions is None or len(predictions) != 1:
        raise RuntimeError(f"Unexpected response body: {payload}")
    print(f"HTTP 200; prediction: {predictions[0]}")


if __name__ == "__main__":
    main()
