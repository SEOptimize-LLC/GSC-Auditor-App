"""Abstract base class for all GSC audit groups."""

from abc import ABC, abstractmethod
from typing import Callable, Optional

import pandas as pd

from core.data_store import DataStore
from models.audit_finding import AuditFinding, Severity, TASK_NAMES


class BaseGSCAuditor(ABC):
    """Base class providing shared infrastructure for all audit groups.

    Subclasses must define TASK_REGISTRY mapping task IDs to method names,
    and implement each task method returning a list of AuditFinding objects.
    """

    TASK_REGISTRY: dict[int, str] = {}

    def __init__(self, store: DataStore, brand_name: str = ""):
        self.store = store
        self.brand_name = brand_name.lower()

    def run_tasks(self, task_ids: list[int]) -> list[AuditFinding]:
        """Run selected tasks and collect all findings."""
        findings: list[AuditFinding] = []
        for tid in task_ids:
            method_name = self.TASK_REGISTRY.get(tid)
            if method_name is None:
                continue
            method = getattr(self, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if result:
                    findings.extend(result)
            except Exception as e:
                findings.append(
                    AuditFinding(
                        task_id=tid,
                        severity=Severity.INSIGHT,
                        summary=f"Task could not be completed: {e}",
                        recommendations=["Check data availability and try again."],
                    )
                )
        return findings

    def get_required_shapes(self, task_ids: list[int]) -> set[str]:
        """Return the set of data shape keys needed for the given tasks."""
        from models.gsc_data import TASK_SHAPES
        shapes: set[str] = set()
        for tid in task_ids:
            shapes.update(TASK_SHAPES.get(tid, []))
        return shapes

    def get_df(self, shape_name: str) -> pd.DataFrame:
        """Get a DataFrame from the data store."""
        return self.store.get_df(shape_name)

    def create_finding(
        self,
        task_id: int,
        severity: Severity,
        summary: str,
        affected_count: int = 0,
        opportunity_value: Optional[str] = None,
        data_table: Optional[pd.DataFrame] = None,
        recommendations: Optional[list[str]] = None,
        chart_config: Optional[dict] = None,
    ) -> AuditFinding:
        """Helper to create a standardized AuditFinding."""
        return AuditFinding(
            task_id=task_id,
            severity=severity,
            summary=summary,
            affected_count=affected_count,
            opportunity_value=opportunity_value,
            data_table=data_table,
            recommendations=recommendations or [],
            chart_config=chart_config,
        )

    def is_brand_query(self, query: str) -> bool:
        """Check if a query contains the brand name."""
        if not self.brand_name:
            return False
        return self.brand_name in query.lower()

    @staticmethod
    def calculate_expected_ctr(position: float) -> float:
        """Return the expected CTR for a given average position.

        Based on industry benchmarks (2024 Advanced Web Ranking data).
        """
        ctr_curve = {
            1: 0.396, 2: 0.187, 3: 0.112, 4: 0.078, 5: 0.053,
            6: 0.038, 7: 0.028, 8: 0.021, 9: 0.016, 10: 0.013,
            11: 0.010, 12: 0.009, 13: 0.008, 14: 0.007, 15: 0.006,
            16: 0.005, 17: 0.005, 18: 0.004, 19: 0.004, 20: 0.003,
        }
        pos_int = max(1, min(20, round(position)))
        return ctr_curve.get(pos_int, 0.003)
