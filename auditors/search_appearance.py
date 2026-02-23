"""Group 5: Search Appearance & SERP Features (Tasks 32-37).

Analyzes rich result coverage, sitelinks, video gaps, AI overview
displacement, AMP performance, and featured snippet ownership.
"""

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


class SearchAppearanceAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        32: "task_32_rich_result_coverage",
        33: "task_33_sitelink_monitoring",
        34: "task_34_video_rich_result_gap",
        35: "task_35_ai_overview_displacement",
        36: "task_36_amp_vs_standard",
        37: "task_37_featured_snippet_ownership",
    }

    # -------------------------------------------------------------------
    # Task 32 — Rich Result Type Coverage Audit
    # -------------------------------------------------------------------
    def task_32_rich_result_coverage(self) -> list[AuditFinding]:
        """Inventory all rich result types earned and their performance."""
        sa = self.get_df("searchapp_90d")

        if sa.empty:
            return [self.create_finding(
                task_id=32,
                severity=Severity.INSIGHT,
                summary="No search appearance data available. This usually means Google has not granted any rich results for your site in the last 90 days.",
                recommendations=[
                    "Implement structured data (Schema.org) for eligible page types.",
                    "Validate markup using Google's Rich Results Test tool.",
                ],
            )]

        display = sa.copy()
        display["CTR %"] = (display["ctr"] * 100).round(2)
        display["Avg Position"] = display["position"].round(1)
        display = display[["searchAppearance", "clicks", "impressions", "CTR %", "Avg Position"]]
        display.columns = ["Search Appearance Type", "Clicks", "Impressions", "CTR %", "Avg Position"]
        display = display.sort_values("Impressions", ascending=False)

        total_types = len(display)
        total_rich_clicks = int(display["Clicks"].sum())

        severity = Severity.INSIGHT if total_types >= 3 else Severity.MEDIUM

        return [self.create_finding(
            task_id=32,
            severity=severity,
            summary=f"Your site earns {total_types} distinct search appearance types generating {total_rich_clicks:,} clicks. "
                    f"Rich results improve visibility and CTR beyond standard blue links.",
            affected_count=total_types,
            opportunity_value=f"{total_rich_clicks:,} clicks from rich results",
            data_table=display,
            recommendations=[
                "Expand structured data to page types not yet earning rich results (FAQ, How-To, Product, Review).",
                "Monitor rich result types with high impressions but low clicks — titles/descriptions may need optimization.",
                "Regularly validate structured data using Google Search Console's Enhancement reports.",
                "Prioritize adding Video schema to content pages to earn video rich results.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 33 — Sitelink Search Box Monitoring
    # -------------------------------------------------------------------
    def task_33_sitelink_monitoring(self) -> list[AuditFinding]:
        """Check for sitelinks in search appearance data."""
        sa = self.get_df("searchapp_90d")

        if sa.empty:
            return [self.create_finding(
                task_id=33,
                severity=Severity.INSIGHT,
                summary="No search appearance data available to check for sitelinks.",
                recommendations=["Ensure Google Search Console search appearance data is being collected."],
            )]

        sitelink_keywords = ["sitelink", "searchbox"]
        sitelink_data = sa[
            sa["searchAppearance"].str.lower().str.contains("|".join(sitelink_keywords), na=False)
        ]

        if sitelink_data.empty:
            return [self.create_finding(
                task_id=33,
                severity=Severity.MEDIUM,
                summary="No sitelink appearances detected. "
                        "Sitelinks typically appear for strong brand queries and indicate Google's trust in your site structure.",
                recommendations=[
                    "Strengthen your brand presence and site authority to earn sitelinks.",
                    "Ensure clear site architecture with descriptive navigation labels.",
                    "Use internal linking to highlight key pages that should appear as sitelinks.",
                    "Verify that your homepage ranks #1 for brand queries — sitelinks only show for the top result.",
                ],
            )]

        total_clicks = int(sitelink_data["clicks"].sum())
        total_impressions = int(sitelink_data["impressions"].sum())

        display = sitelink_data.copy()
        display["CTR %"] = (display["ctr"] * 100).round(2)
        display = display[["searchAppearance", "clicks", "impressions", "CTR %"]]
        display.columns = ["Appearance Type", "Clicks", "Impressions", "CTR %"]

        return [self.create_finding(
            task_id=33,
            severity=Severity.INSIGHT,
            summary=f"Sitelink appearances detected generating {total_clicks:,} clicks from "
                    f"{total_impressions:,} impressions. Sitelinks increase SERP real estate and CTR.",
            affected_count=len(sitelink_data),
            opportunity_value=f"{total_clicks:,} clicks via sitelinks",
            data_table=display,
            recommendations=[
                "Monitor sitelink appearance stability — disappearing sitelinks may signal authority issues.",
                "Ensure branded queries consistently trigger sitelinks.",
                "Optimize the pages appearing as sitelinks for their respective sub-intents.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 34 — Video Rich Result Gap Analysis
    # -------------------------------------------------------------------
    def task_34_video_rich_result_gap(self) -> list[AuditFinding]:
        """Identify video rich result opportunities using appearance data and query patterns."""
        sa = self.get_df("searchapp_90d")
        query_df = self.get_df("query_90d")

        video_keywords = ["video", "richvideo"]
        has_video = False
        if not sa.empty:
            has_video = sa["searchAppearance"].str.lower().str.contains(
                "|".join(video_keywords), na=False
            ).any()

        # Find video-intent queries from query data
        video_intent_patterns = ["how to", "tutorial", "guide", "demo", "review", "unboxing", "walkthrough", "setup", "install"]

        if query_df.empty:
            return [self.create_finding(
                task_id=34,
                severity=Severity.INSIGHT,
                summary="No query data available for video rich result gap analysis.",
                recommendations=["Collect query data to enable this analysis."],
            )]

        video_intent_mask = query_df["query"].str.lower().str.contains(
            "|".join(video_intent_patterns), na=False
        )
        video_intent_queries = query_df[video_intent_mask].copy()

        if video_intent_queries.empty:
            return [self.create_finding(
                task_id=34,
                severity=Severity.INSIGHT,
                summary="No video-intent queries detected (how-to, tutorial, guide, etc.).",
                recommendations=["Continue monitoring as new video-intent queries emerge."],
            )]

        gap_summary = video_intent_queries.sort_values("impressions", ascending=False).head(50)
        display = gap_summary[["query", "clicks", "impressions", "position"]].copy()
        display["position"] = display["position"].round(1)
        display.columns = ["Query", "Clicks", "Impressions", "Avg Position"]

        total_opportunity = int(display["Impressions"].sum())
        video_status = "Your site already earns video rich results." if has_video else "Your site does NOT currently earn any video rich results."

        severity = Severity.MEDIUM if not has_video and len(video_intent_queries) > 10 else Severity.LOW

        return [self.create_finding(
            task_id=34,
            severity=severity,
            summary=f"{video_status} Found {len(video_intent_queries)} video-intent queries "
                    f"with {total_opportunity:,} impressions that could benefit from video content and VideoObject schema.",
            affected_count=len(video_intent_queries),
            opportunity_value=f"{total_opportunity:,} impressions to capture with video",
            data_table=display,
            recommendations=[
                "Create video content for the highest-impression video-intent queries.",
                "Add VideoObject structured data to pages that already contain embedded videos.",
                "Ensure video thumbnails are specified in schema for better SERP visibility.",
                "Host videos on YouTube and embed them on your site for dual exposure.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 35 — AI Overview Query Displacement Tracking
    # -------------------------------------------------------------------
    def task_35_ai_overview_displacement(self) -> list[AuditFinding]:
        """Identify queries where impressions are stable/growing but CTR has sharply declined.

        This pattern suggests AI Overviews or other SERP features are consuming clicks.
        Uses query_date_90d and compares first vs second half.
        """
        df = self.get_df("query_date_90d")

        if df.empty:
            return [self.create_finding(
                task_id=35,
                severity=Severity.INSIGHT,
                summary="No query date data available for AI overview displacement analysis.",
            )]

        df["date"] = pd.to_datetime(df["date"])
        date_range = df["date"].max() - df["date"].min()
        if date_range.days < 30:
            return [self.create_finding(
                task_id=35,
                severity=Severity.INSIGHT,
                summary="Insufficient date range for displacement analysis. Need at least 30 days of data.",
            )]

        midpoint = df["date"].min() + date_range / 2

        first_half = df[df["date"] < midpoint].groupby("query").agg(
            impressions_first=("impressions", "sum"),
            clicks_first=("clicks", "sum"),
        )
        second_half = df[df["date"] >= midpoint].groupby("query").agg(
            impressions_second=("impressions", "sum"),
            clicks_second=("clicks", "sum"),
        )

        comparison = first_half.join(second_half, how="inner")
        # Require meaningful volume
        comparison = comparison[comparison["impressions_first"] >= 50]

        # Calculate CTR for each half
        comparison["ctr_first"] = comparison["clicks_first"] / comparison["impressions_first"].replace(0, 1)
        comparison["ctr_second"] = comparison["clicks_second"] / comparison["impressions_second"].replace(0, 1)

        # Impression stability or growth + CTR decline
        comparison["impression_change_pct"] = (
            (comparison["impressions_second"] - comparison["impressions_first"])
            / comparison["impressions_first"]
            * 100
        )
        comparison["ctr_change_pct"] = (
            (comparison["ctr_second"] - comparison["ctr_first"])
            / comparison["ctr_first"].replace(0, 0.001)
            * 100
        )

        # Stable/growing impressions (>= -10%) but CTR declined significantly (> 20% drop)
        displaced = comparison[
            (comparison["impression_change_pct"] >= -10)
            & (comparison["ctr_change_pct"] < -20)
        ].sort_values("ctr_change_pct")

        if displaced.empty:
            return [self.create_finding(
                task_id=35,
                severity=Severity.INSIGHT,
                summary="No clear AI overview displacement pattern detected. CTR trends are consistent with impression changes.",
            )]

        display = displaced.reset_index().copy()
        display["ctr_first_pct"] = (display["ctr_first"] * 100).round(2)
        display["ctr_second_pct"] = (display["ctr_second"] * 100).round(2)
        display["ctr_change_pct"] = display["ctr_change_pct"].round(1)
        display["impression_change_pct"] = display["impression_change_pct"].round(1)
        display = display[["query", "impressions_first", "impressions_second", "impression_change_pct",
                           "ctr_first_pct", "ctr_second_pct", "ctr_change_pct"]].copy()
        display.columns = ["Query", "Impressions (First Half)", "Impressions (Second Half)",
                           "Impression Change %", "CTR First %", "CTR Second %", "CTR Change %"]

        lost_clicks = int(displaced["clicks_first"].sum() - displaced["clicks_second"].sum())

        severity = Severity.HIGH if len(displaced) > 15 else Severity.MEDIUM

        return [self.create_finding(
            task_id=35,
            severity=severity,
            summary=f"Found {len(displaced)} queries showing potential AI Overview displacement — "
                    f"impressions stable or growing while CTR dropped >20%. "
                    f"Estimated {lost_clicks:,} clicks lost to SERP feature absorption.",
            affected_count=len(displaced),
            opportunity_value=f"~{lost_clicks:,} displaced clicks",
            data_table=display.head(50),
            recommendations=[
                "Optimize content to be cited within AI Overviews — use clear, concise answer formats.",
                "Add FAQ sections with direct, authoritative answers to common questions.",
                "Target featured snippets for these queries as a defensive strategy.",
                "Diversify traffic sources — these queries may permanently lose organic CTR.",
                "Monitor Google's AI Overview rollout announcements for your industry vertical.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 36 — AMP vs Standard Comparison
    # -------------------------------------------------------------------
    def task_36_amp_vs_standard(self) -> list[AuditFinding]:
        """Check for AMP search appearances and assess relevance."""
        sa = self.get_df("searchapp_90d")

        if sa.empty:
            return [self.create_finding(
                task_id=36,
                severity=Severity.INSIGHT,
                summary="No search appearance data available for AMP analysis.",
            )]

        amp_keywords = ["amp", "amp_article", "amp_blue_link"]
        amp_data = sa[
            sa["searchAppearance"].str.lower().str.contains("|".join(amp_keywords), na=False)
        ]

        if amp_data.empty:
            return [self.create_finding(
                task_id=36,
                severity=Severity.INSIGHT,
                summary="No AMP appearances detected. This is expected if your site does not use AMP. "
                        "Google no longer requires AMP for Top Stories or other SERP features.",
                recommendations=[
                    "AMP is no longer required for most SERP benefits — focus on Core Web Vitals instead.",
                    "If you have legacy AMP pages, consider migrating to standard responsive pages.",
                ],
            )]

        non_amp_data = sa[
            ~sa["searchAppearance"].str.lower().str.contains("|".join(amp_keywords), na=False)
        ]

        amp_clicks = int(amp_data["clicks"].sum())
        amp_impressions = int(amp_data["impressions"].sum())
        non_amp_clicks = int(non_amp_data["clicks"].sum()) if not non_amp_data.empty else 0

        amp_click_share = amp_clicks / max(amp_clicks + non_amp_clicks, 1) * 100

        comparison = pd.DataFrame({
            "Metric": ["Total Clicks", "Total Impressions", "Avg CTR"],
            "AMP": [
                amp_clicks,
                amp_impressions,
                f"{(amp_clicks / max(amp_impressions, 1) * 100):.2f}%",
            ],
            "Non-AMP": [
                non_amp_clicks,
                int(non_amp_data["impressions"].sum()) if not non_amp_data.empty else 0,
                f"{(non_amp_clicks / max(int(non_amp_data['impressions'].sum()) if not non_amp_data.empty else 1, 1) * 100):.2f}%",
            ],
        })

        severity = Severity.MEDIUM if amp_click_share > 20 else Severity.LOW

        return [self.create_finding(
            task_id=36,
            severity=severity,
            summary=f"AMP appearances account for {amp_click_share:.1f}% of search appearance clicks. "
                    f"With AMP no longer required for SERP features, evaluate whether maintaining AMP is worth the overhead.",
            affected_count=len(amp_data),
            data_table=comparison,
            recommendations=[
                "If standard pages pass CWV thresholds, consider sunsetting AMP to reduce maintenance burden.",
                "Ensure AMP-to-standard migration uses proper redirects and canonical tags.",
                "Test removing AMP for a subset of pages and monitor performance for 30 days.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 37 — Featured Snippet Ownership Audit
    # -------------------------------------------------------------------
    def task_37_featured_snippet_ownership(self) -> list[AuditFinding]:
        """Identify featured snippet opportunities using query ranking data."""
        sa = self.get_df("searchapp_90d")
        query_df = self.get_df("query_90d")

        # Check if site already has featured snippets
        snippet_keywords = ["rich_snippet", "featured_snippet", "richsnippet"]
        has_snippets = False
        if not sa.empty:
            has_snippets = sa["searchAppearance"].str.lower().str.contains(
                "|".join(snippet_keywords), na=False
            ).any()

        if query_df.empty:
            return [self.create_finding(
                task_id=37,
                severity=Severity.INSIGHT,
                summary="No query data available for featured snippet analysis.",
            )]

        # Find queries ranking #1-3 — these are candidates for snippet capture
        top_ranking = query_df[query_df["position"] <= 3].copy()
        top_ranking = top_ranking.sort_values("impressions", ascending=False)

        if top_ranking.empty:
            return [self.create_finding(
                task_id=37,
                severity=Severity.INSIGHT,
                summary="No queries ranking in positions 1-3 found.",
            )]

        display = top_ranking.head(50).copy()
        display["position"] = display["position"].round(1)
        display["ctr_pct"] = (display["ctr"] * 100).round(2)
        display = display[["query", "position", "clicks", "impressions", "ctr_pct"]]
        display.columns = ["Query", "Avg Position", "Clicks", "Impressions", "CTR %"]

        total_impressions = int(display["Impressions"].sum())
        snippet_status = "Your site currently earns featured snippets." if has_snippets else "No featured snippet appearances detected for your site."

        severity = Severity.MEDIUM if not has_snippets and len(top_ranking) > 10 else Severity.LOW

        return [self.create_finding(
            task_id=37,
            severity=severity,
            summary=f"{snippet_status} Found {len(top_ranking)} queries ranking in positions 1-3 "
                    f"with {total_impressions:,} impressions — these are candidates for featured snippet capture.",
            affected_count=len(top_ranking),
            opportunity_value=f"{total_impressions:,} impressions eligible for snippet capture",
            data_table=display,
            recommendations=[
                "Structure content with clear question-and-answer formatting for top target queries.",
                "Add concise paragraph answers (40-60 words) immediately after H2/H3 headings.",
                "Use ordered/unordered lists and tables for list-type and comparison queries.",
                "Ensure pages have proper heading hierarchy (H1 > H2 > H3) matching query intent.",
                "Study the current featured snippet holders to understand the format Google prefers.",
            ],
        )]
