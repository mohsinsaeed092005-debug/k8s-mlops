"""Shared Iris feature definitions and deterministic feature engineering."""

import numpy as np
import pandas as pd


RAW_FEATURE_COLUMNS = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]
ENGINEERED_FEATURE_COLUMNS = [
    "sepal area (cm^2)",
    "petal area (cm^2)",
    "sepal ratio",
    "petal ratio",
    "total length (cm)",
    "total width (cm)",
]
FEATURE_COLUMNS = RAW_FEATURE_COLUMNS + ENGINEERED_FEATURE_COLUMNS
TARGET_COLUMN = "target"
SPECIES_NAMES = ["Iris setosa", "Iris versicolor", "Iris virginica"]


def engineer_features(data: pd.DataFrame) -> pd.DataFrame:
    """Add six derived measurements; a zero denominator produces ratio 0."""
    result = data.copy()
    for column in RAW_FEATURE_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    sepal_length = result[RAW_FEATURE_COLUMNS[0]]
    sepal_width = result[RAW_FEATURE_COLUMNS[1]]
    petal_length = result[RAW_FEATURE_COLUMNS[2]]
    petal_width = result[RAW_FEATURE_COLUMNS[3]]

    result[ENGINEERED_FEATURE_COLUMNS[0]] = sepal_length * sepal_width
    result[ENGINEERED_FEATURE_COLUMNS[1]] = petal_length * petal_width
    result[ENGINEERED_FEATURE_COLUMNS[2]] = np.divide(
        sepal_length.to_numpy(dtype=float),
        sepal_width.to_numpy(dtype=float),
        out=np.zeros(len(result), dtype=float),
        where=sepal_width.to_numpy(dtype=float) != 0,
    )
    result[ENGINEERED_FEATURE_COLUMNS[3]] = np.divide(
        petal_length.to_numpy(dtype=float),
        petal_width.to_numpy(dtype=float),
        out=np.zeros(len(result), dtype=float),
        where=petal_width.to_numpy(dtype=float) != 0,
    )
    result[ENGINEERED_FEATURE_COLUMNS[4]] = sepal_length + petal_length
    result[ENGINEERED_FEATURE_COLUMNS[5]] = sepal_width + petal_width
    return result
