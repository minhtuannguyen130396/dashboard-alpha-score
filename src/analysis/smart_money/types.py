"""Core dataclasses for the smart money module.

The bucket attribute on FlowPrimitive is REQUIRED and used by the composite
aggregator to split primitives into two independent channels (setup vs.
trigger). Scoring engines read setup_composite / trigger_composite directly;
the top-level composite / confidence fields are UI-only.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Literal


Bucket = Literal["setup", "trigger"]


@dataclass
class FlowPrimitive:
    name: str
    bucket: Bucket
    value: float                       # [-1..+1]
    confidence: float                  # [0..1]
    components: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


@dataclass
class SmartMoneySignal:
    # Bucket outputs — scoring engine reads from here
    setup_composite: float = 0.0
    setup_confidence: float = 0.0
    trigger_composite: float = 0.0
    trigger_confidence: float = 0.0

    # UI-only merged composite (NOT consumed by scoring engines)
    composite: float = 0.0
    confidence: float = 0.0

    label: str = "neutral"             # strong_bull|bull|neutral|bear|strong_bear|toxic
    is_toxic: bool = False
    trend: str = "stable"              # strengthening|stable|weakening
    primitives: Dict[str, FlowPrimitive] = field(default_factory=dict)
    narrative: str = ""
