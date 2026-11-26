"""Create the enhanced Iris CSV, compare models, and save the best model/report."""

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from pipeline.features import (  # noqa: E402
    FEATURE_COLUMNS,
    RAW_FEATURE_COLUMNS,
    TARGET_COLUMN,
    engineer_features,
)


def make_model(estimator):
    # Imputation is fitted within each training fold, preventing test leakage.
    return make_pipeline(SimpleImputer(strategy="median"), estimator)


def evaluate(model, X_test, y_test):
    predicted = model.predict(X_test)
    return {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "precision_macro": float(precision_score(y_test, predicted, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, predicted, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_test, predicted, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_test, predicted, labels=[0, 1, 2]).tolist(),
        "classification_report": classification_report(
            y_test,
            predicted,
            labels=[0, 1, 2],
            target_names=["Iris setosa", "Iris versicolor", "Iris virginica"],
            output_dict=True,
            zero_division=0,
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "iris.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "iris_enhanced.csv")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    args = parser.parse_args()

    original = pd.read_csv(args.input)
    before_shape = list(original.shape)
    for column in RAW_FEATURE_COLUMNS + [TARGET_COLUMN]:
        original[column] = pd.to_numeric(original[column], errors="coerce")
    original = original.dropna(subset=[TARGET_COLUMN]).copy()
    original[TARGET_COLUMN] = original[TARGET_COLUMN].astype(int)

    enhanced = engineer_features(original)
    # Preserve all source rows with a usable label; missing feature values are
    # retained here and imputed only inside models fitted on training data.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    enhanced[FEATURE_COLUMNS + [TARGET_COLUMN]].to_csv(args.output, index=False)

    train_idx, test_idx = train_test_split(
        enhanced.index,
        test_size=0.2,
        random_state=42,
        stratify=enhanced[TARGET_COLUMN],
    )
    y_train = enhanced.loc[train_idx, TARGET_COLUMN]
    y_test = enhanced.loc[test_idx, TARGET_COLUMN]
    old_X = enhanced.loc[:, RAW_FEATURE_COLUMNS]
    new_X = enhanced.loc[:, FEATURE_COLUMNS]

    # Reproduce the existing Random Forest on its original four inputs as the
    # old-model baseline. No saved registered model was available locally.
    baseline = make_model(RandomForestClassifier(n_estimators=100, random_state=42))
    baseline.fit(old_X.loc[train_idx], y_train)
    baseline_metrics = evaluate(baseline, old_X.loc[test_idx], y_test)

    candidates = {
        "random_forest": RandomForestClassifier(n_estimators=100, random_state=42),
        "decision_tree": DecisionTreeClassifier(random_state=42),
    }
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = {}
    for name, estimator in candidates.items():
        cv_scores[name] = cross_val_score(
            make_model(estimator),
            new_X.loc[train_idx],
            y_train,
            scoring="f1_macro",
            cv=folds,
        ).tolist()
    selected_name = max(cv_scores, key=lambda name: sum(cv_scores[name]) / len(cv_scores[name]))
    selected_model = make_model(candidates[selected_name])
    selected_model.fit(new_X.loc[train_idx], y_train)
    selected_metrics = evaluate(selected_model, new_X.loc[test_idx], y_test)

    args.model_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.model_dir / "iris_best_model.joblib"
    joblib.dump(selected_model, model_path)
    report = {
        "dataset": {
            "source": str(args.input.relative_to(ROOT) if args.input.is_relative_to(ROOT) else args.input),
            "enhanced_csv": str(args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output),
            "shape_before": before_shape,
            "shape_after": list(enhanced[FEATURE_COLUMNS + [TARGET_COLUMN]].shape),
            "feature_columns": FEATURE_COLUMNS,
            "target_column": TARGET_COLUMN,
            "missing_values_after_enhancement": int(enhanced[FEATURE_COLUMNS].isna().sum().sum()),
        },
        "split": {"train_rows": len(train_idx), "test_rows": len(test_idx), "stratified": True, "random_state": 42},
        "old_four_feature_random_forest_baseline": baseline_metrics,
        "candidate_cv_macro_f1": {
            name: {"fold_scores": scores, "mean": sum(scores) / len(scores)}
            for name, scores in cv_scores.items()
        },
        "selected_algorithm": selected_name,
        "new_ten_feature_model": selected_metrics,
        "model_file": str(model_path.relative_to(ROOT) if model_path.is_relative_to(ROOT) else model_path),
    }
    report_path = args.model_dir / "training_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Dataset: {before_shape} -> {report['dataset']['shape_after']} (features + target)")
    print(f"Enhanced CSV: {args.output}")
    print(f"Baseline RF (4 features) accuracy: {baseline_metrics['accuracy']:.4f}")
    print(f"CV macro F1: {report['candidate_cv_macro_f1']}")
    print(f"Selected: {selected_name}")
    print("New model metrics:", {key: selected_metrics[key] for key in ("accuracy", "precision_macro", "recall_macro", "f1_macro")})
    print("Confusion matrix [0, 1, 2]:\n", selected_metrics["confusion_matrix"])
    print("Classification report:\n", json.dumps(selected_metrics["classification_report"], indent=2))
    print(f"Saved model: {model_path}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
