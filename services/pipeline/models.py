from __future__ import annotations

from dataclasses import dataclass
from math import exp

from services.pipeline.features import FEATURE_NAMES, FeatureRow


TREND_MODEL_LOGIC_VERSION = "1.0"
PRICE_MODEL_LOGIC_VERSION = "1.0"
DEFAULT_PRICE_REGRESSOR_EPOCHS = 600
DEFAULT_PRICE_REGRESSOR_LEARNING_RATE = 0.05


@dataclass(frozen=True)
class Standardization:
    means: dict[str, float]
    scales: dict[str, float]


@dataclass(frozen=True)
class TrendPrediction:
    label: int
    confidence: float
    score: float


@dataclass(frozen=True)
class RegressionPrediction:
    predicted_return: float
    target_price: float


@dataclass(frozen=True)
class TrendModel:
    standardization: Standardization
    positive_centroid: dict[str, float] | None
    negative_centroid: dict[str, float] | None
    single_label: int | None = None

    def predict(self, row: FeatureRow) -> TrendPrediction:
        if self.single_label is not None:
            score = 1.0 if self.single_label == 1 else -1.0
            confidence = 1 / (1 + exp(-score))
            return TrendPrediction(label=self.single_label, confidence=confidence, score=score)

        if self.positive_centroid is None or self.negative_centroid is None:
            raise ValueError("TrendModel centroids must be defined for multi-class prediction")

        features = _normalize(row.feature_values, self.standardization)
        positive_distance = _distance(features, self.positive_centroid)
        negative_distance = _distance(features, self.negative_centroid)
        score = negative_distance - positive_distance
        confidence = 1 / (1 + exp(-score))
        label = 1 if positive_distance <= negative_distance else 0
        return TrendPrediction(label=label, confidence=confidence, score=score)


@dataclass(frozen=True)
class PriceRegressor:
    standardization: Standardization
    weights: dict[str, float]
    bias: float

    def predict(self, row: FeatureRow) -> RegressionPrediction:
        features = _normalize(row.feature_values, self.standardization)
        predicted_return = self.bias + sum(
            self.weights[name] * features[name]
            for name in FEATURE_NAMES
        )
        target_price = row.current_price * (1 + predicted_return)
        return RegressionPrediction(predicted_return=predicted_return, target_price=target_price)



def fit_trend_model(rows: list[FeatureRow]) -> TrendModel:
    standardization = _fit_standardization(rows)
    positive_rows = [row for row in rows if row.trend_label == 1]
    negative_rows = [row for row in rows if row.trend_label == 0]
    if not positive_rows or not negative_rows:
        single_label = 1 if positive_rows else 0
        return TrendModel(
            standardization=standardization,
            positive_centroid=None,
            negative_centroid=None,
            single_label=single_label,
        )

    positive_centroid = _centroid(positive_rows, standardization)
    negative_centroid = _centroid(negative_rows, standardization)
    return TrendModel(
        standardization=standardization,
        positive_centroid=positive_centroid,
        negative_centroid=negative_centroid,
    )



def fit_price_regressor(
    rows: list[FeatureRow],
    epochs: int = DEFAULT_PRICE_REGRESSOR_EPOCHS,
    learning_rate: float = DEFAULT_PRICE_REGRESSOR_LEARNING_RATE,
) -> PriceRegressor:
    standardization = _fit_standardization(rows)
    weights = {name: 0.0 for name in FEATURE_NAMES}
    bias = sum(row.future_return for row in rows) / len(rows)

    for _ in range(epochs):
        weight_gradients = {name: 0.0 for name in FEATURE_NAMES}
        bias_gradient = 0.0
        for row in rows:
            normalized = _normalize(row.feature_values, standardization)
            prediction = bias + sum(weights[name] * normalized[name] for name in FEATURE_NAMES)
            error = prediction - row.future_return
            bias_gradient += error
            for name in FEATURE_NAMES:
                weight_gradients[name] += error * normalized[name]
        row_count = float(len(rows))
        bias -= learning_rate * (bias_gradient / row_count)
        for name in FEATURE_NAMES:
            weights[name] -= learning_rate * (weight_gradients[name] / row_count)

    return PriceRegressor(standardization=standardization, weights=weights, bias=bias)



def _fit_standardization(rows: list[FeatureRow]) -> Standardization:
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for name in FEATURE_NAMES:
        values = [row.feature_values[name] for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = variance ** 0.5
        means[name] = mean
        scales[name] = scale if scale > 0 else 1.0
    return Standardization(means=means, scales=scales)



def _normalize(values: dict[str, float], standardization: Standardization) -> dict[str, float]:
    return {
        name: (values[name] - standardization.means[name]) / standardization.scales[name]
        for name in FEATURE_NAMES
    }



def _centroid(rows: list[FeatureRow], standardization: Standardization) -> dict[str, float]:
    centroid = {name: 0.0 for name in FEATURE_NAMES}
    for row in rows:
        normalized = _normalize(row.feature_values, standardization)
        for name in FEATURE_NAMES:
            centroid[name] += normalized[name]
    row_count = float(len(rows))
    return {name: centroid[name] / row_count for name in FEATURE_NAMES}



def _distance(left: dict[str, float], right: dict[str, float]) -> float:
    return sum((left[name] - right[name]) ** 2 for name in FEATURE_NAMES) ** 0.5
