"""Group 1: Foundational Audit (Tasks 1-6).

Core SEO health checks that every audit should include:
CTR optimization, dead pages, dying content, cannibalization,
quick wins, and branded keyword performance.
"""

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


class FoundationalAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        1: "task_01_ctr_optimization",
        2: "task_02_dead_pages",
        3: "task_03_dying_content",
        4: "task_04_keyword_cannibalization",
        5: "task_05_quick_wins",
        6: "task_06_branded_keywords",
    }

    def task_01_ctr_optimization(self) -> list[AuditFinding]:
        """Identify high-impression, low-CTR queries for metadata rewrites."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        df["expected_ctr"] = df["position"].apply(self.calculate_expected_ctr)
        df["ctr_gap"] = df["expected_ctr"] - df["ctr"]

        min_impressions = max(100, df["impressions"].quantile(0.5))
        opportunities = df[
            (df["impressions"] >= min_impressions)
            & (df["ctr_gap"] > 0.02)
        ].sort_values("ctr_gap", ascending=False)

        if opportunities.empty:
            return [self.create_finding(
                task_id=1,
                severity=Severity.INSIGHT,
                summary="No significant CTR optimization opportunities found. Your titles and meta descriptions appear well-optimized relative to your ranking positions.",
            )]

        top = opportunities.head(50).copy()
        top["ctr_pct"] = (top["ctr"] * 100).round(2)
        top["expected_ctr_pct"] = (top["expected_ctr"] * 100).round(2)
        top["gap_pct"] = (top["ctr_gap"] * 100).round(2)
        display = top[["query", "impressions", "clicks", "ctr_pct", "expected_ctr_pct", "gap_pct", "position"]].copy()
        display.columns = ["Query", "Impressions", "Clicks", "CTR %", "Expected CTR %", "Gap %", "Avg Position"]

        estimated_clicks = int((top["impressions"] * top["ctr_gap"]).sum())

        severity = Severity.HIGH if len(opportunities) > 20 else Severity.MEDIUM

        return [self.create_finding(
            task_id=1,
            severity=severity,
            summary=f"Found {len(opportunities)} queries with CTR significantly below expected benchmarks for their position. "
                    f"Optimizing titles and meta descriptions for these queries could capture an estimated {estimated_clicks:,} additional clicks.",
            affected_count=len(opportunities),
            opportunity_value=f"~{estimated_clicks:,} additional clicks",
            data_table=display,
            recommendations=[
                "Rewrite title tags for the top underperforming queries to be more compelling and click-worthy.",
                "Add power words, numbers, or emotional triggers to meta descriptions.",
                "Test adding the current year to titles for time-sensitive queries.",
                "Ensure titles match search intent — informational queries need educational titles, transactional need action-oriented ones.",
            ],
        )]

    def task_02_dead_pages(self) -> list[AuditFinding]:
        """Detect URLs with zero or near-zero impressions over 90 days."""
        df = self.get_df("page_90d")
        if df.empty:
            return []

        dead = df[
            (df["clicks"] == 0) & (df["impressions"] <= 5)
        ].sort_values("impressions", ascending=True)

        if dead.empty:
            return [self.create_finding(
                task_id=2,
                severity=Severity.INSIGHT,
                summary="No dead pages detected. All indexed pages are generating at least some impressions.",
            )]

        total_pages = len(df)
        dead_pct = (len(dead) / total_pages * 100) if total_pages > 0 else 0

        display = dead[["page", "impressions", "clicks"]].copy()
        display.columns = ["Page URL", "Impressions", "Clicks"]

        severity = Severity.CRITICAL if dead_pct > 30 else Severity.HIGH if dead_pct > 15 else Severity.MEDIUM

        return [self.create_finding(
            task_id=2,
            severity=severity,
            summary=f"Found {len(dead)} dead pages ({dead_pct:.1f}% of indexed pages) generating zero clicks and near-zero impressions. "
                    f"These pages dilute your crawl budget and site quality signals.",
            affected_count=len(dead),
            data_table=display.head(100),
            recommendations=[
                "Evaluate each dead page: does it serve a purpose or have potential?",
                "Consolidate thin content pages into stronger, comprehensive pages.",
                "301 redirect obsolete pages to relevant live pages.",
                "Use noindex on pages that must exist but shouldn't consume index slots.",
                "Consider removing truly worthless pages and returning 410 Gone.",
            ],
        )]

    def task_03_dying_content(self) -> list[AuditFinding]:
        """Monitor pages with consistent decline in clicks over 90 days."""
        df = self.get_df("page_date_90d")
        if df.empty:
            return []

        df["date"] = pd.to_datetime(df["date"])
        date_range = df["date"].max() - df["date"].min()
        if date_range.days < 60:
            return []

        midpoint = df["date"].min() + date_range / 2
        first_half = df[df["date"] < midpoint].groupby("page").agg(
            clicks_first=("clicks", "sum"),
            impressions_first=("impressions", "sum"),
        )
        second_half = df[df["date"] >= midpoint].groupby("page").agg(
            clicks_second=("clicks", "sum"),
            impressions_second=("impressions", "sum"),
        )

        comparison = first_half.join(second_half, how="inner")
        comparison = comparison[comparison["clicks_first"] >= 10]

        comparison["click_change_pct"] = (
            (comparison["clicks_second"] - comparison["clicks_first"])
            / comparison["clicks_first"]
            * 100
        )
        comparison["impression_change_pct"] = (
            (comparison["impressions_second"] - comparison["impressions_first"])
            / comparison["impressions_first"]
            * 100
        )

        dying = comparison[
            (comparison["click_change_pct"] < -20)
            & (comparison["impression_change_pct"] < -10)
        ].sort_values("click_change_pct")

        if dying.empty:
            return [self.create_finding(
                task_id=3,
                severity=Severity.INSIGHT,
                summary="No significant content decay detected. Your pages are maintaining or growing their traffic.",
            )]

        display = dying.reset_index()[
            ["page", "clicks_first", "clicks_second", "click_change_pct", "impression_change_pct"]
        ].copy()
        display.columns = ["Page URL", "Clicks (First Half)", "Clicks (Second Half)", "Click Change %", "Impression Change %"]
        display["Click Change %"] = display["Click Change %"].round(1)
        display["Impression Change %"] = display["Impression Change %"].round(1)

        total_lost = int(dying["clicks_first"].sum() - dying["clicks_second"].sum())

        severity = Severity.HIGH if len(dying) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=3,
            severity=severity,
            summary=f"Found {len(dying)} pages experiencing content decay with >20% click decline. "
                    f"These pages have collectively lost approximately {total_lost:,} clicks compared to the first half of the analysis period.",
            affected_count=len(dying),
            opportunity_value=f"~{total_lost:,} clicks to recover",
            data_table=display.head(50),
            recommendations=[
                "Prioritize content refreshes for pages with the steepest declines.",
                "Update outdated information, statistics, and examples.",
                "Add new sections addressing current search intent.",
                "Improve internal linking to these pages from high-authority pages.",
                "Check if competitors have published more comprehensive content on the same topics.",
            ],
        )]

    def task_04_keyword_cannibalization(self) -> list[AuditFinding]:
        """Find multiple URLs ranking for the same query."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return []

        min_impressions = max(50, df["impressions"].quantile(0.3))
        significant = df[df["impressions"] >= min_impressions]

        pages_per_query = significant.groupby("query").agg(
            page_count=("page", "nunique"),
            total_impressions=("impressions", "sum"),
            total_clicks=("clicks", "sum"),
        )

        cannibalized = pages_per_query[pages_per_query["page_count"] >= 2].sort_values(
            "total_impressions", ascending=False
        )

        if cannibalized.empty:
            return [self.create_finding(
                task_id=4,
                severity=Severity.INSIGHT,
                summary="No keyword cannibalization detected. Each query maps to a single dominant URL.",
            )]

        cannibalized_queries = cannibalized.head(30).index.tolist()
        detail_rows = []
        for q in cannibalized_queries:
            query_data = significant[significant["query"] == q].sort_values("impressions", ascending=False)
            for _, row in query_data.iterrows():
                detail_rows.append({
                    "Query": q,
                    "Page URL": row["page"],
                    "Impressions": row["impressions"],
                    "Clicks": row["clicks"],
                    "Position": round(row["position"], 1),
                })

        display = pd.DataFrame(detail_rows)
        severity = Severity.HIGH if len(cannibalized) > 15 else Severity.MEDIUM

        return [self.create_finding(
            task_id=4,
            severity=severity,
            summary=f"Found {len(cannibalized)} queries with cannibalization issues — multiple pages competing for the same terms. "
                    f"This splits ranking authority and confuses Google about which page to show.",
            affected_count=len(cannibalized),
            data_table=display,
            recommendations=[
                "For each cannibalized query, designate one primary page as the canonical target.",
                "Merge thin competing pages into the primary page where content overlaps.",
                "Add canonical tags pointing competing pages to the primary page.",
                "Update internal links to point to the primary page for each target query.",
                "Differentiate page intent — if both pages serve different intents, optimize each for its own query variant.",
            ],
        )]

    def task_05_quick_wins(self) -> list[AuditFinding]:
        """Identify keywords ranking 8-15 with high impressions."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        quick_wins = df[
            (df["position"] >= 8) & (df["position"] <= 15)
        ].copy()

        min_impressions = max(50, quick_wins["impressions"].quantile(0.5)) if not quick_wins.empty else 50
        quick_wins = quick_wins[quick_wins["impressions"] >= min_impressions]
        quick_wins = quick_wins.sort_values("impressions", ascending=False)

        if quick_wins.empty:
            return [self.create_finding(
                task_id=5,
                severity=Severity.INSIGHT,
                summary="No quick-win opportunities found in positions 8-15 with significant impressions.",
            )]

        display = quick_wins.head(50).copy()
        display["ctr_pct"] = (display["ctr"] * 100).round(2)
        display = display[["query", "impressions", "clicks", "ctr_pct", "position"]].copy()
        display.columns = ["Query", "Impressions", "Clicks", "CTR %", "Avg Position"]
        display["Avg Position"] = display["Avg Position"].round(1)

        estimated_uplift = int(quick_wins.head(50)["impressions"].sum() * 0.03)

        return [self.create_finding(
            task_id=5,
            severity=Severity.HIGH,
            summary=f"Found {len(quick_wins)} quick-win queries in striking distance (positions 8-15) with meaningful search volume. "
                    f"These require minimal effort to push onto page one.",
            affected_count=len(quick_wins),
            opportunity_value=f"~{estimated_uplift:,} potential additional clicks",
            data_table=display,
            recommendations=[
                "Add the target query naturally to the page title, H1, and first paragraph if not already present.",
                "Improve internal linking to the ranking page using the target query as anchor text.",
                "Expand the page content to cover the topic more comprehensively than competitors.",
                "Add supporting content (FAQ sections, related subtopics) to boost topical relevance.",
                "Build 2-3 quality internal links from high-authority pages on your site.",
            ],
        )]

    def task_06_branded_keywords(self) -> list[AuditFinding]:
        """Analyze branded keyword performance vs. non-branded."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        if not self.brand_name:
            return [self.create_finding(
                task_id=6,
                severity=Severity.INSIGHT,
                summary="Brand name not provided. Enter your brand name in the sidebar to enable branded keyword analysis.",
                recommendations=["Enter your brand name in the sidebar configuration."],
            )]

        df["is_branded"] = df["query"].apply(self.is_brand_query)
        branded = df[df["is_branded"]]
        non_branded = df[~df["is_branded"]]

        total_clicks = df["clicks"].sum()
        branded_clicks = branded["clicks"].sum()
        non_branded_clicks = non_branded["clicks"].sum()
        branded_pct = (branded_clicks / total_clicks * 100) if total_clicks > 0 else 0

        branded_avg_ctr = branded["ctr"].mean() if not branded.empty else 0
        non_branded_avg_ctr = non_branded["ctr"].mean() if not non_branded.empty else 0
        branded_avg_pos = branded["position"].mean() if not branded.empty else 0

        summary_data = pd.DataFrame({
            "Metric": [
                "Total Queries", "Total Clicks", "Total Impressions",
                "Avg CTR", "Avg Position"
            ],
            "Branded": [
                len(branded), branded_clicks, branded["impressions"].sum(),
                f"{branded_avg_ctr * 100:.1f}%", f"{branded_avg_pos:.1f}",
            ],
            "Non-Branded": [
                len(non_branded), non_branded_clicks, non_branded["impressions"].sum(),
                f"{non_branded_avg_ctr * 100:.1f}%",
                f"{non_branded['position'].mean():.1f}" if not non_branded.empty else "N/A",
            ],
        })

        if branded_pct > 60:
            severity = Severity.HIGH
            summary_text = (
                f"Your site is heavily dependent on branded traffic ({branded_pct:.1f}% of clicks). "
                f"Non-branded SEO efforts need significant investment to reduce brand dependency risk."
            )
        elif branded_pct > 40:
            severity = Severity.MEDIUM
            summary_text = (
                f"Branded traffic accounts for {branded_pct:.1f}% of clicks. "
                f"There's room to grow non-branded organic visibility."
            )
        else:
            severity = Severity.INSIGHT
            summary_text = (
                f"Healthy balance: {branded_pct:.1f}% branded vs. {100 - branded_pct:.1f}% non-branded clicks. "
                f"Your SEO strategy is driving meaningful non-brand discovery traffic."
            )

        return [self.create_finding(
            task_id=6,
            severity=severity,
            summary=summary_text,
            affected_count=len(branded),
            data_table=summary_data,
            recommendations=[
                "If branded traffic is too high, invest in content targeting non-branded informational queries.",
                "Monitor branded CTR — drops may indicate reputation issues or SERP feature displacement.",
                "Track branded impression trends as a proxy for brand awareness growth.",
                "Ensure your brand SERP displays correctly (sitelinks, knowledge panel, etc.).",
            ],
        )]
