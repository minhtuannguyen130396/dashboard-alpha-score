"""Smart money module — institutional flow detection.

Public API:

    from src.analysis.smart_money import (
        compute_smart_money,
        SmartMoneySignal,
        FlowPrimitive,
        SmartMoneyConfig,
        DEFAULT_SMART_MONEY_CONFIG,
    )
"""
from src.analysis.smart_money.composite import (
    compute_smart_money,
    compute_smart_money_mtf,
)
from src.analysis.smart_money.config import (
    DEFAULT_SMART_MONEY_CONFIG,
    SmartMoneyConfig,
)
from src.analysis.smart_money.types import FlowPrimitive, SmartMoneySignal

__all__ = [
    "compute_smart_money",
    "compute_smart_money_mtf",
    "SmartMoneySignal",
    "FlowPrimitive",
    "SmartMoneyConfig",
    "DEFAULT_SMART_MONEY_CONFIG",
]
