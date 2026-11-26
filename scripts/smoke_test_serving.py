"""Send a 10-feature Iris record to the serving endpoint and verify its output."""

import argparse
import json
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    request = Request(
        f"{args.url.rstrip('/')}/invocations",
        data=json.dumps({"inputs": [[5.1, 3.5, 1.4, 0.2, 17.85, 0.28, 5.1 / 3.5, 7.0, 6.5, 3.7]]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")

    predictions = payload.get("predictions")
    if predictions is None or len(predictions) != 1 or predictions[0] not in (0, 1, 2):
        raise RuntimeError(f"Unexpected response body: {payload}")
    if len(payload.get("species", [])) != 1 or len(payload.get("confidence", [])) != 1:
        raise RuntimeError(f"Response is missing species or confidence: {payload}")
    print(
        f"HTTP 200; prediction: {payload['species'][0]} ({predictions[0]}), "
        f"confidence: {payload['confidence'][0]:.3f}"
    )


if __name__ == "__main__":
    main()
