"""Small browser UI that forwards Iris predictions to the local serving port."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Iris Model Prediction</title>
  <style>
    body{font:16px system-ui,sans-serif;background:#f4f7fb;color:#172033;margin:0;padding:32px}
    main{max-width:620px;margin:auto;background:white;padding:28px;border-radius:16px;box-shadow:0 8px 30px #19345a18}
    h1{margin-top:0}p{color:#526078}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    label{display:grid;gap:6px;font-size:14px}input{padding:11px;border:1px solid #bcc8d8;border-radius:8px;font:inherit}
    button{margin-top:20px;padding:12px 20px;border:0;border-radius:8px;background:#2563eb;color:white;font:inherit;cursor:pointer}
    pre{white-space:pre-wrap;background:#eef3fa;padding:14px;border-radius:8px;min-height:24px}
  </style>
</head>
<body><main>
  <h1>Iris model prediction</h1>
  <p>Enter sepal and petal measurements in centimeters.</p>
  <form id="predict-form"><div class="grid">
    <label>Sepal length<input name="sepal_length" type="number" step="any" value="5.1" required></label>
    <label>Sepal width<input name="sepal_width" type="number" step="any" value="3.5" required></label>
    <label>Petal length<input name="petal_length" type="number" step="any" value="1.4" required></label>
    <label>Petal width<input name="petal_width" type="number" step="any" value="0.2" required></label>
  </div><button type="submit">Predict</button></form>
  <h2>Result</h2><pre id="result">Enter values and select Predict.</pre>
</main>
<script>
document.querySelector('#predict-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const [sepalLength, sepalWidth, petalLength, petalWidth] = [...new FormData(event.currentTarget).values()].map(Number);
  const safeRatio = (numerator, denominator) => denominator === 0 ? 0 : numerator / denominator;
  const values = [
    sepalLength, sepalWidth, petalLength, petalWidth,
    sepalLength * sepalWidth, petalLength * petalWidth,
    safeRatio(sepalLength, sepalWidth), safeRatio(petalLength, petalWidth),
    sepalLength + petalLength, sepalWidth + petalWidth
  ];
  const result = document.querySelector('#result'); result.textContent = 'Predicting…';
  try {
    const response = await fetch('/predict', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inputs:[values]})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    const label = data.predictions[0];
    const species = data.species?.[0] || ['Iris setosa','Iris versicolor','Iris virginica'][label] || 'unknown class';
    const confidence = data.confidence?.[0];
    result.textContent = `Prediction: ${species} (class ${label})${confidence === undefined ? '' : `\nConfidence: ${(confidence * 100).toFixed(1)}%`}`;
  } catch (error) { result.textContent = `Prediction failed: ${error.message}`; }
});
</script></body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self) -> None:
        if self.path != "/predict":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            inputs = payload["inputs"]
            if len(inputs) != 1 or len(inputs[0]) != 10:
                raise ValueError("Provide exactly one record with 10 features (four measurements and six engineered values).")
            request = Request(
                "http://127.0.0.1:8082/invocations",
                data=json.dumps({"inputs": inputs}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=20) as response:
                body = response.read()
                status = response.status
        except HTTPError as exc:
            body, status = exc.read(), exc.code
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            body, status = json.dumps({"error": str(exc)}).encode(), 400
        except (URLError, TimeoutError, OSError) as exc:
            body, status = json.dumps({"error": f"Serving endpoint unavailable: {exc}"}).encode(), 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("Iris prediction page listening on 0.0.0.0:8090", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
