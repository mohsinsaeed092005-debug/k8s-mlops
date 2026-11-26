"""Compile the Kubeflow Iris training pipeline with engineered features."""

import base64
from pathlib import Path

from kfp import compiler, dsl
from kfp.dsl import Dataset, Input, Metrics, Model, Output


# Build and load this image into every Minikube node before submitting runs.
# Pipeline task pods then use the installed packages without needing pod DNS.
BASE = "iris-pipeline:v1"
DATA_CSV_B64 = base64.b64encode(
    (Path(__file__).resolve().parents[1] / "data" / "iris.csv").read_bytes()
).decode("ascii")


@dsl.component(base_image=BASE, install_kfp_package=False)
def load_data(data_csv_b64: str, train_data: Output[Dataset], test_data: Output[Dataset]):
    """Read the checked-in data, engineer features, then make a stratified split."""
    import base64
    import io

    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split

    raw_columns = [
        "sepal length (cm)",
        "sepal width (cm)",
        "petal length (cm)",
        "petal width (cm)",
    ]
    csv_bytes = base64.b64decode(data_csv_b64)
    df = pd.read_csv(io.BytesIO(csv_bytes))
    for column in raw_columns + ["target"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["target"]).copy()
    df["sepal area (cm^2)"] = df[raw_columns[0]] * df[raw_columns[1]]
    df["petal area (cm^2)"] = df[raw_columns[2]] * df[raw_columns[3]]
    # Use zero for ratios with a zero denominator; missing input remains missing
    # and is imputed from training data only in the model pipeline.
    df["sepal ratio"] = np.divide(
        df[raw_columns[0]].to_numpy(float), df[raw_columns[1]].to_numpy(float),
        out=np.zeros(len(df), dtype=float), where=df[raw_columns[1]].to_numpy(float) != 0,
    )
    df["petal ratio"] = np.divide(
        df[raw_columns[2]].to_numpy(float), df[raw_columns[3]].to_numpy(float),
        out=np.zeros(len(df), dtype=float), where=df[raw_columns[3]].to_numpy(float) != 0,
    )
    df["total length (cm)"] = df[raw_columns[0]] + df[raw_columns[2]]
    df["total width (cm)"] = df[raw_columns[1]] + df[raw_columns[3]]
    df["target"] = df["target"].astype(int)

    train, test = train_test_split(
        df, test_size=0.2, random_state=42, stratify=df["target"]
    )
    train.to_csv(train_data.path, index=False)
    test.to_csv(test_data.path, index=False)


@dsl.component(
    base_image=BASE,
    install_kfp_package=False,
)
def train(train_data: Input[Dataset], model_out: Output[Model], n_estimators: int = 100):
    """Select RF or Decision Tree by training-only cross validation."""
    import joblib
    import pandas as pd
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier

    df = pd.read_csv(train_data.path)
    X, y = df.drop(columns="target"), df["target"]
    candidates = {
        "random_forest": RandomForestClassifier(n_estimators=n_estimators, random_state=42),
        "decision_tree": DecisionTreeClassifier(random_state=42),
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = {
        name: cross_val_score(
            make_pipeline(SimpleImputer(strategy="median"), estimator),
            X, y, cv=cv, scoring="f1_macro",
        ).mean()
        for name, estimator in candidates.items()
    }
    best_name = max(scores, key=scores.get)
    best_model = make_pipeline(
        SimpleImputer(strategy="median"), candidates[best_name]
    ).fit(X, y)
    joblib.dump(best_model, model_out.path)
    model_out.metadata["algorithm"] = best_name
    model_out.metadata["cv_f1_macro"] = float(scores[best_name])
    print(f"Selected {best_name}; CV macro F1={scores[best_name]:.4f}; all features={list(X.columns)}")


@dsl.component(
    base_image=BASE,
    install_kfp_package=False,
)
def evaluate(model_in: Input[Model], test_data: Input[Dataset], metrics: Output[Metrics]) -> float:
    import joblib
    import pandas as pd
    from sklearn.metrics import (
        accuracy_score, classification_report, confusion_matrix,
        f1_score, precision_score, recall_score,
    )

    model = joblib.load(model_in.path)
    df = pd.read_csv(test_data.path)
    X, y = df.drop(columns="target"), df["target"]
    predicted = model.predict(X)
    accuracy = float(accuracy_score(y, predicted))
    metrics.log_metric("accuracy", accuracy)
    metrics.log_metric("precision_macro", float(precision_score(y, predicted, average="macro", zero_division=0)))
    metrics.log_metric("recall_macro", float(recall_score(y, predicted, average="macro", zero_division=0)))
    metrics.log_metric("f1_macro", float(f1_score(y, predicted, average="macro", zero_division=0)))
    print("Confusion matrix (classes 0, 1, 2):\n", confusion_matrix(y, predicted, labels=[0, 1, 2]))
    print("Classification report:\n", classification_report(y, predicted, labels=[0, 1, 2], target_names=["setosa", "versicolor", "virginica"], zero_division=0))
    return accuracy


@dsl.component(
    base_image=BASE,
    install_kfp_package=False,
)
def register_model(model_in: Input[Model], accuracy: float, tracking_uri: str, model_name: str):
    import joblib
    import mlflow
    import mlflow.sklearn
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("iris")
    model = joblib.load(model_in.path)
    with mlflow.start_run():
        mlflow.log_metric("test_accuracy", accuracy)
        mlflow.sklearn.log_model(
            model, name="model", registered_model_name=model_name,
            skops_trusted_types=["sklearn.tree._tree.Tree", "numpy.dtype"],
        )

    client = MlflowClient()
    versions = client.search_model_versions(f"name='{model_name}'")
    version = str(max(int(item.version) for item in versions))
    try:
        client.transition_model_version_stage(model_name, version, "Staging")
        client.transition_model_version_stage(model_name, version, "Production")
    except Exception as error:
        print("Stage transition unavailable; assigning aliases:", error)
    client.set_registered_model_alias(model_name, "staging", version)
    client.set_registered_model_alias(model_name, "production", version)
    print(f"Aliases staging and production now point to version {version}")


@dsl.pipeline(name="iris-pipeline", description="Engineer 10 Iris features -> Train -> Evaluate -> Register")
def iris_pipeline(
    tracking_uri: str = "http://mlflow.mlops.svc.cluster.local:5000",
    model_name: str = "iris-model",
    n_estimators: int = 100,
    data_csv_b64: str = DATA_CSV_B64,
):
    data_task = load_data(data_csv_b64=data_csv_b64)
    train_task = train(
        train_data=data_task.outputs["train_data"], n_estimators=n_estimators
    )
    evaluation_task = evaluate(
        model_in=train_task.outputs["model_out"],
        test_data=data_task.outputs["test_data"],
    )
    register_model(
        model_in=train_task.outputs["model_out"],
        accuracy=evaluation_task.outputs["Output"],
        tracking_uri=tracking_uri,
        model_name=model_name,
    )


if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=iris_pipeline, package_path="pipeline/pipeline.yaml"
    )
