# Kubernetes MLOps Iris Project

This workspace contains the existing Minikube/Kubeflow/MLflow Iris project. It is currently a working directory rather than a Git checkout. The live cluster has three Ready Minikube nodes, Kubeflow Pipelines and Nginx Ingress, and MLflow in namespace `mlops` with its 5 GiB PVC mounted at `/mlflow`.

## Run the Iris pipeline

Create a local environment and install the pinned client dependencies:

```bash
cd ~/k8s-mlops
python3 -m venv .venv
.venv/bin/python -m pip install -r pipeline/requirements.txt
.venv/bin/python pipeline/pipeline.py
minikube -p mlops image build -t iris-pipeline:v1 ./pipeline
minikube -p mlops image save iris-pipeline:v1 - > /tmp/iris-pipeline-v1.tar
for node in mlops-m02 mlops-m03; do
  minikube -p mlops cp /tmp/iris-pipeline-v1.tar "$node:/tmp/iris-pipeline-v1.tar"
  minikube -p mlops ssh -n "$node" -- sudo ctr -n k8s.io images import /tmp/iris-pipeline-v1.tar
done
kubectl -n kubeflow port-forward svc/ml-pipeline 8888:8888
```

In another terminal, submit and wait for a run:

```bash
.venv/bin/python scripts/run_iris_pipeline.py
```

The pipeline reads the checked-in Iris CSV, adds six derived features, makes a stratified split, chooses between Random Forest and Decision Tree using training-only cross-validation, logs test metrics, and registers the model as `iris-model`. The final component promotes it to the Production stage and assigns `staging` and `production` aliases. To repair aliases manually after a run, use `scripts/promote_model.py` while the MLflow port-forward is active.

## Enhanced 10-feature model

Create `data/iris_enhanced.csv`, compare Random Forest and Decision Tree models, evaluate the four-feature baseline and selected 10-feature model, and save the selected model plus report:

```bash
pipeline/venv/bin/python scripts/train_enhanced_model.py
```

The original `data/iris.csv` stays unchanged. The enhanced CSV keeps the four measurements and adds sepal area, petal area, sepal ratio, petal ratio, total length, and total width. Ratios are set to `0` when their denominator is zero. The training script uses a stratified 80/20 split and training-only cross-validation; missing numeric values are imputed inside each fitted model. It writes `models/iris_best_model.joblib` and `models/training_report.json`.

The Kubeflow pipeline uses the same checked-in CSV, creates the engineered values, compares Random Forest and Decision Tree on training folds, evaluates the selected model, and registers it in MLflow. Pipeline task pods use the prebuilt `iris-pipeline:v1` image so they do not need to download Python packages from the network at runtime. Recompile and rebuild it after changing pipeline code:

```bash
pipeline/venv/bin/python pipeline/pipeline.py
minikube -p mlops image build -t iris-pipeline:v1 ./pipeline
minikube -p mlops image save iris-pipeline:v1 - > /tmp/iris-pipeline-v1.tar
for node in mlops-m02 mlops-m03; do
  minikube -p mlops cp /tmp/iris-pipeline-v1.tar "$node:/tmp/iris-pipeline-v1.tar"
  minikube -p mlops ssh -n "$node" -- sudo ctr -n k8s.io images import /tmp/iris-pipeline-v1.tar
done
```

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
minikube -p mlops image build -t iris-serving:v3 ./serving
minikube -p mlops ssh -n mlops -- sudo ctr -n k8s.io images export /tmp/iris-serving-v3.tar docker.io/library/iris-serving:v3
minikube -p mlops cp mlops:/tmp/iris-serving-v3.tar /tmp/iris-serving-v3.tar
minikube -p mlops image load /tmp/iris-serving-v3.tar
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
  -d '{"inputs":[[5.1,3.5,1.4,0.2,17.85,0.28,1.457142857142857,7.0,6.5,3.7]]}' \
  http://127.0.0.1:8081/invocations
```

The API response includes the predicted class (`0`, `1`, or `2`), species name, confidence, and class probabilities. In Postman, the prediction request calculates the six engineered values from the four collection variables `sepal_length`, `sepal_width`, `petal_length`, and `petal_width`.

With the serving service port-forwarded to `8080:80`, the same inference request can be checked with `.venv/bin/python scripts/smoke_test_serving.py`.

## Demonstration checklist

For the required screen recording, show `kubectl get nodes -o wide`, the Iris pipeline run and its accuracy in the Kubeflow Pipelines UI, the `iris-model` Production version in MLflow, and a successful `/invocations` request through the Nginx ingress. Keep the port-forward terminals visible so the local endpoints are clear.

## One-command demo menu

From WSL Ubuntu, run:

```bash
cd ~/k8s-mlops
bash scripts/demo.sh
```

Choose `1` to start/check the `mlops` cluster, open Kubeflow UI, MLflow, and serving health in the browser, and check Jenkins. Kubeflow UI is at `http://127.0.0.1:8889`; its API remains forwarded on `8888` for pipeline submissions. Choose `5` to run a sample prediction and test the Nginx ingress; choose `6` to compile and submit a fresh pipeline run; choose `8` to open a browser page with a form that sends prediction requests. Port-forwards stay running in the background. Serving health is forwarded on port `8082`; Jenkins is opened using the current WSL IP on port `8080`. If Jenkins is stopped, choose `4`; the menu prints `sudo service jenkins start`.

## Project state and operational notes

- `terraform/main.tf` uses a local-exec provisioner that starts Minikube and also deletes the cluster when Terraform destroys that resource. Do not run `terraform destroy` against the live cluster.
- Terraform CLI was not installed in the current WSL shell when checked; the live Minikube cluster is already running, so the CLI was not installed during this pass.
- The MLflow deployment manifest references the existing `mlflow-pvc`; it does not create or delete that PVC.
- `Jenkinsfile` compiles and runs the Kubeflow pipeline, assigns model aliases, builds the serving image on all Minikube nodes, and deploys it. Jenkins 2.580.2 runs as a WSL host service. The Jenkins job requires an online agent labeled `mlops-wsl`, using the existing Python 3.11 environment at `/home/mohsin/k8s-mlops/pipeline/venv/bin/python`, and a Secret file credential with ID `mlops-kubeconfig` for the kubeconfig.
- The assignment asks for a live GitHub link and screen recording. The current project repository is https://github.com/mohsinsaeed092005-debug/k8s-mlops. The recording still needs to be made on the user's desktop.
