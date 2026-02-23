"""Builds prompts for AI analysis from audit findings."""

from models.audit_finding import AuditFinding, AUDIT_GROUPS
from models.audit_result import AuditResult


MAX_TABLE_ROWS = 15
MAX_FINDINGS_PER_GROUP = 20


def serialize_finding(finding: AuditFinding) -> str:
    """Convert a single AuditFinding into a text representation for AI analysis."""
    lines = [
        f"### Task {finding.task_id}: {finding.task_name}",
        f"**Severity:** {finding.severity.value.upper()}",
        f"**Summary:** {finding.summary}",
    ]

    if finding.affected_count > 0:
        lines.append(f"**Affected Items:** {finding.affected_count:,}")

    if finding.opportunity_value:
        lines.append(f"**Opportunity:** {finding.opportunity_value}")

    if finding.recommendations:
        lines.append("**Recommendations:**")
        for rec in finding.recommendations:
            lines.append(f"- {rec}")

    if finding.data_table is not None and not finding.data_table.empty:
        table_preview = finding.data_table.head(MAX_TABLE_ROWS)
        lines.append("\n**Data Sample:**")
        lines.append(table_preview.to_markdown(index=False))

    return "\n".join(lines)


def build_group_prompt(group_id: int, findings: list[AuditFinding]) -> tuple[str, str]:
    """Build system prompt and user content for a group analysis.

    Returns (system_prompt, user_content).
    """
    group_name = AUDIT_GROUPS.get(group_id, f"Group {group_id}")

    system_prompt = f"""You are an expert SEO analyst specializing in {group_name.lower()}.

You are analyzing Google Search Console audit findings for a website. Your task is to:

1. Provide a concise narrative analysis of the findings (300-500 words)
2. Identify the most critical issues and their business impact
3. Prioritize the findings by urgency and potential traffic impact
4. Suggest a specific action sequence for addressing the issues

Write in a professional but accessible tone. Focus on actionable insights, not just restating the data.
Use specific numbers from the findings to support your analysis.
Do not use excessive formatting — keep it clean and scannable."""

    findings_text_parts = [
        f"# {group_name} — Audit Findings\n",
        f"**Total Findings:** {len(findings)}\n",
    ]

    for finding in findings[:MAX_FINDINGS_PER_GROUP]:
        findings_text_parts.append(serialize_finding(finding))
        findings_text_parts.append("")

    user_content = "\n".join(findings_text_parts)
    return system_prompt, user_content


def build_executive_summary_prompt(
    result: AuditResult,
    group_analyses: dict[int, str],
) -> tuple[str, str]:
    """Build system prompt and user content for the executive summary.

    Returns (system_prompt, user_content).
    """
    system_prompt = """You are a senior SEO strategist preparing an executive summary and content optimization plan
for a comprehensive Google Search Console audit.

Your output must include:

1. **Executive Summary** (2-3 paragraphs): Overall site health assessment, key strengths, and critical weaknesses.

2. **Top 5 Critical Actions**: The five most impactful issues that need immediate attention, with specific steps.

3. **Content Optimization Plan**: A prioritized roadmap of content actions organized by:
   - **Immediate (This Week)**: Quick wins and critical fixes
   - **Short-term (This Month)**: Content refreshes and optimization
   - **Medium-term (This Quarter)**: Strategic content development
   - **Long-term (Ongoing)**: Monitoring and maintenance

4. **Priority Matrix**: Categorize all key findings into:
   - High Impact / Low Effort (Do First)
   - High Impact / High Effort (Plan For)
   - Low Impact / Low Effort (Quick Wins)
   - Low Impact / High Effort (Deprioritize)

Write in a strategic, business-oriented tone. Be specific with numbers and recommendations.
This report will be read by SEO professionals and marketing stakeholders."""

    content_parts = [
        f"# GSC Audit Results — {result.property_url}\n",
        f"**Audit Date:** {result.audit_timestamp[:10]}",
        f"**Analysis Period:** {result.start_date} to {result.end_date}",
        f"**Tasks Executed:** {len(result.tasks_executed)}",
        f"**Total Findings:** {result.total_findings}",
        f"**Health Score:** {result.health_score}/100 (Grade: {result.health_grade})\n",
        "## Severity Breakdown",
    ]

    for sev, count in result.severity_counts.items():
        content_parts.append(f"- **{sev.title()}:** {count}")

    content_parts.append("\n## Group Analyses\n")

    for group_id in sorted(group_analyses.keys()):
        group_name = AUDIT_GROUPS.get(group_id, f"Group {group_id}")
        content_parts.append(f"### {group_name}")
        content_parts.append(group_analyses[group_id])
        content_parts.append("")

    user_content = "\n".join(content_parts)
    return system_prompt, user_content
