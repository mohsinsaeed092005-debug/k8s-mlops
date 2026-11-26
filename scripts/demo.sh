#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="${XDG_RUNTIME_DIR:-/tmp}/k8s-mlops-demo-${USER:-user}"
LOG_DIR="${HOME}/.cache/k8s-mlops-demo"
PYTHON_BIN=""
mkdir -p "$PID_DIR" "$LOG_DIR"

open_url() {
  local url="$1"
  if command -v wslview >/dev/null 2>&1; then
    wslview "$url" >/dev/null 2>&1 &
  elif command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$url" >/dev/null 2>&1 &
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  else
    printf 'Browser mein kholen: %s\n' "$url"
  fi
}

ensure_cluster() {
  if ! command -v minikube >/dev/null 2>&1; then
    echo 'Minikube command nahi mila. WSL Ubuntu terminal use karein.' >&2
    exit 1
  fi
  echo 'Minikube mlops cluster check/start ho raha hai...'
  if ! kubectl --context mlops get nodes >/dev/null 2>&1; then
    minikube -p mlops start
  else
    echo 'mlops cluster pehle se chal raha hai.'
  fi
  kubectl config use-context mlops >/dev/null
  kubectl wait --for=condition=Ready nodes --all --timeout=180s
}

port_is_open() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" | grep -q LISTEN
  else
    (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1
  fi
}

ensure_forward() {
  local name="$1" namespace="$2" target="$3" local_port="$4" service_port="$5"
  local pid_file="$PID_DIR/$name.pid" log_file="$LOG_DIR/$name.log" pid
  if port_is_open "$local_port"; then
    echo "$name: localhost:$local_port pe pehle se available hai."
    return
  fi
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "$name port-forward start ho raha hai; log: $log_file"
      for _ in {1..20}; do
        port_is_open "$local_port" && return
        sleep 1
      done
      echo "$name port-forward nahi chala. Log dekhein: $log_file" >&2
      return 1
    fi
    rm -f "$pid_file"
  fi
  nohup kubectl -n "$namespace" port-forward --address 127.0.0.1 "svc/$target" "$local_port:$service_port" >"$log_file" 2>&1 </dev/null &
  pid=$!
  echo "$pid" >"$pid_file"
  for _ in {1..20}; do
    port_is_open "$local_port" && {
      echo "$name ready: http://127.0.0.1:$local_port"
      return
    }
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$name port-forward fail hua. Log dekhein: $log_file" >&2
      return 1
    fi
    sleep 1
  done
  echo "$name port-forward start nahi hua. Log dekhein: $log_file" >&2
  return 1
}

open_kubeflow() {
  # Keep the API forward for pipeline submissions and open the separate UI service.
  ensure_forward kubeflow kubeflow ml-pipeline 8888 8888
  ensure_forward kubeflow-ui kubeflow ml-pipeline-ui 8889 80
  open_url http://127.0.0.1:8889
}

open_mlflow() {
  kubectl -n mlops rollout status deployment/mlflow --timeout=180s
  ensure_forward mlflow mlops mlflow 5000 5000
  open_url http://127.0.0.1:5000
}

open_serving() {
  kubectl -n mlops rollout status deployment/iris-serving --timeout=180s
  ensure_forward serving mlops iris-serving 8082 80
  open_url http://127.0.0.1:8082/health
}

open_jenkins() {
  local wsl_ip jenkins_url
  wsl_ip="$(hostname -I | awk '{print $1}')"
  jenkins_url="http://${wsl_ip}:8080"
  if curl -fsS --max-time 3 "$jenkins_url/login" >/dev/null; then
    echo "Jenkins browser URL: $jenkins_url"
    open_url "$jenkins_url"
  else
    echo "Jenkins $jenkins_url par abhi jawab nahi de raha."
    echo 'Jenkins WSL service start karein: sudo service jenkins start'
  fi
}

open_prediction_page() {
  ensure_cluster
  open_serving
  if ! port_is_open 8090; then
    local pid
    nohup python3 "$PROJECT_DIR/scripts/predict_web.py" >"$LOG_DIR/predict-web.log" 2>&1 </dev/null &
    pid=$!
    echo "$pid" >"$PID_DIR/predict-web.pid"
    for _ in {1..20}; do
      port_is_open 8090 && break
      kill -0 "$pid" 2>/dev/null || {
        echo "Prediction page start nahi hua. Log dekhein: $LOG_DIR/predict-web.log" >&2
        return 1
      }
      sleep 1
    done
  fi
  local url
  url="http://$(hostname -I | awk '{print $1}'):8090"
  echo "Browser prediction page: $url"
  open_url "$url"
}

ensure_python_env() {
  if [[ -x "$PROJECT_DIR/pipeline/venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/pipeline/venv/bin/python"
  elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
  else
    if command -v python3.11 >/dev/null 2>&1; then
      python3.11 -m venv "$PROJECT_DIR/.venv"
    else
      echo 'Python 3.11 environment nahi mila; KFP dependency Python 3.11 maangti hai.' >&2
      return 1
    fi
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
  fi
  if ! "$PYTHON_BIN" -c 'import kfp' >/dev/null 2>&1; then
    echo 'Pipeline dependencies install ho rahi hain...'
    "$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/pipeline/requirements.txt"
  fi
}

open_all() {
  ensure_cluster
  open_kubeflow
  open_mlflow
  open_serving
  open_jenkins
  echo
  echo 'Kubeflow UI: http://127.0.0.1:8889'
  echo 'Kubeflow API: http://127.0.0.1:8888'
  echo 'MLflow:   http://127.0.0.1:5000'
  echo "Jenkins:  http://$(hostname -I | awk '{print $1}'):8080"
  echo 'Serving:  http://127.0.0.1:8082/health'
}

run_prediction() {
  ensure_cluster
  ensure_python_env
  open_serving
  echo 'Iris sample prediction chal rahi hai...'
  "$PYTHON_BIN" "$PROJECT_DIR/scripts/smoke_test_serving.py" --url http://127.0.0.1:8082
  echo 'Ingress endpoint bhi verify ho raha hai...'
  ensure_forward ingress ingress-nginx ingress-nginx-controller 8081 80
  curl -fsS -H 'Host: iris.local' http://127.0.0.1:8081/health
  echo
  curl -fsS -H 'Host: iris.local' -H 'Content-Type: application/json' \
    -d '{"inputs":[[5.1,3.5,1.4,0.2,17.85,0.28,1.457142857142857,7.0,6.5,3.7]]}' http://127.0.0.1:8081/invocations
  echo
}

run_pipeline() {
  ensure_cluster
  ensure_python_env
  "$PYTHON_BIN" "$PROJECT_DIR/pipeline/pipeline.py"
  minikube -p mlops image tag iris-pipeline:latest iris-pipeline:v1
  minikube -p mlops image save iris-pipeline:v1 - > /tmp/iris-pipeline-v1.tar
  for node in mlops-m02 mlops-m03; do
    minikube -p mlops cp /tmp/iris-pipeline-v1.tar "$node:/tmp/iris-pipeline-v1.tar"
    minikube -p mlops ssh -n "$node" -- sudo ctr -n k8s.io images import /tmp/iris-pipeline-v1.tar
  done
  ensure_forward kubeflow kubeflow ml-pipeline 8888 8888
  "$PYTHON_BIN" "$PROJECT_DIR/scripts/run_iris_pipeline.py"
}

while true; do
  cat <<'MENU'

=== Iris MLOps Demo ===
1) Sab dashboards open karo
2) MLflow open karo
3) Kubeflow open karo
4) Jenkins open/check karo
5) Prediction + ingress test chalao
6) Naya Iris pipeline run karo
7) Cluster/pods status dikhao
8) Browser prediction page kholo
0) Band karo
MENU
  read -r -p 'Option: ' choice
  case "$choice" in
    1) open_all ;;
    2) ensure_cluster; open_mlflow ;;
    3) ensure_cluster; open_kubeflow ;;
    4) open_jenkins ;;
    5) run_prediction ;;
    6) run_pipeline ;;
    7) kubectl get nodes -o wide; kubectl get pods -A ;;
    8) open_prediction_page ;;
    0) exit 0 ;;
    *) echo 'Option 0 se 7 tak choose karein.' ;;
  esac
done
