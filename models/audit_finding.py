from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSIGHT = "insight"

    @property
    def priority(self) -> int:
        return {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INSIGHT: 4,
        }[self]

    @property
    def color(self) -> str:
        return {
            Severity.CRITICAL: "#DC2626",
            Severity.HIGH: "#EA580C",
            Severity.MEDIUM: "#CA8A04",
            Severity.LOW: "#2563EB",
            Severity.INSIGHT: "#6B7280",
        }[self]

    @property
    def emoji(self) -> str:
        return {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🔵",
            Severity.INSIGHT: "⚪",
        }[self]


AUDIT_GROUPS = {
    1: "Foundational Audit",
    2: "Query Intelligence",
    3: "Page-Level Deep Analysis",
    4: "CTR & Position Curve Analysis",
    5: "Search Appearance & SERP Features",
    6: "Device & Country Segmentation",
    7: "Indexing & Coverage Diagnostics",
    8: "Core Web Vitals & Experience",
    9: "Trend & Strategic Analysis",
}

TASK_TO_GROUP = {
    **{i: 1 for i in range(1, 7)},
    **{i: 2 for i in range(7, 17)},
    **{i: 3 for i in range(17, 27)},
    **{i: 4 for i in range(27, 32)},
    **{i: 5 for i in range(32, 38)},
    **{i: 6 for i in range(38, 43)},
    **{i: 7 for i in range(43, 48)},
    **{i: 8 for i in range(48, 52)},
    **{i: 9 for i in range(52, 57)},
}

TASK_NAMES = {
    1: "CTR Optimization Opportunities",
    2: "Dead Pages",
    3: "Dying Content",
    4: "Keyword Cannibalization",
    5: "Quick Wins",
    6: "Branded Keyword Performance",
    7: "Long-Tail Query Cluster Gap Analysis",
    8: "Zero-Click Query Identification",
    9: "Search Intent Drift Detection",
    10: "Question-Format Query Mining",
    11: "High-Impression, Top-Position, Low-CTR Anomaly",
    12: "Navigational Query Misrouting Detection",
    13: "Broad Query to Long-Tail Conversion Opportunity",
    14: "High-CTR, Low-Impression Query Expansion",
    15: "Seasonality Pattern Mapping",
    16: "Spam Query Contamination Check",
    17: "Impression-to-Click Funnel by Page",
    18: "Zero-Impression Indexed Page Audit",
    19: "New Content Ramp-Up Velocity",
    20: "Page Consolidation Candidates",
    21: "Top Pages vs. Top Queries Alignment",
    22: "Parameterized URL Performance Bleed",
    23: "Internal Link Opportunity Mapping",
    24: "Pages Losing Position (Pre-Crash Detection)",
    25: "Rich-Result-Eligible Page Identification",
    26: "Soft 404 / Thin Content Detection",
    27: "Site-Specific Position-to-CTR Curve",
    28: "Title Tag A/B Opportunity Prioritization",
    29: "Mobile vs. Desktop CTR Gap",
    30: "Country-Specific CTR Anomaly",
    31: "Rich Result CTR Lift Quantification",
    32: "Rich Result Type Coverage Audit",
    33: "Sitelink Search Box Monitoring",
    34: "Video Rich Result Gap Analysis",
    35: "AI Overview Query Displacement Tracking",
    36: "AMP vs. Standard Comparison",
    37: "Featured Snippet Ownership Audit",
    38: "Geographic Demand vs. Content Coverage Gap",
    39: "Mobile vs. Desktop Position Delta",
    40: "Hreflang Delivery Validation",
    41: "High-Value Country Crawl Budget Check",
    42: "Tablet Traffic Viability Assessment",
    43: "Index Bloat Ratio Calculation",
    44: "Crawled — Not Indexed Pattern Clustering",
    45: "Sitemap vs. Indexed Pages Reconciliation",
    46: "Google-Overridden Canonical Audit",
    47: "Redirect Chain Click Loss Assessment",
    48: "CWV Regression Detection Post-Deployment",
    49: "Poor CWV URLs Prioritized by Traffic Value",
    50: "INP Bottleneck Page Identification",
    51: "Mobile vs. Desktop CWV Disparity",
    52: "Algorithm Update Impact Segmentation",
    53: "Year-Over-Year Query Demand Shift",
    54: "Post-Migration Performance Reconciliation",
    55: "Content Freshness Decay Rate Benchmarking",
    56: "Query Impression Share Trend for Core Topics",
}


@dataclass
class AuditFinding:
    task_id: int
    severity: Severity
    summary: str
    affected_count: int = 0
    opportunity_value: Optional[str] = None
    data_table: Optional[pd.DataFrame] = None
    recommendations: list[str] = field(default_factory=list)
    chart_config: Optional[dict] = None

    @property
    def task_name(self) -> str:
        return TASK_NAMES.get(self.task_id, f"Task {self.task_id}")

    @property
    def group_id(self) -> int:
        return TASK_TO_GROUP.get(self.task_id, 0)

    @property
    def group_name(self) -> str:
        return AUDIT_GROUPS.get(self.group_id, "Unknown")
