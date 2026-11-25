
from kfp import dsl, compiler
from kfp.dsl import Dataset, Input, Output, Model, Metrics

BASE = "python:3.11"
SKLEARN = "scikit-learn==1.5.2"
MLFLOW_VERSION = "3.18.0"


# Component A: Load and preprocess data
@dsl.component(base_image=BASE, packages_to_install=[SKLEARN, "pandas==2.2.3"])
def load_data(train_data: Output[Dataset], test_data: Output[Dataset]):
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    df = load_iris(as_frame=True).frame.dropna().drop_duplicates()

    train, test = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
        stratify=df["target"]
    )

    train.to_csv(train_data.path, index=False)
    test.to_csv(test_data.path, index=False)


# Component B: Train model
@dsl.component(
    base_image=BASE,
    packages_to_install=[SKLEARN, "pandas==2.2.3", "joblib"]
)
def train(
    train_data: Input[Dataset],
    model_out: Output[Model],
    n_estimators: int = 100
):
    import joblib
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier

    df = pd.read_csv(train_data.path)
    X, y = df.drop(columns="target"), df["target"]

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        random_state=42
    ).fit(X, y)

    joblib.dump(clf, model_out.path)


# Component C: Evaluate model
@dsl.component(
    base_image=BASE,
    packages_to_install=[SKLEARN, "pandas==2.2.3", "joblib"]
)
def evaluate(
    model_in: Input[Model],
    test_data: Input[Dataset],
    metrics: Output[Metrics]
) -> float:
    import joblib
    import pandas as pd
    from sklearn.metrics import accuracy_score

    model = joblib.load(model_in.path)
    df = pd.read_csv(test_data.path)

    acc = float(
        accuracy_score(
            df["target"],
            model.predict(df.drop(columns="target"))
        )
    )

    metrics.log_metric("accuracy", acc)
    return acc


# Component D: Register model in MLflow
@dsl.component(
    base_image=BASE,
    packages_to_install=[
        f"mlflow=={MLFLOW_VERSION}",
        SKLEARN,
        "pandas==2.2.3",
        "joblib"
    ]
)
def register_model(
    model_in: Input[Model],
    accuracy: float,
    tracking_uri: str,
    model_name: str
):
    import joblib
    import mlflow
    import mlflow.sklearn
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("iris")

    model = joblib.load(model_in.path)

    with mlflow.start_run():
        mlflow.log_metric("accuracy", accuracy)

        mlflow.sklearn.log_model(
            model,
            name="model",
            registered_model_name=model_name,
            skops_trusted_types=["sklearn.tree._tree.Tree"]
        )

    client = MlflowClient()

    versions = client.search_model_versions(
        f"name='{model_name}'"
    )

    v = str(max(int(x.version) for x in versions))

    try:
        client.transition_model_version_stage(
            model_name, v, "Staging"
        )
        client.transition_model_version_stage(
            model_name, v, "Production"
        )

        print(f"Version {v} moved to Production (stage)")

    except Exception as e:
        print("Stage transition unavailable; assigning registry aliases:", e)

    # MLflow stages are legacy; serving consumes the stable production alias.
    client.set_registered_model_alias(model_name, "staging", v)
    client.set_registered_model_alias(model_name, "production", v)
    print(f"Aliases staging and production now point to version {v}")


# Complete Pipeline
@dsl.pipeline(
    name="iris-pipeline",
    description="Load Data -> Train -> Evaluate -> Register Model"
)
def iris_pipeline(
    tracking_uri: str = "http://mlflow.mlops.svc.cluster.local:5000",
    model_name: str = "iris-model",
    n_estimators: int = 100
):
    data_task = load_data()

    train_task = train(
        train_data=data_task.outputs["train_data"],
        n_estimators=n_estimators
    )

    evaluate_task = evaluate(
        model_in=train_task.outputs["model_out"],
        test_data=data_task.outputs["test_data"]
    )

    register_model(
        model_in=train_task.outputs["model_out"],
       accuracy=evaluate_task.outputs["Output"],
        tracking_uri=tracking_uri,
        model_name=model_name
    )


# Compile Pipeline
if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=iris_pipeline,
        package_path="pipeline/pipeline.yaml"
    )
