"""Auditor registry and task routing."""

from typing import TYPE_CHECKING

from core.data_store import DataStore
from models.audit_finding import TASK_TO_GROUP

if TYPE_CHECKING:
    from auditors.base_auditor import BaseGSCAuditor


def get_auditors_for_tasks(
    task_ids: list[int],
    store: DataStore,
    brand_name: str = "",
) -> list[tuple["BaseGSCAuditor", list[int]]]:
    """Return a list of (auditor_instance, task_ids) tuples for the given tasks.

    Groups task IDs by their audit group and instantiates the appropriate
    auditor class for each group.
    """
    from auditors.foundational import FoundationalAuditor
    from auditors.query_intelligence import QueryIntelligenceAuditor
    from auditors.page_analysis import PageAnalysisAuditor
    from auditors.ctr_position import CTRPositionAuditor
    from auditors.search_appearance import SearchAppearanceAuditor
    from auditors.device_country import DeviceCountryAuditor
    from auditors.indexing_coverage import IndexingCoverageAuditor
    from auditors.core_web_vitals import CoreWebVitalsAuditor
    from auditors.trend_strategic import TrendStrategicAuditor

    GROUP_TO_AUDITOR = {
        1: FoundationalAuditor,
        2: QueryIntelligenceAuditor,
        3: PageAnalysisAuditor,
        4: CTRPositionAuditor,
        5: SearchAppearanceAuditor,
        6: DeviceCountryAuditor,
        7: IndexingCoverageAuditor,
        8: CoreWebVitalsAuditor,
        9: TrendStrategicAuditor,
    }

    groups: dict[int, list[int]] = {}
    for tid in task_ids:
        gid = TASK_TO_GROUP.get(tid)
        if gid is not None:
            groups.setdefault(gid, []).append(tid)

    auditors = []
    for gid in sorted(groups.keys()):
        auditor_cls = GROUP_TO_AUDITOR.get(gid)
        if auditor_cls:
            auditor = auditor_cls(store=store, brand_name=brand_name)
            auditors.append((auditor, groups[gid]))

    return auditors
