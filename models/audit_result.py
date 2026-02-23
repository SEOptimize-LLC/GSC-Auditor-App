from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from models.audit_finding import AuditFinding, Severity, AUDIT_GROUPS


@dataclass
class AuditResult:
    property_url: str
    start_date: str
    end_date: str
    tasks_executed: list[int] = field(default_factory=list)
    findings: list[AuditFinding] = field(default_factory=list)
    ai_group_analyses: dict[int, str] = field(default_factory=dict)
    ai_executive_summary: Optional[str] = None
    ai_content_plan: Optional[str] = None
    audit_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_finding(self, finding: AuditFinding) -> None:
        self.findings.append(finding)

    def add_findings(self, findings: list[AuditFinding]) -> None:
        self.findings.extend(findings)

    @property
    def findings_by_group(self) -> dict[int, list[AuditFinding]]:
        grouped: dict[int, list[AuditFinding]] = {}
        for f in self.findings:
            grouped.setdefault(f.group_id, []).append(f)
        return grouped

    @property
    def findings_by_severity(self) -> dict[Severity, list[AuditFinding]]:
        by_sev: dict[Severity, list[AuditFinding]] = {}
        for f in self.findings:
            by_sev.setdefault(f.severity, []).append(f)
        return by_sev

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts

    @property
    def health_score(self) -> int:
        if not self.findings:
            return 100
        penalty = 0
        weights = {
            Severity.CRITICAL: 15,
            Severity.HIGH: 8,
            Severity.MEDIUM: 3,
            Severity.LOW: 1,
            Severity.INSIGHT: 0,
        }
        for f in self.findings:
            penalty += weights.get(f.severity, 0)
        score = max(0, 100 - penalty)
        return score

    @property
    def health_grade(self) -> str:
        s = self.health_score
        if s >= 90:
            return "A"
        if s >= 80:
            return "B"
        if s >= 70:
            return "C"
        if s >= 60:
            return "D"
        return "F"

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def critical_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == Severity.CRITICAL]

    @property
    def top_findings(self) -> list[AuditFinding]:
        return sorted(self.findings, key=lambda f: f.severity.priority)[:10]

    @property
    def groups_with_findings(self) -> list[int]:
        return sorted(set(f.group_id for f in self.findings))
