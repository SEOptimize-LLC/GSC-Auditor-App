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
        query_sa = self.get_df("query_searchapp_90d")
        page_sa = self.get_df("page_searchapp_90d")

        if query_sa.empty and page_sa.empty:
            return [self.create_finding(
                task_id=32,
                severity=Severity.INSIGHT,
                summary="No search appearance data available. This usually means Google has not granted any rich results for your site in the last 90 days.",
                recommendations=[
                    "Implement structured data (Schema.org) for eligible page types.",
                    "Validate markup using Google's Rich Results Test tool.",
                ],
            )]

        # Aggregate by search appearance type from both datasets
        findings_list: list[AuditFinding] = []

        # Query-level breakdown
        if not query_sa.empty:
            query_summary = query_sa.groupby("searchAppearance").agg(
                queries=("query", "nunique"),
                clicks=("clicks", "sum"),
                impressions=("impressions", "sum"),
            ).sort_values("impressions", ascending=False).reset_index()
            query_summary.columns = ["Rich Result Type", "Unique Queries", "Clicks", "Impressions"]
        else:
            query_summary = pd.DataFrame()

        # Page-level breakdown
        if not page_sa.empty:
            page_summary = page_sa.groupby("searchAppearance").agg(
                pages=("page", "nunique"),
                clicks=("clicks", "sum"),
                impressions=("impressions", "sum"),
            ).sort_values("impressions", ascending=False).reset_index()
            page_summary.columns = ["Rich Result Type", "Unique Pages", "Clicks", "Impressions"]
        else:
            page_summary = pd.DataFrame()

        # Build combined display table
        if not query_summary.empty and not page_summary.empty:
            display = query_summary.merge(
                page_summary[["Rich Result Type", "Unique Pages"]],
                on="Rich Result Type",
                how="outer",
            )
            display = display.fillna(0)
            for col in ["Unique Queries", "Clicks", "Impressions", "Unique Pages"]:
                if col in display.columns:
                    display[col] = display[col].astype(int)
            display = display.sort_values("Impressions", ascending=False)
        elif not query_summary.empty:
            display = query_summary
        else:
            display = page_summary

        total_types = len(display)
        total_rich_clicks = int(display["Clicks"].sum()) if "Clicks" in display.columns else 0

        severity = Severity.INSIGHT if total_types >= 3 else Severity.MEDIUM

        return [self.create_finding(
            task_id=32,
            severity=severity,
            summary=f"Your site earns {total_types} distinct rich result types generating {total_rich_clicks:,} clicks. "
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
        """Check for sitelinks in search appearance data and monitor brand query association."""
        query_sa = self.get_df("query_searchapp_90d")

        if query_sa.empty:
            return [self.create_finding(
                task_id=33,
                severity=Severity.INSIGHT,
                summary="No search appearance data available to check for sitelinks.",
                recommendations=["Ensure Google Search Console search appearance data is being collected."],
            )]

        # Filter for sitelink-related appearances
        sitelink_keywords = ["sitelink", "searchbox"]
        sitelink_data = query_sa[
            query_sa["searchAppearance"].str.lower().str.contains("|".join(sitelink_keywords), na=False)
        ]

        if sitelink_data.empty:
            return [self.create_finding(
                task_id=33,
                severity=Severity.MEDIUM,
                summary="No sitelink appearances detected in search appearance data. "
                        "Sitelinks typically appear for strong brand queries and indicate Google's trust in your site structure.",
                recommendations=[
                    "Strengthen your brand presence and site authority to earn sitelinks.",
                    "Ensure clear site architecture with descriptive navigation labels.",
                    "Use internal linking to highlight key pages that should appear as sitelinks.",
                    "Verify that your homepage ranks #1 for brand queries — sitelinks only show for the top result.",
                ],
            )]

        # Analyze which queries trigger sitelinks
        sitelink_summary = sitelink_data.groupby("query").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        ).sort_values("impressions", ascending=False).reset_index()

        sitelink_summary["ctr_pct"] = (
            (sitelink_summary["clicks"] / sitelink_summary["impressions"].replace(0, 1)) * 100
        ).round(2)

        sitelink_summary.columns = ["Query", "Clicks", "Impressions", "CTR %"]

        # Check how many are branded
        branded_count = sum(
            1 for q in sitelink_summary["Query"]
            if self.is_brand_query(q)
        )
        total_queries = len(sitelink_summary)
        total_clicks = int(sitelink_summary["Clicks"].sum())

        severity = Severity.INSIGHT

        return [self.create_finding(
            task_id=33,
            severity=severity,
            summary=f"Sitelinks appear for {total_queries} queries ({branded_count} branded) generating "
                    f"{total_clicks:,} clicks. Sitelinks increase SERP real estate and CTR.",
            affected_count=total_queries,
            opportunity_value=f"{total_clicks:,} clicks via sitelinks",
            data_table=sitelink_summary.head(30),
            recommendations=[
                "Monitor sitelink appearance stability — disappearing sitelinks may signal authority issues.",
                "Ensure branded queries consistently trigger sitelinks.",
                "Optimize the pages appearing as sitelinks for their respective sub-intents.",
                "Use Google Search Console to demote undesirable sitelink URLs if needed.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 34 — Video Rich Result Gap Analysis
    # -------------------------------------------------------------------
    def task_34_video_rich_result_gap(self) -> list[AuditFinding]:
        """Find pages that could benefit from Video rich results but don't have them."""
        page_sa = self.get_df("page_searchapp_90d")
        query_sa = self.get_df("query_searchapp_90d")

        if page_sa.empty and query_sa.empty:
            return [self.create_finding(
                task_id=34,
                severity=Severity.INSIGHT,
                summary="No search appearance data available for video rich result gap analysis.",
                recommendations=["Collect search appearance data to enable this analysis."],
            )]

        # Identify pages/queries already with video rich results
        video_keywords = ["video", "richvideo"]
        pages_with_video: set[str] = set()
        if not page_sa.empty:
            video_pages = page_sa[
                page_sa["searchAppearance"].str.lower().str.contains("|".join(video_keywords), na=False)
            ]
            pages_with_video = set(video_pages["page"].unique())

        # Identify queries that suggest video intent but lack video rich results
        video_intent_patterns = ["how to", "tutorial", "guide", "demo", "review", "unboxing", "walkthrough", "setup", "install"]

        if not query_sa.empty:
            # Queries suggesting video intent
            video_intent_mask = query_sa["query"].str.lower().str.contains(
                "|".join(video_intent_patterns), na=False
            )
            video_intent_queries = query_sa[video_intent_mask]

            # Of those, which do NOT have video appearance?
            video_appearance_mask = query_sa["searchAppearance"].str.lower().str.contains(
                "|".join(video_keywords), na=False
            )
            gap_queries = video_intent_queries[~video_appearance_mask]
        else:
            gap_queries = pd.DataFrame()

        if gap_queries.empty:
            return [self.create_finding(
                task_id=34,
                severity=Severity.INSIGHT,
                summary="No significant video rich result gaps found. Video-intent queries already have video appearances, "
                        "or no video-intent queries were detected.",
                recommendations=["Continue monitoring as new video-intent queries emerge."],
            )]

        gap_summary = gap_queries.groupby("query").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        ).sort_values("impressions", ascending=False).reset_index()
        gap_summary.columns = ["Query", "Clicks", "Impressions"]

        total_opportunity_impressions = int(gap_summary["Impressions"].sum())

        severity = Severity.MEDIUM if len(gap_summary) > 10 else Severity.LOW

        return [self.create_finding(
            task_id=34,
            severity=severity,
            summary=f"Found {len(gap_summary)} video-intent queries without video rich results. "
                    f"These queries (how-to, tutorial, guide, etc.) have {total_opportunity_impressions:,} impressions "
                    f"and could benefit from video content and VideoObject schema.",
            affected_count=len(gap_summary),
            opportunity_value=f"{total_opportunity_impressions:,} impressions to capture with video",
            data_table=gap_summary.head(50),
            recommendations=[
                "Create video content for the highest-impression gap queries.",
                "Add VideoObject structured data to pages that already contain embedded videos.",
                "Ensure video thumbnails are specified in schema for better SERP visibility.",
                "Host videos on YouTube and embed them on your site for dual exposure.",
                "Use descriptive video titles and descriptions that match the target queries.",
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
        """Compare AMP vs non-AMP page performance."""
        page_sa = self.get_df("page_searchapp_90d")

        if page_sa.empty:
            return [self.create_finding(
                task_id=36,
                severity=Severity.INSIGHT,
                summary="No search appearance data available for AMP analysis.",
            )]

        amp_keywords = ["amp", "AMP_ARTICLE", "AMP_BLUE_LINK"]
        amp_data = page_sa[
            page_sa["searchAppearance"].str.lower().str.contains("|".join([k.lower() for k in amp_keywords]), na=False)
        ]

        if amp_data.empty:
            return [self.create_finding(
                task_id=36,
                severity=Severity.INSIGHT,
                summary="No AMP pages detected in search appearance data. This is expected if your site does not use AMP. "
                        "Google no longer requires AMP for Top Stories or other SERP features.",
                recommendations=[
                    "AMP is no longer required for most SERP benefits — focus on Core Web Vitals instead.",
                    "If you have legacy AMP pages, consider migrating to standard responsive pages.",
                ],
            )]

        # Aggregate AMP vs non-AMP
        non_amp_data = page_sa[
            ~page_sa["searchAppearance"].str.lower().str.contains("|".join([k.lower() for k in amp_keywords]), na=False)
        ]

        amp_agg = amp_data.groupby("page").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        )
        amp_agg["type"] = "AMP"

        non_amp_agg = non_amp_data.groupby("page").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        )
        non_amp_agg["type"] = "Standard"

        comparison = pd.DataFrame({
            "Metric": ["Pages", "Total Clicks", "Total Impressions", "Avg CTR"],
            "AMP": [
                len(amp_agg),
                int(amp_agg["clicks"].sum()),
                int(amp_agg["impressions"].sum()),
                f"{(amp_agg['clicks'].sum() / max(amp_agg['impressions'].sum(), 1) * 100):.2f}%",
            ],
            "Standard": [
                len(non_amp_agg),
                int(non_amp_agg["clicks"].sum()),
                int(non_amp_agg["impressions"].sum()),
                f"{(non_amp_agg['clicks'].sum() / max(non_amp_agg['impressions'].sum(), 1) * 100):.2f}%",
            ],
        })

        amp_click_share = amp_agg["clicks"].sum() / max(amp_agg["clicks"].sum() + non_amp_agg["clicks"].sum(), 1) * 100
        severity = Severity.MEDIUM if amp_click_share > 20 else Severity.LOW

        return [self.create_finding(
            task_id=36,
            severity=severity,
            summary=f"AMP pages account for {amp_click_share:.1f}% of clicks across {len(amp_agg)} pages. "
                    f"With AMP no longer required for SERP features, evaluate whether maintaining AMP is worth the overhead.",
            affected_count=len(amp_agg),
            data_table=comparison,
            recommendations=[
                "Audit whether AMP pages outperform their standard equivalents in CTR and Core Web Vitals.",
                "If standard pages pass CWV thresholds, consider sunsetting AMP to reduce maintenance burden.",
                "Ensure AMP-to-standard migration uses proper redirects and canonical tags.",
                "Test removing AMP for a subset of pages and monitor performance for 30 days.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 37 — Featured Snippet Ownership Audit
    # -------------------------------------------------------------------
    def task_37_featured_snippet_ownership(self) -> list[AuditFinding]:
        """Find queries where site ranks #1-3 but doesn't own the featured snippet."""
        query_sa = self.get_df("query_searchapp_90d")

        if query_sa.empty:
            return [self.create_finding(
                task_id=37,
                severity=Severity.INSIGHT,
                summary="No search appearance data available for featured snippet analysis.",
            )]

        snippet_keywords = ["rich_snippet", "featured_snippet", "richsnippet"]

        # Queries that have featured snippet appearance
        snippet_queries = set(
            query_sa[
                query_sa["searchAppearance"].str.lower().str.contains(
                    "|".join(snippet_keywords), na=False
                )
            ]["query"].unique()
        )

        # Queries ranking #1-3 (from the same dataset, take best position per query)
        top_ranking = query_sa.groupby("query").agg(
            best_position=("position", "min"),
            total_clicks=("clicks", "sum"),
            total_impressions=("impressions", "sum"),
        ).reset_index()

        top_ranking = top_ranking[top_ranking["best_position"] <= 3]

        # Queries ranking #1-3 but NOT having featured snippet appearance
        no_snippet = top_ranking[~top_ranking["query"].isin(snippet_queries)].copy()
        no_snippet = no_snippet.sort_values("total_impressions", ascending=False)

        if no_snippet.empty:
            return [self.create_finding(
                task_id=37,
                severity=Severity.INSIGHT,
                summary="All top-ranking queries appear to have associated rich/featured snippet appearances, "
                        "or no queries rank in positions 1-3.",
            )]

        display = no_snippet.head(50).copy()
        display["best_position"] = display["best_position"].round(1)
        display.columns = ["Query", "Best Position", "Clicks", "Impressions"]

        total_impressions_at_stake = int(display["Impressions"].sum())

        severity = Severity.MEDIUM if len(no_snippet) > 10 else Severity.LOW

        return [self.create_finding(
            task_id=37,
            severity=severity,
            summary=f"Found {len(no_snippet)} queries ranking in positions 1-3 without featured snippet ownership. "
                    f"Winning the featured snippet for these queries could significantly boost CTR and visibility.",
            affected_count=len(no_snippet),
            opportunity_value=f"{total_impressions_at_stake:,} impressions eligible for snippet capture",
            data_table=display,
            recommendations=[
                "Structure content with clear question-and-answer formatting for top target queries.",
                "Add concise paragraph answers (40-60 words) immediately after H2/H3 headings.",
                "Use ordered/unordered lists and tables for list-type and comparison queries.",
                "Ensure pages have proper heading hierarchy (H1 > H2 > H3) matching query intent.",
                "Study the current featured snippet holders to understand the format Google prefers.",
            ],
        )]
