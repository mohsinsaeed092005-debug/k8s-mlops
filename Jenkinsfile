pipeline {
    agent { label 'mlops-wsl' }

    environment {
        PROJECT_PYTHON = '/home/mohsin/k8s-mlops/pipeline/venv/bin/python'
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Compile pipeline') {
            steps {
                sh '$PROJECT_PYTHON --version'
                sh '$PROJECT_PYTHON pipeline/pipeline.py'
            }
        }

        stage('Build pipeline runtime image') {
            steps {
                sh '''
                    set -eu
                    minikube -p mlops image build -t iris-pipeline:v1 ./pipeline
                    minikube -p mlops image save iris-pipeline:v1 - > /tmp/iris-pipeline-v1.tar
                    for node in mlops-m02 mlops-m03; do
                        minikube -p mlops cp /tmp/iris-pipeline-v1.tar "$node:/tmp/iris-pipeline-v1.tar"
                        minikube -p mlops ssh -n "$node" -- sudo ctr -n k8s.io images import /tmp/iris-pipeline-v1.tar
                    done
                '''
            }
        }

        stage('Run Kubeflow pipeline') {
            steps {
                withCredentials([file(credentialsId: 'mlops-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh '''
                        set -eu
                        kubectl -n kubeflow port-forward svc/ml-pipeline 8888:8888 >/tmp/kfp-port-forward.log 2>&1 &
                        PF_PID=$!
                        trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
                        sleep 5
                        "$PROJECT_PYTHON" scripts/run_iris_pipeline.py --host http://127.0.0.1:8888 --timeout 3600
                    '''
                }
            }
        }

        stage('Promote model') {
            steps {
                withCredentials([file(credentialsId: 'mlops-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh '''
                        set -eu
                        kubectl -n mlops port-forward svc/mlflow 5000:5000 >/tmp/mlflow-port-forward.log 2>&1 &
                        PF_PID=$!
                        trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
                        sleep 5
                        "$PROJECT_PYTHON" scripts/promote_model.py iris-model --tracking-uri http://127.0.0.1:5000
                    '''
                }
            }
        }

        stage('Build serving image') {
            steps {
                sh '''
                    set -eu
                    minikube -p mlops image build -t iris-serving:v3 ./serving
                    minikube -p mlops ssh -n mlops -- sudo ctr -n k8s.io images export /tmp/iris-serving-v3.tar docker.io/library/iris-serving:v3
                    minikube -p mlops cp mlops:/tmp/iris-serving-v3.tar /tmp/iris-serving-v3.tar
                    minikube -p mlops image load /tmp/iris-serving-v3.tar
                '''
            }
        }

        stage('Deploy to Minikube') {
            steps {
                withCredentials([file(credentialsId: 'mlops-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh 'kubectl apply -k k8s'
                    sh 'kubectl -n mlops rollout status deployment/mlflow --timeout=180s'
                    sh 'kubectl -n mlops rollout status deployment/iris-serving --timeout=300s'
                }
            }
        }
    }
}
