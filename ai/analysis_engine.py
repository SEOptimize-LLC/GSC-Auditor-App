"""Orchestrates AI analysis across audit groups."""

import logging
from typing import Callable, Optional

from ai.openrouter_client import OpenRouterClient
from ai.prompt_builder import build_group_prompt, build_executive_summary_prompt
from models.audit_finding import AUDIT_GROUPS
from models.audit_result import AuditResult

logger = logging.getLogger(__name__)


class AnalysisEngine:
    """Coordinates AI analysis of audit results."""

    def __init__(self, api_key: str = ""):
        self.client = OpenRouterClient(api_key=api_key)

    def analyze_result(
        self,
        result: AuditResult,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        """Run full AI analysis on audit results.

        Modifies the result in-place, adding:
        - ai_group_analyses: dict of group_id -> narrative
        - ai_executive_summary: executive summary text
        - ai_content_plan: content optimization plan
        """
        groups_with_findings = result.findings_by_group
        total_steps = len(groups_with_findings) + 1
        current_step = 0

        # Analyze each group
        for group_id, findings in sorted(groups_with_findings.items()):
            group_name = AUDIT_GROUPS.get(group_id, f"Group {group_id}")
            try:
                system_prompt, user_content = build_group_prompt(group_id, findings)
                analysis = self.client.analyze_group(system_prompt, user_content)
                result.ai_group_analyses[group_id] = analysis
                logger.info(f"AI analysis complete for Group {group_id}: {group_name}")
            except Exception as e:
                logger.error(f"AI analysis failed for Group {group_id}: {e}")
                result.ai_group_analyses[group_id] = (
                    f"AI analysis unavailable for this group: {e}"
                )

            current_step += 1
            if progress_callback:
                progress_callback(
                    current_step / total_steps,
                    f"Analyzed {group_name}",
                )

        # Generate executive summary
        try:
            system_prompt, user_content = build_executive_summary_prompt(
                result, result.ai_group_analyses
            )
            summary = self.client.generate_executive_summary(
                system_prompt, user_content
            )

            sections = summary.split("## Content Optimization Plan", 1)
            if len(sections) == 2:
                result.ai_executive_summary = sections[0].strip()
                result.ai_content_plan = "## Content Optimization Plan" + sections[1].strip()
            else:
                sections = summary.split("# Content Optimization Plan", 1)
                if len(sections) == 2:
                    result.ai_executive_summary = sections[0].strip()
                    result.ai_content_plan = "# Content Optimization Plan" + sections[1].strip()
                else:
                    result.ai_executive_summary = summary
                    result.ai_content_plan = None

            logger.info("Executive summary generated successfully")
        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}")
            result.ai_executive_summary = f"Executive summary unavailable: {e}"

        current_step += 1
        if progress_callback:
            progress_callback(1.0, "AI analysis complete")
