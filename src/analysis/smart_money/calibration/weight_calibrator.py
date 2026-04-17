"""Weight calibration via logistic regression (Phase 5).

Train offline on historical signals; output a JSON weights file that the
composite can load. Composite logic itself stays simple — calibration only
swaps the static weight dict for a learned one. ML stays out of runtime.

Key invariants:
- Negative coefficients are dropped (signal pointing the wrong way → kill)
- Weights are L1-normalized so the bucket aggregator behaves identically
- Walk-forward only — caller is responsible for not training on future data
"""
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date as _date
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple


# =============================================================================
# Lightweight logistic regression (no sklearn dep at runtime)
# =============================================================================

def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _fit_logistic(
    X: List[List[float]],
    y: List[int],
    l2: float = 1.0,
    lr: float = 0.1,
    epochs: int = 200,
) -> List[float]:
    """L2-regularized logistic regression via batch gradient descent.

    Pure-Python so unit tests don't pull in sklearn. Sufficient for the
    calibration use case (≤ 50 features, ≤ 100k rows).
    """
    if not X:
        return []
    n_features = len(X[0])
    weights = [0.0] * n_features
    n = len(X)
    inv_n = 1.0 / n

    for _ in range(epochs):
        gradients = [0.0] * n_features
        for xi, yi in zip(X, y):
            z = sum(w * x for w, x in zip(weights, xi))
            pred = _sigmoid(z)
            err = pred - yi
            for j in range(n_features):
                gradients[j] += err * xi[j]
        for j in range(n_features):
            grad = gradients[j] * inv_n + l2 * weights[j]
            weights[j] -= lr * grad
    return weights


# =============================================================================
# Public dataclasses
# =============================================================================

@dataclass
class CalibratedWeights:
    """Calibrated weight bundle.

    ``weights_matrix`` keys are stringified ``(regime, symbol_class)`` tuples.
    Use ``get_weights(regime, symbol_class)`` to look up with the documented
    fallback ladder.
    """
    default_weights: Dict[str, float] = field(default_factory=dict)
    weights_by_regime: Dict[str, Dict[str, float]] = field(default_factory=dict)
    weights_by_symbol: Dict[str, Dict[str, float]] = field(default_factory=dict)
    weights_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get_weights(
        self, regime: Optional[str] = None, symbol_class: Optional[str] = None,
    ) -> Dict[str, float]:
        if regime and symbol_class:
            key = f"{regime}::{symbol_class}"
            if key in self.weights_matrix:
                return self.weights_matrix[key]
        if symbol_class and symbol_class in self.weights_by_symbol:
            return self.weights_by_symbol[symbol_class]
        if regime and regime in self.weights_by_regime:
            return self.weights_by_regime[regime]
        return self.default_weights

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CalibratedWeights":
        return cls(
            default_weights=d.get("default_weights", {}),
            weights_by_regime=d.get("weights_by_regime", {}),
            weights_by_symbol=d.get("weights_by_symbol", {}),
            weights_matrix=d.get("weights_matrix", {}),
        )


@dataclass
class ExpectedReturnBins:
    """Bin index → mean forward return for UI display."""
    bin_edges: List[float] = field(default_factory=list)
    bin_means: List[float] = field(default_factory=list)

    def lookup(self, composite: float) -> Optional[float]:
        if not self.bin_edges or not self.bin_means:
            return None
        for i in range(len(self.bin_edges) - 1):
            if self.bin_edges[i] <= composite < self.bin_edges[i + 1]:
                return self.bin_means[i]
        if composite >= self.bin_edges[-1]:
            return self.bin_means[-1]
        return self.bin_means[0]


# =============================================================================
# Calibrator
# =============================================================================

@dataclass
class TrainingSignal:
    """One row of historical training data."""
    features: Dict[str, float]
    forward_return_5d: float
    regime: Optional[str] = None        # bull_trend|bear_trend|sideway
    symbol_class: Optional[str] = None  # large_cap|mid_cap|small_cap
    date: Optional[_date] = None
    symbol: Optional[str] = None


class WeightCalibrator:
    """Fits logistic regression and converts coefficients to bucket weights."""

    MIN_SIGNALS_PER_BUCKET = 500
    HIT_THRESHOLD = 0.02   # forward 5d return ≥ 2% counts as a "hit"

    def __init__(self, l2: float = 1.0, hit_threshold: Optional[float] = None):
        self.l2 = l2
        if hit_threshold is not None:
            self.HIT_THRESHOLD = hit_threshold

    def fit(self, signals: List[TrainingSignal]) -> Dict[str, float]:
        """Fit one logistic model on ``signals`` → return normalized weights."""
        if not signals:
            return {}

        feature_names = sorted(signals[0].features.keys())
        X: List[List[float]] = []
        y: List[int] = []
        for s in signals:
            X.append([float(s.features.get(k, 0.0)) for k in feature_names])
            y.append(1 if s.forward_return_5d >= self.HIT_THRESHOLD else 0)

        coefs = _fit_logistic(X, y, l2=self.l2)

        positive = {k: max(0.0, v) for k, v in zip(feature_names, coefs)}
        total = sum(positive.values())
        if total <= 0:
            # Degenerate: no feature points the right way → uniform weights
            return {k: 1.0 / len(feature_names) for k in feature_names}
        return {k: v / total for k, v in positive.items()}

    def fit_matrix(
        self,
        signals: List[TrainingSignal],
    ) -> CalibratedWeights:
        """Fit default + per-regime + per-symbol-class + (regime × class) weights."""
        out = CalibratedWeights()
        out.default_weights = self.fit(signals)

        # Per regime
        regime_buckets: Dict[str, List[TrainingSignal]] = {}
        for s in signals:
            if s.regime:
                regime_buckets.setdefault(s.regime, []).append(s)
        for regime, bucket in regime_buckets.items():
            if len(bucket) >= self.MIN_SIGNALS_PER_BUCKET:
                out.weights_by_regime[regime] = self.fit(bucket)

        # Per symbol class
        sym_buckets: Dict[str, List[TrainingSignal]] = {}
        for s in signals:
            if s.symbol_class:
                sym_buckets.setdefault(s.symbol_class, []).append(s)
        for cls, bucket in sym_buckets.items():
            if len(bucket) >= self.MIN_SIGNALS_PER_BUCKET:
                out.weights_by_symbol[cls] = self.fit(bucket)

        # Matrix (regime × symbol_class)
        matrix_buckets: Dict[str, List[TrainingSignal]] = {}
        for s in signals:
            if s.regime and s.symbol_class:
                key = f"{s.regime}::{s.symbol_class}"
                matrix_buckets.setdefault(key, []).append(s)
        for key, bucket in matrix_buckets.items():
            if len(bucket) >= self.MIN_SIGNALS_PER_BUCKET:
                out.weights_matrix[key] = self.fit(bucket)

        return out

    def compute_expected_return_bins(
        self, signals: List[TrainingSignal], n_bins: int = 20,
        composite_extractor=None,
    ) -> ExpectedReturnBins:
        """Bin signals by composite score → mean forward return per bin.

        ``composite_extractor`` is a callable ``signal → composite ∈ [-1..+1]``;
        defaults to ``signal.features.get('composite', 0)``.
        """
        if not signals:
            return ExpectedReturnBins()
        if composite_extractor is None:
            composite_extractor = lambda s: s.features.get("composite", 0.0)

        edges = [-1.0 + 2.0 * i / n_bins for i in range(n_bins + 1)]
        bin_returns: List[List[float]] = [[] for _ in range(n_bins)]
        for s in signals:
            c = composite_extractor(s)
            idx = min(n_bins - 1, max(0, int((c + 1.0) / 2.0 * n_bins)))
            bin_returns[idx].append(s.forward_return_5d)

        means = [
            (sum(b) / len(b)) if len(b) >= 30 else 0.0
            for b in bin_returns
        ]
        return ExpectedReturnBins(bin_edges=edges, bin_means=means)


# =============================================================================
# Persistence
# =============================================================================

def save_calibrated_weights(weights: CalibratedWeights, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(weights.to_dict(), f, indent=2)


def load_calibrated_weights(path: str) -> CalibratedWeights:
    with open(path, "r", encoding="utf-8") as f:
        return CalibratedWeights.from_dict(json.load(f))


def save_expected_return_bins(bins: ExpectedReturnBins, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(bins), f, indent=2)


# =============================================================================
# Drift detection
# =============================================================================

@dataclass
class DriftReport:
    recent_pf: float
    baseline_pf: float
    pf_change_pct: float
    needs_recalibration: bool
    reason: str


class DriftMonitor:
    """Detects when calibrated weights stop working.

    Compares profit factor of the last ``recent_window`` trades against the
    prior ``baseline_window``. PF drop ≥ 20% → flag for recalibration.
    """

    def __init__(
        self, recent_window: int = 90, baseline_window: int = 90,
        pf_drop_threshold: float = 0.2,
    ):
        self.recent_window = recent_window
        self.baseline_window = baseline_window
        self.pf_drop_threshold = pf_drop_threshold

    @staticmethod
    def _profit_factor(returns: List[float]) -> float:
        gains = sum(r for r in returns if r > 0)
        losses = -sum(r for r in returns if r < 0)
        if losses <= 0:
            return float("inf") if gains > 0 else 0.0
        return gains / losses

    def check(self, returns_chronological: List[float]) -> DriftReport:
        if len(returns_chronological) < (self.recent_window + self.baseline_window):
            return DriftReport(
                recent_pf=0.0, baseline_pf=0.0, pf_change_pct=0.0,
                needs_recalibration=False,
                reason="not enough history",
            )
        recent = returns_chronological[-self.recent_window:]
        baseline = returns_chronological[
            -(self.recent_window + self.baseline_window): -self.recent_window
        ]
        rpf = self._profit_factor(recent)
        bpf = self._profit_factor(baseline)
        if not math.isfinite(rpf) or not math.isfinite(bpf) or bpf <= 0:
            return DriftReport(
                recent_pf=rpf, baseline_pf=bpf, pf_change_pct=0.0,
                needs_recalibration=False, reason="degenerate PF",
            )
        change = (rpf - bpf) / bpf
        needs = change < -self.pf_drop_threshold
        return DriftReport(
            recent_pf=rpf,
            baseline_pf=bpf,
            pf_change_pct=change,
            needs_recalibration=needs,
            reason="PF drop exceeds threshold" if needs else "stable",
        )
