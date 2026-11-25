# Kubernetes MLOps Iris Project

This workspace contains the existing Minikube/Kubeflow/MLflow Iris project. It is currently a working directory rather than a Git checkout. The live cluster has three Ready Minikube nodes, Kubeflow Pipelines and Nginx Ingress, and MLflow in namespace `mlops` with its 5 GiB PVC mounted at `/mlflow`.

## Run the Iris pipeline

Create a local environment and install the pinned client dependencies:

```bash
cd ~/k8s-mlops
python3 -m venv .venv
.venv/bin/python -m pip install -r pipeline/requirements.txt
.venv/bin/python pipeline/pipeline.py
kubectl -n kubeflow port-forward svc/ml-pipeline 8888:8888
```

In another terminal, submit and wait for a run:

```bash
.venv/bin/python scripts/run_iris_pipeline.py
```

The pipeline loads and splits Iris data, trains a Random Forest, logs accuracy, and registers the model as `iris-model`. The final component promotes it to the Production stage and assigns `staging` and `production` aliases. To repair aliases manually after a run, use `scripts/promote_model.py` while the MLflow port-forward is active.

## Verify MLflow artifacts

```bash
kubectl -n mlops port-forward svc/mlflow 5000:5000
```

In another terminal:

```bash
.venv/bin/python scripts/verify_mlflow_artifacts.py
.venv/bin/python scripts/check_mlflow_registry.py
```

The artifact check makes a small verification run in the `iris` experiment, uploads a text file, lists it, downloads it, and checks its contents. MLflow artifact and SQLite data are stored on `mlflow-pvc`.

## Build and deploy model serving

Run the Iris pipeline successfully first so `iris-model@production` exists. Build the image into the Minikube cluster and apply the manifests:

```bash
minikube -p mlops image build -t iris-serving:latest ./serving
kubectl apply -k k8s
kubectl -n mlops rollout status deployment/iris-serving
kubectl -n mlops get pods -l app=iris-serving -o wide
```

The serving deployment has three replicas, a Kubernetes Service, topology spreading across nodes, and an Ingress rule routed by the Nginx controller at host `iris.local`. The model server reads the Production alias from MLflow at startup.

For a local Nginx ingress check:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8081:80
curl -H 'Host: iris.local' http://127.0.0.1:8081/health
curl -H 'Host: iris.local' -H 'Content-Type: application/json' \
  -d '{"inputs":[[5.1,3.5,1.4,0.2]]}' \
  http://127.0.0.1:8081/invocations
```

With the serving service port-forwarded to `8080:80`, the same inference request can be checked with `.venv/bin/python scripts/smoke_test_serving.py`.

## Demonstration checklist

For the required screen recording, show `kubectl get nodes -o wide`, the Iris pipeline run and its accuracy in the Kubeflow Pipelines UI, the `iris-model` Production version in MLflow, and a successful `/invocations` request through the Nginx ingress. Keep the port-forward terminals visible so the local endpoints are clear.

## Project state and operational notes

- `terraform/main.tf` uses a local-exec provisioner that starts Minikube and also deletes the cluster when Terraform destroys that resource. Do not run `terraform destroy` against the live cluster.
- Terraform CLI was not installed in the current WSL shell when checked; the live Minikube cluster is already running, so the CLI was not installed during this pass.
- The MLflow deployment manifest references the existing `mlflow-pvc`; it does not create or delete that PVC.
- `Jenkinsfile` compiles and runs the Kubeflow pipeline, assigns model aliases, builds the serving image on all Minikube nodes, and deploys it. Jenkins 2.580.2 runs as a WSL host service. The Jenkins job requires an online agent labeled `mlops-wsl`, using the existing Python 3.11 environment at `/home/mohsin/k8s-mlops/pipeline/venv/bin/python`, and a Secret file credential with ID `mlops-kubeconfig` for the kubeconfig.
- The attached assignment asks for the live GitHub repository link and a screen recording. The active workspace has no `.git` directory, so changes here cannot be committed or pushed until it is placed in the intended repository. Two separate checkouts were found at `https://github.com/mohsinsaeed092005-debug/k8s-project.git` and `https://github.com/mohsinsaeed092005-debug/mlops-flask-project.git`; neither is this complete workspace.
