"""Phase 5 — adaptive weight calibration.

Public surface:

    from src.analysis.smart_money.calibration import (
        WeightCalibrator,
        CalibratedWeights,
        ExpectedReturnBins,
        DriftMonitor,
        load_calibrated_weights,
    )
"""
from src.analysis.smart_money.calibration.weight_calibrator import (
    CalibratedWeights,
    DriftMonitor,
    ExpectedReturnBins,
    WeightCalibrator,
    load_calibrated_weights,
)

__all__ = [
    "WeightCalibrator",
    "CalibratedWeights",
    "ExpectedReturnBins",
    "DriftMonitor",
    "load_calibrated_weights",
]
