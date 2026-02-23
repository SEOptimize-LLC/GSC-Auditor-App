"""Group 3: Page-Level Deep Analysis (Tasks 17-26).

Deep-dive into individual page performance, consolidation opportunities,
parameterized URL bleed, internal linking gaps, position degradation,
rich result eligibility, and thin content detection.
"""

from datetime import timedelta

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity
from utils.url_utils import is_parameterized, get_url_directory


class PageAnalysisAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        17: "task_17_impression_to_click_funnel",
        18: "task_18_zero_impression_indexed",
        19: "task_19_new_content_ramp_up",
        20: "task_20_page_consolidation",
        21: "task_21_top_pages_vs_queries",
        22: "task_22_parameterized_url_bleed",
        23: "task_23_internal_link_opportunity",
        24: "task_24_pre_crash_detection",
        25: "task_25_rich_result_eligible",
        26: "task_26_soft_404_thin_content",
    }

    # ------------------------------------------------------------------
    # Task 17 — Impression-to-Click Funnel by Page
    # ------------------------------------------------------------------
    def task_17_impression_to_click_funnel(self) -> list[AuditFinding]:
        """For top 20 pages by impressions, calculate click conversion rates
        and identify outliers with low rates despite high impressions."""
        df = self.get_df("page_90d")
        if df.empty:
            return []

        top20 = df.nlargest(20, "impressions").copy()
        if top20.empty:
            return []

        top20["click_rate_pct"] = (top20["ctr"] * 100).round(2)
        top20["expected_ctr"] = top20["position"].apply(self.calculate_expected_ctr)
        top20["expected_ctr_pct"] = (top20["expected_ctr"] * 100).round(2)
        top20["gap_pct"] = ((top20["expected_ctr"] - top20["ctr"]) * 100).round(2)

        # Outliers: pages where actual CTR is less than half the expected CTR
        outliers = top20[top20["ctr"] < top20["expected_ctr"] * 0.5]

        display = top20[["page", "impressions", "clicks", "click_rate_pct",
                         "expected_ctr_pct", "gap_pct", "position"]].copy()
        display.columns = ["Page URL", "Impressions", "Clicks", "CTR %",
                           "Expected CTR %", "Gap %", "Avg Position"]
        display["Avg Position"] = display["Avg Position"].round(1)

        if outliers.empty:
            return [self.create_finding(
                task_id=17,
                severity=Severity.INSIGHT,
                summary=(
                    "All top-20 impression pages have click conversion rates "
                    "reasonably aligned with their ranking positions. "
                    "No major funnel leaks detected."
                ),
                data_table=display,
            )]

        estimated_missed = int((outliers["impressions"] * outliers["expected_ctr"]
                                - outliers["clicks"]).sum())

        severity = Severity.HIGH if len(outliers) >= 5 else Severity.MEDIUM

        return [self.create_finding(
            task_id=17,
            severity=severity,
            summary=(
                f"{len(outliers)} of your top-20 impression pages have click "
                f"conversion rates far below expected benchmarks. These pages "
                f"are generating visibility but failing to convert impressions "
                f"into clicks, representing an estimated {estimated_missed:,} "
                f"missed clicks."
            ),
            affected_count=len(outliers),
            opportunity_value=f"~{estimated_missed:,} missed clicks",
            data_table=display,
            recommendations=[
                "Rewrite title tags and meta descriptions for the underperforming pages to be more compelling.",
                "Ensure page titles accurately match the dominant search intent for their top queries.",
                "Test adding structured data to improve SERP presentation (ratings, dates, FAQs).",
                "Check if SERP features (featured snippets, PAA) are pushing these results below the fold.",
                "Compare your SERP snippets against competitors ranking for the same queries.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 18 — Zero-Impression Indexed Page Audit
    # ------------------------------------------------------------------
    def task_18_zero_impression_indexed(self) -> list[AuditFinding]:
        """Find all pages with zero impressions in 90 days — index bloat."""
        df = self.get_df("page_90d")
        if df.empty:
            return []

        zero_imp = df[df["impressions"] == 0].copy()

        # Enrich with URL inspection data if available
        url_inspection = self.store.get("url_inspection")
        if url_inspection and isinstance(url_inspection, dict) and not zero_imp.empty:
            zero_imp["index_status"] = zero_imp["page"].map(
                lambda u: url_inspection.get(u, {}).get("indexing_state", "Unknown")
                if isinstance(url_inspection.get(u), dict) else "Unknown"
            )
        elif not zero_imp.empty:
            zero_imp["index_status"] = "Not checked"

        if zero_imp.empty:
            return [self.create_finding(
                task_id=18,
                severity=Severity.INSIGHT,
                summary=(
                    "No zero-impression pages found. All indexed pages are "
                    "generating at least some search visibility."
                ),
            )]

        total_pages = len(df)
        bloat_pct = (len(zero_imp) / total_pages * 100) if total_pages > 0 else 0

        # Categorize by directory
        zero_imp["directory"] = zero_imp["page"].apply(get_url_directory)
        dir_summary = (
            zero_imp.groupby("directory")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )

        display = zero_imp[["page", "index_status", "directory"]].head(100).copy()
        display.columns = ["Page URL", "Index Status", "Directory"]

        severity = (
            Severity.CRITICAL if bloat_pct > 40
            else Severity.HIGH if bloat_pct > 20
            else Severity.MEDIUM
        )

        return [self.create_finding(
            task_id=18,
            severity=severity,
            summary=(
                f"Found {len(zero_imp)} pages ({bloat_pct:.1f}% of indexed pages) "
                f"with zero impressions over 90 days. This represents significant "
                f"index bloat that wastes crawl budget. Top directories affected: "
                f"{', '.join(dir_summary.head(3)['directory'].tolist())}."
            ),
            affected_count=len(zero_imp),
            data_table=display,
            recommendations=[
                "Audit zero-impression pages to determine if they should exist in the index at all.",
                "Add noindex tags to utility pages (login, cart, thank-you) that shouldn't rank.",
                "Consolidate thin or duplicate pages into stronger canonical versions.",
                "Block crawling of low-value parameter variations via robots.txt or URL parameter handling.",
                "Submit removal requests in GSC for pages that have been noindexed or deleted.",
            ],
            chart_config={
                "type": "bar",
                "data": dir_summary.head(10).to_dict(orient="records"),
                "x": "directory",
                "y": "count",
                "title": "Zero-Impression Pages by Directory",
            },
        )]

    # ------------------------------------------------------------------
    # Task 19 — New Content Ramp-Up Velocity
    # ------------------------------------------------------------------
    def task_19_new_content_ramp_up(self) -> list[AuditFinding]:
        """Find pages that first appeared in the last 60 days and track
        their impression growth at 7/14/30 day marks."""
        df = self.get_df("page_date_90d")
        if df.empty:
            return []

        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        cutoff_60d = max_date - timedelta(days=60)

        # First appearance = minimum date per page
        first_seen = df.groupby("page")["date"].min().reset_index()
        first_seen.columns = ["page", "first_seen"]

        new_pages = first_seen[first_seen["first_seen"] >= cutoff_60d].copy()

        if new_pages.empty:
            return [self.create_finding(
                task_id=19,
                severity=Severity.INSIGHT,
                summary=(
                    "No new pages detected in the last 60 days. Either no new "
                    "content was published, or new content has not yet gained "
                    "any search visibility."
                ),
                recommendations=[
                    "If new content was published recently, ensure pages are submitted in GSC.",
                    "Check that new pages are internally linked from existing high-authority pages.",
                ],
            )]

        # Calculate impressions at different milestones
        rows = []
        for _, row in new_pages.iterrows():
            page = row["page"]
            fs = row["first_seen"]
            page_data = df[df["page"] == page]

            imp_7d = page_data[page_data["date"] <= fs + timedelta(days=7)]["impressions"].sum()
            imp_14d = page_data[page_data["date"] <= fs + timedelta(days=14)]["impressions"].sum()
            imp_30d = page_data[page_data["date"] <= fs + timedelta(days=30)]["impressions"].sum()
            imp_total = page_data["impressions"].sum()
            clicks_total = page_data["clicks"].sum()
            days_active = (max_date - fs).days

            rows.append({
                "Page URL": page,
                "First Seen": fs.strftime("%Y-%m-%d"),
                "Days Active": days_active,
                "Imp (7d)": int(imp_7d),
                "Imp (14d)": int(imp_14d),
                "Imp (30d)": int(imp_30d),
                "Total Impressions": int(imp_total),
                "Total Clicks": int(clicks_total),
            })

        display = pd.DataFrame(rows).sort_values("Total Impressions", ascending=False)

        # Identify fast vs slow rampers
        fast_ramp = display[display["Imp (7d)"] > 0]
        slow_ramp = display[display["Imp (14d)"] == 0]

        avg_7d = display["Imp (7d)"].mean()
        avg_30d = display["Imp (30d)"].mean()

        severity = Severity.MEDIUM if len(slow_ramp) > len(fast_ramp) else Severity.INSIGHT

        return [self.create_finding(
            task_id=19,
            severity=severity,
            summary=(
                f"Tracked {len(new_pages)} new pages published in the last 60 days. "
                f"Average impressions at 7 days: {avg_7d:.0f}, at 30 days: {avg_30d:.0f}. "
                f"{len(fast_ramp)} pages gained impressions within the first week, "
                f"while {len(slow_ramp)} pages had zero impressions after 14 days."
            ),
            affected_count=len(new_pages),
            data_table=display.head(50),
            recommendations=[
                "Ensure new content is submitted to Google via GSC URL Inspection immediately after publishing.",
                "Build 3-5 internal links from high-authority existing pages to each new page.",
                "Share new content on social channels to accelerate initial discovery signals.",
                "Pages with zero impressions after 14 days may have indexing issues — check GSC coverage.",
                "Benchmark your ramp-up velocity against historical averages to set realistic expectations.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 20 — Page Consolidation Candidates
    # ------------------------------------------------------------------
    def task_20_page_consolidation(self) -> list[AuditFinding]:
        """Find groups of pages that share >50% of their query footprint."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return []

        # Build query sets per page (only pages with meaningful data)
        page_queries = df.groupby("page")["query"].apply(set).to_dict()

        # Filter to pages with at least a few queries
        page_queries = {p: qs for p, qs in page_queries.items() if len(qs) >= 3}
        pages = list(page_queries.keys())

        if len(pages) < 2:
            return [self.create_finding(
                task_id=20,
                severity=Severity.INSIGHT,
                summary="Not enough pages with sufficient query data to identify consolidation candidates.",
            )]

        # Compare pairs — limit to top 200 pages by total impressions to keep computation manageable
        page_imp = df.groupby("page")["impressions"].sum().nlargest(200)
        top_pages = [p for p in page_imp.index if p in page_queries]

        consolidation_pairs = []
        for i, page_a in enumerate(top_pages):
            for page_b in top_pages[i + 1:]:
                qs_a = page_queries[page_a]
                qs_b = page_queries[page_b]
                overlap = qs_a & qs_b
                min_size = min(len(qs_a), len(qs_b))
                if min_size == 0:
                    continue
                overlap_pct = len(overlap) / min_size
                if overlap_pct > 0.5:
                    consolidation_pairs.append({
                        "Page A": page_a,
                        "Page B": page_b,
                        "Shared Queries": len(overlap),
                        "Page A Queries": len(qs_a),
                        "Page B Queries": len(qs_b),
                        "Overlap %": round(overlap_pct * 100, 1),
                    })

        if not consolidation_pairs:
            return [self.create_finding(
                task_id=20,
                severity=Severity.INSIGHT,
                summary=(
                    "No significant page consolidation candidates found. "
                    "Your pages have distinct query footprints with minimal overlap."
                ),
            )]

        display = pd.DataFrame(consolidation_pairs).sort_values(
            "Overlap %", ascending=False
        )

        severity = Severity.HIGH if len(consolidation_pairs) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=20,
            severity=severity,
            summary=(
                f"Found {len(consolidation_pairs)} page pairs sharing more than "
                f"50% of their query footprint. These pages are competing against "
                f"each other and diluting ranking authority. Consolidating them "
                f"could significantly boost rankings for their shared queries."
            ),
            affected_count=len(consolidation_pairs),
            data_table=display.head(50),
            recommendations=[
                "For each pair, determine which page has stronger authority and performance metrics.",
                "Merge the weaker page's unique content into the stronger page.",
                "Set up a 301 redirect from the weaker page to the consolidated page.",
                "Update all internal links pointing to the deprecated page.",
                "Monitor rankings for the shared queries after consolidation to confirm uplift.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 21 — Top Pages vs. Top Queries Alignment
    # ------------------------------------------------------------------
    def task_21_top_pages_vs_queries(self) -> list[AuditFinding]:
        """Map top 20 highest-click pages against top 20 highest-impression
        queries. Check if highest-demand queries are served by top pages."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return []

        # Top 20 pages by clicks
        page_stats = df.groupby("page").agg(
            total_clicks=("clicks", "sum"),
            total_impressions=("impressions", "sum"),
        ).nlargest(20, "total_clicks")
        top_pages = set(page_stats.index)

        # Top 20 queries by impressions
        query_stats = df.groupby("query").agg(
            total_clicks=("clicks", "sum"),
            total_impressions=("impressions", "sum"),
        ).nlargest(20, "total_impressions")
        top_queries = set(query_stats.index)

        # Check which top queries are served by top pages
        top_query_pages = df[df["query"].isin(top_queries)].copy()
        top_query_pages["served_by_top_page"] = top_query_pages["page"].isin(top_pages)

        # For each top query, find the best-performing page
        best_per_query = (
            top_query_pages
            .sort_values(["query", "clicks"], ascending=[True, False])
            .groupby("query")
            .first()
            .reset_index()
        )

        best_per_query["alignment"] = best_per_query["page"].isin(top_pages).map(
            {True: "Aligned", False: "Misaligned"}
        )

        misaligned = best_per_query[best_per_query["alignment"] == "Misaligned"]

        display = best_per_query[["query", "page", "impressions", "clicks",
                                   "position", "alignment"]].copy()
        display.columns = ["Top Query", "Best Page", "Impressions", "Clicks",
                           "Avg Position", "Alignment"]
        display["Avg Position"] = display["Avg Position"].round(1)

        if misaligned.empty:
            return [self.create_finding(
                task_id=21,
                severity=Severity.INSIGHT,
                summary=(
                    "Your highest-demand queries are being served by your "
                    "highest-performing pages. The alignment between top "
                    "queries and top pages is strong."
                ),
                data_table=display,
            )]

        severity = Severity.HIGH if len(misaligned) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=21,
            severity=severity,
            summary=(
                f"{len(misaligned)} of the top-20 highest-impression queries are "
                f"NOT being served by your top-20 highest-click pages. This "
                f"suggests your best content isn't capturing your highest-demand "
                f"traffic. Strategic realignment could significantly boost clicks."
            ),
            affected_count=len(misaligned),
            data_table=display,
            recommendations=[
                "For misaligned queries, optimize your top-performing pages to target these high-demand terms.",
                "Add dedicated sections or FAQ blocks to top pages addressing misaligned query topics.",
                "Build internal links from top pages to the pages currently ranking for these queries.",
                "Consider creating new cornerstone content specifically targeting unserved high-demand queries.",
                "Ensure your top pages have strong on-page SEO for the highest-impression query variations.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 22 — Parameterized URL Performance Bleed
    # ------------------------------------------------------------------
    def task_22_parameterized_url_bleed(self) -> list[AuditFinding]:
        """Calculate how many impressions/clicks go to parameterized URLs
        that should be consolidated via canonical tags."""
        df = self.get_df("page_90d")
        if df.empty:
            return []

        df["is_parameterized"] = df["page"].apply(is_parameterized)
        param_pages = df[df["is_parameterized"]].copy()

        if param_pages.empty:
            return [self.create_finding(
                task_id=22,
                severity=Severity.INSIGHT,
                summary=(
                    "No parameterized URLs found in search results. "
                    "Your URL parameter handling appears clean."
                ),
            )]

        total_impressions = df["impressions"].sum()
        total_clicks = df["clicks"].sum()
        param_impressions = param_pages["impressions"].sum()
        param_clicks = param_pages["clicks"].sum()
        param_imp_pct = (param_impressions / total_impressions * 100) if total_impressions > 0 else 0
        param_click_pct = (param_clicks / total_clicks * 100) if total_clicks > 0 else 0

        # Categorize by base URL to show which clean URLs are affected
        param_pages["base_url"] = param_pages["page"].str.split("?").str[0]
        base_summary = (
            param_pages.groupby("base_url")
            .agg(
                param_variants=("page", "count"),
                total_impressions=("impressions", "sum"),
                total_clicks=("clicks", "sum"),
            )
            .sort_values("total_impressions", ascending=False)
            .reset_index()
        )
        base_summary.columns = ["Base URL", "Param Variants", "Impressions", "Clicks"]

        display = param_pages[["page", "impressions", "clicks", "position"]].copy()
        display.columns = ["Parameterized URL", "Impressions", "Clicks", "Avg Position"]
        display["Avg Position"] = display["Avg Position"].round(1)
        display = display.sort_values("Impressions", ascending=False)

        severity = (
            Severity.HIGH if param_imp_pct > 10
            else Severity.MEDIUM if param_imp_pct > 3
            else Severity.LOW
        )

        return [self.create_finding(
            task_id=22,
            severity=severity,
            summary=(
                f"Found {len(param_pages)} parameterized URLs consuming "
                f"{param_impressions:,} impressions ({param_imp_pct:.1f}%) and "
                f"{param_clicks:,} clicks ({param_click_pct:.1f}%). These URLs "
                f"fragment ranking signals and waste crawl budget. "
                f"{len(base_summary)} unique base URLs are affected."
            ),
            affected_count=len(param_pages),
            opportunity_value=f"{param_impressions:,} impressions to consolidate",
            data_table=display.head(50),
            recommendations=[
                "Add canonical tags on parameterized URLs pointing to their clean base URL.",
                "Configure URL parameter handling in GSC to tell Google which parameters to ignore.",
                "Use robots.txt to block crawling of known irrelevant parameter patterns.",
                "Implement self-referencing canonicals on all clean URLs as a defensive measure.",
                "Audit your CMS and internal links to ensure they don't generate unnecessary parameter URLs.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 23 — Internal Link Opportunity Mapping
    # ------------------------------------------------------------------
    def task_23_internal_link_opportunity(self) -> list[AuditFinding]:
        """Identify high-click pages and low-click pages ranking for similar
        queries. The high-click pages should link to low-click pages."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return []

        # Classify pages into high-click and low-click groups
        page_clicks = df.groupby("page")["clicks"].sum()
        if page_clicks.empty:
            return []

        click_median = page_clicks.median()
        high_click_pages = set(page_clicks[page_clicks >= click_median].nlargest(50).index)
        low_click_pages = set(page_clicks[page_clicks < click_median].index)

        if not high_click_pages or not low_click_pages:
            return []

        # Build query sets per page
        page_queries = df.groupby("page")["query"].apply(set).to_dict()

        # Find link opportunities: high-click pages sharing queries with low-click pages
        opportunities = []
        for high_page in high_click_pages:
            high_qs = page_queries.get(high_page, set())
            if not high_qs:
                continue
            for low_page in low_click_pages:
                low_qs = page_queries.get(low_page, set())
                if not low_qs:
                    continue
                shared = high_qs & low_qs
                if len(shared) >= 2:
                    opportunities.append({
                        "From (High-Click Page)": high_page,
                        "To (Low-Click Page)": low_page,
                        "Shared Queries": len(shared),
                        "From Page Clicks": int(page_clicks.get(high_page, 0)),
                        "To Page Clicks": int(page_clicks.get(low_page, 0)),
                        "Sample Shared Queries": ", ".join(list(shared)[:3]),
                    })

        if not opportunities:
            return [self.create_finding(
                task_id=23,
                severity=Severity.INSIGHT,
                summary=(
                    "No clear internal link opportunities found based on shared "
                    "query footprints between high-click and low-click pages."
                ),
            )]

        display = (
            pd.DataFrame(opportunities)
            .sort_values("Shared Queries", ascending=False)
            .head(50)
        )

        severity = Severity.MEDIUM if len(opportunities) > 5 else Severity.LOW

        return [self.create_finding(
            task_id=23,
            severity=severity,
            summary=(
                f"Identified {len(opportunities)} internal link opportunities where "
                f"high-click pages could pass authority to low-click pages that "
                f"rank for similar queries. Strategic internal linking can boost "
                f"rankings for the receiving pages."
            ),
            affected_count=len(opportunities),
            data_table=display,
            recommendations=[
                "Add contextual internal links from high-click pages to the identified low-click targets.",
                "Use anchor text that includes the shared queries for maximum relevance signals.",
                "Prioritize link opportunities with the highest number of shared queries.",
                "Place internal links within the main content body, not just in sidebars or footers.",
                "Monitor the receiving pages' position changes after implementing new internal links.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 24 — Pages Losing Position (Pre-Crash Detection)
    # ------------------------------------------------------------------
    def task_24_pre_crash_detection(self) -> list[AuditFinding]:
        """Compare average position in first 30 days vs. last 30 days.
        Flag pages with position degradation of 3+ spots."""
        df = self.get_df("page_date_90d")
        if df.empty:
            return []

        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        min_date = df["date"].min()

        if (max_date - min_date).days < 60:
            return [self.create_finding(
                task_id=24,
                severity=Severity.INSIGHT,
                summary="Insufficient date range for pre-crash detection. At least 60 days of data required.",
            )]

        cutoff_first = min_date + timedelta(days=30)
        cutoff_last = max_date - timedelta(days=30)

        first_30 = df[df["date"] <= cutoff_first].groupby("page").agg(
            avg_pos_first=("position", "mean"),
            clicks_first=("clicks", "sum"),
            impressions_first=("impressions", "sum"),
        )

        last_30 = df[df["date"] >= cutoff_last].groupby("page").agg(
            avg_pos_last=("position", "mean"),
            clicks_last=("clicks", "sum"),
            impressions_last=("impressions", "sum"),
        )

        comparison = first_30.join(last_30, how="inner")

        # Only consider pages with meaningful impressions in the first period
        comparison = comparison[comparison["impressions_first"] >= 10]

        comparison["position_change"] = comparison["avg_pos_last"] - comparison["avg_pos_first"]
        comparison["click_change"] = comparison["clicks_last"] - comparison["clicks_first"]

        # Flag pages losing 3+ positions (higher position number = worse)
        degrading = comparison[comparison["position_change"] >= 3].sort_values(
            "position_change", ascending=False
        )

        if degrading.empty:
            return [self.create_finding(
                task_id=24,
                severity=Severity.INSIGHT,
                summary=(
                    "No pages showing significant position degradation (3+ spots). "
                    "Your rankings appear stable across the analysis period."
                ),
            )]

        display = degrading.reset_index()[
            ["page", "avg_pos_first", "avg_pos_last", "position_change",
             "clicks_first", "clicks_last", "click_change"]
        ].copy()
        display.columns = [
            "Page URL", "Avg Pos (First 30d)", "Avg Pos (Last 30d)",
            "Position Drop", "Clicks (First 30d)", "Clicks (Last 30d)", "Click Change"
        ]
        display["Avg Pos (First 30d)"] = display["Avg Pos (First 30d)"].round(1)
        display["Avg Pos (Last 30d)"] = display["Avg Pos (Last 30d)"].round(1)
        display["Position Drop"] = display["Position Drop"].round(1)

        total_click_loss = int(degrading[degrading["click_change"] < 0]["click_change"].sum())

        severity = Severity.HIGH if len(degrading) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=24,
            severity=severity,
            summary=(
                f"Detected {len(degrading)} pages losing 3+ ranking positions "
                f"over the last 90 days. These are pre-crash signals — if left "
                f"unaddressed, these pages will likely continue declining. "
                f"Estimated click loss so far: {abs(total_click_loss):,}."
            ),
            affected_count=len(degrading),
            opportunity_value=f"~{abs(total_click_loss):,} clicks at risk",
            data_table=display.head(50),
            recommendations=[
                "Prioritize content refreshes for pages with the steepest position drops.",
                "Check if competitors have published newer, more comprehensive content on these topics.",
                "Verify these pages haven't suffered technical issues (broken links, slow load times).",
                "Strengthen internal linking to degrading pages from your highest-authority content.",
                "Investigate whether recent algorithm updates may have shifted ranking criteria for these topics.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 25 — Rich-Result-Eligible Page Identification
    # ------------------------------------------------------------------
    def task_25_rich_result_eligible(self) -> list[AuditFinding]:
        """Identify pages ranking for question-pattern queries that could
        benefit from structured data markup (FAQ, HowTo, etc.)."""
        # Check what rich result types the site already earns
        df_sa = self.get_df("searchapp_90d")
        existing_rich_types = set()
        rich_type_keywords = {
            "FAQ", "HOWTO", "REVIEW", "PRODUCT", "RECIPE", "VIDEO",
            "BREADCRUMB",
        }
        if not df_sa.empty and "searchAppearance" in df_sa.columns:
            for sa_type in df_sa["searchAppearance"].unique():
                upper = str(sa_type).upper()
                for kw in rich_type_keywords:
                    if kw in upper:
                        existing_rich_types.add(sa_type)

        # Use query-page data to find pages with question-pattern queries
        df_qp = self.get_df("query_page_90d")
        if df_qp.empty:
            return []

        question_patterns = (
            r"(?i)^(how|what|why|when|where|who|which|can|does|is|are|do)\b"
        )
        eligible = df_qp[
            df_qp["query"].str.contains(
                question_patterns, regex=True, na=False
            )
        ]

        if eligible.empty:
            return [self.create_finding(
                task_id=25,
                severity=Severity.INSIGHT,
                summary=(
                    "No question-pattern queries found in your search data. "
                    "Rich result opportunities may be limited for this site."
                ),
            )]

        # Aggregate by page — best candidates for structured data
        candidates = (
            eligible
            .groupby("page")
            .agg(
                question_queries=("query", "count"),
                total_impressions=("impressions", "sum"),
                total_clicks=("clicks", "sum"),
                sample_queries=(
                    "query",
                    lambda x: ", ".join(x.head(3).tolist()),
                ),
            )
            .sort_values("total_impressions", ascending=False)
            .reset_index()
        )
        candidates.columns = [
            "Page URL", "Question Queries", "Impressions",
            "Clicks", "Sample Queries",
        ]

        rich_note = ""
        if existing_rich_types:
            rich_note = (
                f" Your site already earns these rich result types: "
                f"{', '.join(sorted(existing_rich_types))}."
            )

        severity = Severity.MEDIUM if len(candidates) > 5 else Severity.LOW

        return [self.create_finding(
            task_id=25,
            severity=severity,
            summary=(
                f"Found {len(candidates)} pages ranking for question-pattern "
                f"queries that may benefit from structured data markup.{rich_note}"
            ),
            affected_count=len(candidates),
            data_table=candidates.head(50),
            recommendations=[
                "Add FAQ schema (JSON-LD) to pages ranking for question queries.",
                "Implement HowTo schema on tutorial and guide pages.",
                "Add Review/Product schema where applicable.",
                "Validate markup with Google's Rich Results Test tool.",
                "Monitor Search Appearance in GSC after deploying schema.",
            ],
        )]

    # ------------------------------------------------------------------
    # Task 26 — Soft 404 / Thin Content Detection
    # ------------------------------------------------------------------
    def task_26_soft_404_thin_content(self) -> list[AuditFinding]:
        """Find pages with very low impressions (<10) and zero clicks.
        Flag as potential thin content or soft 404s."""
        df = self.get_df("page_90d")
        if df.empty:
            return []

        thin = df[
            (df["impressions"] < 10) & (df["clicks"] == 0)
        ].copy()

        if thin.empty:
            return [self.create_finding(
                task_id=26,
                severity=Severity.INSIGHT,
                summary=(
                    "No potential soft 404 or thin content pages detected. "
                    "All pages are generating meaningful impressions or clicks."
                ),
            )]

        # Enrich with URL inspection data if available
        url_inspection = self.store.get("url_inspection")
        if url_inspection and isinstance(url_inspection, dict):
            thin["index_status"] = thin["page"].map(
                lambda u: url_inspection.get(u, {}).get("indexing_state", "Unknown")
                if isinstance(url_inspection.get(u), dict) else "Unknown"
            )
            thin["coverage_state"] = thin["page"].map(
                lambda u: url_inspection.get(u, {}).get("coverage_state", "Unknown")
                if isinstance(url_inspection.get(u), dict) else "Unknown"
            )
        else:
            thin["index_status"] = "Not checked"
            thin["coverage_state"] = "Not checked"

        # Categorize by directory
        thin["directory"] = thin["page"].apply(get_url_directory)
        dir_summary = (
            thin.groupby("directory")
            .agg(page_count=("page", "count"), total_impressions=("impressions", "sum"))
            .sort_values("page_count", ascending=False)
            .reset_index()
        )

        total_pages = len(df)
        thin_pct = (len(thin) / total_pages * 100) if total_pages > 0 else 0

        display = thin[["page", "impressions", "index_status", "coverage_state",
                         "directory"]].copy()
        display.columns = ["Page URL", "Impressions", "Index Status",
                           "Coverage State", "Directory"]
        display = display.sort_values("Impressions", ascending=True)

        severity = (
            Severity.HIGH if thin_pct > 25
            else Severity.MEDIUM if thin_pct > 10
            else Severity.LOW
        )

        return [self.create_finding(
            task_id=26,
            severity=severity,
            summary=(
                f"Found {len(thin)} pages ({thin_pct:.1f}% of total) with fewer "
                f"than 10 impressions and zero clicks over 90 days. These are "
                f"likely thin content pages or soft 404s. Top affected directories: "
                f"{', '.join(dir_summary.head(3)['directory'].tolist())}."
            ),
            affected_count=len(thin),
            data_table=display.head(100),
            recommendations=[
                "Manually review flagged pages — confirm whether they have substantive, unique content.",
                "Pages returning 200 status but showing error/empty content are soft 404s — fix or return proper 404.",
                "Consolidate thin pages into comprehensive topic pages where content overlaps.",
                "Add noindex to utility pages that must exist but shouldn't consume index slots.",
                "For pages with indexing issues flagged by URL Inspection, address the specific coverage errors.",
            ],
            chart_config={
                "type": "bar",
                "data": dir_summary.head(10).to_dict(orient="records"),
                "x": "directory",
                "y": "page_count",
                "title": "Thin Content / Soft 404 Pages by Directory",
            },
        )]
