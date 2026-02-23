"""Group 2: Query Intelligence (Tasks 7-16).

Advanced query-level analysis for uncovering search behavior patterns:
long-tail cluster gaps, zero-click queries, intent drift, question mining,
CTR anomalies, navigational misrouting, broad-to-longtail opportunities,
high-CTR low-impression expansion, seasonality, and spam detection.
"""

import re

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


class QueryIntelligenceAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        7: "task_07_long_tail_cluster_gap",
        8: "task_08_zero_click_queries",
        9: "task_09_search_intent_drift",
        10: "task_10_question_format_mining",
        11: "task_11_high_imp_top_pos_low_ctr",
        12: "task_12_navigational_misrouting",
        13: "task_13_broad_to_longtail",
        14: "task_14_high_ctr_low_impression",
        15: "task_15_seasonality_patterns",
        16: "task_16_spam_query_check",
    }

    # ------------------------------------------------------------------ #
    # Task 7 — Long-Tail Query Cluster Gap Analysis
    # ------------------------------------------------------------------ #
    def task_07_long_tail_cluster_gap(self) -> list[AuditFinding]:
        """Cluster queries by word count and identify long-tail gaps."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        df = df.copy()
        df["word_count"] = df["query"].str.split().str.len()
        df["tier"] = df["word_count"].apply(
            lambda wc: "Head (1-2 words)" if wc <= 2
            else "Mid-Tail (3 words)" if wc == 3
            else "Long-Tail (4+ words)"
        )

        total_clicks = df["clicks"].sum()
        if total_clicks == 0:
            return []

        tier_stats = df.groupby("tier").agg(
            queries=("query", "count"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            avg_position=("position", "mean"),
        ).reset_index()
        tier_stats["click_share_pct"] = (tier_stats["clicks"] / total_clicks * 100).round(1)
        tier_stats["avg_position"] = tier_stats["avg_position"].round(1)
        tier_stats.columns = ["Tier", "Queries", "Clicks", "Impressions", "Avg Position", "Click Share %"]

        # Identify long-tail clusters with strong impressions but low clicks
        long_tail = df[df["word_count"] >= 4].copy()
        lt_opportunities = long_tail[
            (long_tail["impressions"] >= 50) & (long_tail["clicks"] <= 2)
        ].sort_values("impressions", ascending=False)

        if lt_opportunities.empty:
            return [self.create_finding(
                task_id=7,
                severity=Severity.INSIGHT,
                summary="Long-tail query distribution is healthy. No significant clusters with strong impressions lacking dedicated page coverage.",
                data_table=tier_stats,
            )]

        lt_display = lt_opportunities.head(50)[["query", "impressions", "clicks", "position"]].copy()
        lt_display.columns = ["Query", "Impressions", "Clicks", "Avg Position"]
        lt_display["Avg Position"] = lt_display["Avg Position"].round(1)

        estimated_clicks = int(lt_opportunities["impressions"].sum() * 0.03)
        severity = Severity.HIGH if len(lt_opportunities) > 30 else Severity.MEDIUM

        return [
            self.create_finding(
                task_id=7,
                severity=severity,
                summary=f"Found {len(lt_opportunities)} long-tail queries with meaningful impressions but near-zero clicks. "
                        f"These queries are generating visibility without dedicated page mapping, "
                        f"representing an estimated {estimated_clicks:,} untapped clicks.",
                affected_count=len(lt_opportunities),
                opportunity_value=f"~{estimated_clicks:,} potential clicks",
                data_table=lt_display,
                recommendations=[
                    "Create dedicated content pages targeting clusters of related long-tail queries.",
                    "Add FAQ sections to existing pages that address these long-tail queries directly.",
                    "Use long-tail queries as H2/H3 headings within topically relevant content.",
                    "Build internal links from high-authority pages using these long-tail queries as anchor text.",
                    "Group similar long-tail queries into topic clusters and create hub pages.",
                ],
            ),
        ]

    # ------------------------------------------------------------------ #
    # Task 8 — Zero-Click Query Identification
    # ------------------------------------------------------------------ #
    def task_08_zero_click_queries(self) -> list[AuditFinding]:
        """Find high-impression queries with near-zero CTR (SERP feature displacement)."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        zero_click = df[
            (df["impressions"] > 500) & (df["ctr"] < 0.005)
        ].sort_values("impressions", ascending=False).copy()

        if zero_click.empty:
            return [self.create_finding(
                task_id=8,
                severity=Severity.INSIGHT,
                summary="No zero-click queries detected. All high-impression queries are generating reasonable click-through rates.",
            )]

        zero_click["ctr_pct"] = (zero_click["ctr"] * 100).round(2)
        display = zero_click.head(50)[["query", "impressions", "clicks", "ctr_pct", "position"]].copy()
        display.columns = ["Query", "Impressions", "Clicks", "CTR %", "Avg Position"]
        display["Avg Position"] = display["Avg Position"].round(1)

        total_lost_impressions = int(zero_click["impressions"].sum())
        severity = Severity.HIGH if len(zero_click) > 20 else Severity.MEDIUM

        return [self.create_finding(
            task_id=8,
            severity=severity,
            summary=f"Found {len(zero_click)} queries with over 500 impressions but CTR below 0.5%. "
                    f"These {total_lost_impressions:,} total impressions are likely being absorbed by "
                    f"SERP features such as AI Overviews, Featured Snippets, or Knowledge Panels.",
            affected_count=len(zero_click),
            opportunity_value=f"{total_lost_impressions:,} impressions at risk",
            data_table=display,
            recommendations=[
                "Target Featured Snippet formats (lists, tables, definitions) for these queries.",
                "Add structured data markup (FAQ, HowTo) to improve SERP feature eligibility.",
                "Optimize for AI Overview inclusion by providing clear, authoritative answers.",
                "Consider whether these queries are worth pursuing or if effort is better spent on click-generating queries.",
                "Monitor which SERP features are appearing for these queries using a SERP tracker.",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 9 — Search Intent Drift Detection
    # ------------------------------------------------------------------ #
    def task_09_search_intent_drift(self) -> list[AuditFinding]:
        """Detect queries where position or CTR changed significantly between first and last 30 days."""
        df = self.get_df("query_date_90d")
        if df.empty:
            return []

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        date_min = df["date"].min()
        date_max = df["date"].max()
        date_range = (date_max - date_min).days
        if date_range < 45:
            return []

        first_30_end = date_min + pd.Timedelta(days=30)
        last_30_start = date_max - pd.Timedelta(days=30)

        first_30 = df[df["date"] <= first_30_end]
        last_30 = df[df["date"] >= last_30_start]

        # Focus on top queries by total impressions
        total_imp = df.groupby("query")["impressions"].sum()
        top_queries = total_imp.nlargest(500).index

        first_agg = first_30[first_30["query"].isin(top_queries)].groupby("query").agg(
            avg_pos_first=("position", "mean"),
            avg_ctr_first=("ctr", "mean"),
            impressions_first=("impressions", "sum"),
        )
        last_agg = last_30[last_30["query"].isin(top_queries)].groupby("query").agg(
            avg_pos_last=("position", "mean"),
            avg_ctr_last=("ctr", "mean"),
            impressions_last=("impressions", "sum"),
        )

        comparison = first_agg.join(last_agg, how="inner")
        if comparison.empty:
            return []

        comparison["pos_change"] = comparison["avg_pos_last"] - comparison["avg_pos_first"]
        # Guard against division by zero for CTR change calculation
        comparison["ctr_change_pct"] = comparison.apply(
            lambda r: ((r["avg_ctr_last"] - r["avg_ctr_first"]) / r["avg_ctr_first"] * 100)
            if r["avg_ctr_first"] > 0 else 0,
            axis=1,
        )

        drifted = comparison[
            (comparison["pos_change"] > 3) | (comparison["ctr_change_pct"] < -30)
        ].sort_values("pos_change", ascending=False)

        if drifted.empty:
            return [self.create_finding(
                task_id=9,
                severity=Severity.INSIGHT,
                summary="No significant search intent drift detected. Top queries are maintaining stable positions and CTR over the 90-day period.",
            )]

        display = drifted.reset_index()[
            ["query", "avg_pos_first", "avg_pos_last", "pos_change", "avg_ctr_first", "avg_ctr_last", "ctr_change_pct"]
        ].copy()
        display["avg_pos_first"] = display["avg_pos_first"].round(1)
        display["avg_pos_last"] = display["avg_pos_last"].round(1)
        display["pos_change"] = display["pos_change"].round(1)
        display["avg_ctr_first"] = (display["avg_ctr_first"] * 100).round(2)
        display["avg_ctr_last"] = (display["avg_ctr_last"] * 100).round(2)
        display["ctr_change_pct"] = display["ctr_change_pct"].round(1)
        display.columns = [
            "Query", "Pos (First 30d)", "Pos (Last 30d)", "Position Change",
            "CTR % (First 30d)", "CTR % (Last 30d)", "CTR Change %",
        ]

        severity = Severity.HIGH if len(drifted) > 15 else Severity.MEDIUM

        return [self.create_finding(
            task_id=9,
            severity=severity,
            summary=f"Found {len(drifted)} queries showing intent drift — position dropped >3 spots or CTR dropped >30% "
                    f"between the first 30 days and last 30 days of the analysis window. "
                    f"This may indicate algorithm updates, new competitors, or shifting search intent.",
            affected_count=len(drifted),
            data_table=display.head(50),
            recommendations=[
                "Review SERP changes for drifting queries — has the dominant intent shifted?",
                "Update content to match the current search intent for each affected query.",
                "Check for new competitors that may have entered the SERP.",
                "Cross-reference with known Google algorithm update timelines.",
                "Consider whether your content freshness or depth needs improvement for these topics.",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 10 — Question-Format Query Mining
    # ------------------------------------------------------------------ #
    def task_10_question_format_mining(self) -> list[AuditFinding]:
        """Extract and categorize question-format queries for FAQ/PAA targeting."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        question_words = [
            "who", "what", "where", "when", "why", "how",
            "can", "does", "is", "are", "will", "should",
        ]
        pattern = r"^(" + "|".join(question_words) + r")\b"
        questions = df[df["query"].str.match(pattern, case=False, na=False)].copy()

        if questions.empty:
            return [self.create_finding(
                task_id=10,
                severity=Severity.INSIGHT,
                summary="No question-format queries detected in your search data. "
                        "This may indicate your content isn't targeting informational search intent.",
                recommendations=[
                    "Consider creating FAQ content targeting common questions in your niche.",
                    "Research People Also Ask (PAA) boxes for your core topics.",
                ],
            )]

        questions["question_type"] = questions["query"].str.extract(
            r"^(" + "|".join(question_words) + r")\b", flags=re.IGNORECASE
        )[0].str.lower()

        type_stats = questions.groupby("question_type").agg(
            query_count=("query", "count"),
            total_impressions=("impressions", "sum"),
            total_clicks=("clicks", "sum"),
            avg_position=("position", "mean"),
        ).sort_values("total_impressions", ascending=False).reset_index()
        type_stats["avg_position"] = type_stats["avg_position"].round(1)
        type_stats.columns = ["Question Type", "Query Count", "Total Impressions", "Total Clicks", "Avg Position"]

        top_questions = questions.sort_values("impressions", ascending=False).head(50)
        q_display = top_questions[["query", "impressions", "clicks", "ctr", "position"]].copy()
        q_display["ctr"] = (q_display["ctr"] * 100).round(2)
        q_display["position"] = q_display["position"].round(1)
        q_display.columns = ["Query", "Impressions", "Clicks", "CTR %", "Avg Position"]

        total_question_impressions = int(questions["impressions"].sum())
        total_impressions = int(df["impressions"].sum())
        question_share = (total_question_impressions / total_impressions * 100) if total_impressions > 0 else 0

        severity = Severity.MEDIUM if len(questions) > 20 else Severity.LOW

        return [self.create_finding(
            task_id=10,
            severity=severity,
            summary=f"Found {len(questions)} question-format queries accounting for {question_share:.1f}% of total impressions. "
                    f"These are prime candidates for FAQ schema, PAA targeting, and featured snippet optimization.",
            affected_count=len(questions),
            opportunity_value=f"{total_question_impressions:,} question impressions",
            data_table=q_display,
            recommendations=[
                "Create dedicated FAQ pages or sections addressing the most-asked question types.",
                "Add FAQ structured data (schema.org) to pages targeting question queries.",
                "Format answers in concise, snippet-friendly paragraphs (40-60 words).",
                "Target People Also Ask (PAA) boxes by answering related questions on the same page.",
                "Use question queries as H2/H3 headings with direct answers immediately following.",
            ],
            chart_config={
                "type": "bar",
                "data": type_stats.to_dict(orient="records"),
                "x": "Question Type",
                "y": "Total Impressions",
                "title": "Question Queries by Type",
            },
        )]

    # ------------------------------------------------------------------ #
    # Task 11 — High-Impression, Top-Position, Low-CTR Anomaly
    # ------------------------------------------------------------------ #
    def task_11_high_imp_top_pos_low_ctr(self) -> list[AuditFinding]:
        """Find queries ranking 1-3 with high impressions but CTR below expected."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        top_pos = df[(df["position"] <= 3) & (df["position"] >= 1)].copy()
        if top_pos.empty:
            return []

        min_impressions = max(100, top_pos["impressions"].quantile(0.3))
        top_pos = top_pos[top_pos["impressions"] >= min_impressions]

        top_pos["expected_ctr"] = top_pos["position"].apply(self.calculate_expected_ctr)
        top_pos["ctr_gap"] = top_pos["expected_ctr"] - top_pos["ctr"]

        anomalies = top_pos[top_pos["ctr_gap"] > 0.03].sort_values("ctr_gap", ascending=False)

        if anomalies.empty:
            return [self.create_finding(
                task_id=11,
                severity=Severity.INSIGHT,
                summary="No CTR anomalies found for top-3 queries. Your titles and snippets are performing well at top positions.",
            )]

        display = anomalies.head(50).copy()
        display["ctr_pct"] = (display["ctr"] * 100).round(2)
        display["expected_ctr_pct"] = (display["expected_ctr"] * 100).round(2)
        display["gap_pct"] = (display["ctr_gap"] * 100).round(2)
        display["position"] = display["position"].round(1)
        display = display[["query", "impressions", "clicks", "ctr_pct", "expected_ctr_pct", "gap_pct", "position"]]
        display.columns = ["Query", "Impressions", "Clicks", "CTR %", "Expected CTR %", "Gap %", "Avg Position"]

        estimated_clicks = int((anomalies["impressions"] * anomalies["ctr_gap"]).sum())
        severity = Severity.HIGH if len(anomalies) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=11,
            severity=severity,
            summary=f"Found {len(anomalies)} queries ranking in positions 1-3 with CTR significantly below expectations. "
                    f"These represent title/snippet failures at the best possible position, with an estimated "
                    f"{estimated_clicks:,} clicks being left on the table.",
            affected_count=len(anomalies),
            opportunity_value=f"~{estimated_clicks:,} additional clicks",
            data_table=display,
            recommendations=[
                "These are your highest-priority title tag rewrites — you already rank #1-3.",
                "Check if SERP features (AI Overviews, Featured Snippets) are displacing your organic result.",
                "A/B test compelling title variations with power words, numbers, or brackets.",
                "Ensure meta descriptions are complete and include a clear call-to-action.",
                "Verify your structured data isn't causing snippet issues (truncated titles, wrong descriptions).",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 12 — Navigational Query Misrouting Detection
    # ------------------------------------------------------------------ #
    def task_12_navigational_misrouting(self) -> list[AuditFinding]:
        """Find navigational/brand queries where multiple pages compete for impressions."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return []

        nav_terms = ["login", "sign in", "signin", "pricing", "contact", "support",
                      "about", "help", "account", "dashboard", "signup", "sign up"]

        def is_navigational(query: str) -> bool:
            q = query.lower()
            if self.is_brand_query(q):
                return True
            return any(term in q for term in nav_terms)

        nav_queries = df[df["query"].apply(is_navigational)].copy()

        if nav_queries.empty:
            if not self.brand_name:
                return [self.create_finding(
                    task_id=12,
                    severity=Severity.INSIGHT,
                    summary="No brand name provided and no navigational queries detected. "
                            "Enter your brand name to enable navigational misrouting analysis.",
                    recommendations=["Enter your brand name in the sidebar configuration."],
                )]
            return [self.create_finding(
                task_id=12,
                severity=Severity.INSIGHT,
                summary="No navigational query misrouting detected.",
            )]

        pages_per_query = nav_queries.groupby("query").agg(
            page_count=("page", "nunique"),
            total_impressions=("impressions", "sum"),
        )
        misrouted = pages_per_query[pages_per_query["page_count"] >= 2].sort_values(
            "total_impressions", ascending=False
        )

        if misrouted.empty:
            return [self.create_finding(
                task_id=12,
                severity=Severity.INSIGHT,
                summary="All navigational queries are routing to a single page. No misrouting issues detected.",
            )]

        detail_rows = []
        for q in misrouted.head(30).index.tolist():
            query_data = nav_queries[nav_queries["query"] == q].sort_values("impressions", ascending=False)
            for _, row in query_data.iterrows():
                detail_rows.append({
                    "Query": q,
                    "Page URL": row["page"],
                    "Impressions": row["impressions"],
                    "Clicks": row["clicks"],
                    "Position": round(row["position"], 1),
                })

        display = pd.DataFrame(detail_rows)
        severity = Severity.HIGH if len(misrouted) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=12,
            severity=severity,
            summary=f"Found {len(misrouted)} navigational or brand queries where multiple pages receive impressions. "
                    f"Google is uncertain which page to surface, which can confuse users and reduce CTR.",
            affected_count=len(misrouted),
            data_table=display,
            recommendations=[
                "Ensure each navigational query has one clear canonical landing page.",
                "Add or fix canonical tags so competing pages point to the intended destination.",
                "Strengthen internal linking to the primary page for each navigational term.",
                "Review title tags and H1s on competing pages to differentiate their intent.",
                "Consider adding redirects from low-priority pages to the primary page where appropriate.",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 13 — Broad Query to Long-Tail Conversion Opportunity
    # ------------------------------------------------------------------ #
    def task_13_broad_to_longtail(self) -> list[AuditFinding]:
        """Find head terms outside top 10 with associated long-tail variants in striking distance."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        df = df.copy()
        df["word_count"] = df["query"].str.split().str.len()

        head_terms = df[(df["word_count"] <= 2) & (df["position"] > 10)].copy()
        long_tail = df[(df["word_count"] >= 4) & (df["position"] >= 4) & (df["position"] <= 15)].copy()

        if head_terms.empty or long_tail.empty:
            return [self.create_finding(
                task_id=13,
                severity=Severity.INSIGHT,
                summary="No broad-to-long-tail conversion opportunities identified. "
                        "Either head terms are already ranking well or no matching long-tail variants exist.",
            )]

        # Sort head terms by impressions for priority
        head_terms = head_terms.sort_values("impressions", ascending=False)

        opportunities = []
        for _, head_row in head_terms.head(100).iterrows():
            head_query = head_row["query"]
            # Find long-tail queries containing the head term
            matching_lt = long_tail[
                long_tail["query"].str.contains(re.escape(head_query), case=False, na=False)
            ]
            if not matching_lt.empty:
                for _, lt_row in matching_lt.head(5).iterrows():
                    opportunities.append({
                        "Head Term": head_query,
                        "Head Position": round(head_row["position"], 1),
                        "Head Impressions": head_row["impressions"],
                        "Long-Tail Query": lt_row["query"],
                        "LT Position": round(lt_row["position"], 1),
                        "LT Impressions": lt_row["impressions"],
                        "LT Clicks": lt_row["clicks"],
                    })

        if not opportunities:
            return [self.create_finding(
                task_id=13,
                severity=Severity.INSIGHT,
                summary="No matching long-tail variants found for head terms ranking outside top 10.",
            )]

        display = pd.DataFrame(opportunities).head(50)
        severity = Severity.HIGH if len(opportunities) > 20 else Severity.MEDIUM

        return [self.create_finding(
            task_id=13,
            severity=severity,
            summary=f"Found {len(opportunities)} broad-to-long-tail opportunities. "
                    f"These long-tail variants (positions 4-15) are faster wins than trying to push the head term directly. "
                    f"Ranking improvements on long-tail queries can also lift the associated head term.",
            affected_count=len(opportunities),
            data_table=display,
            recommendations=[
                "Focus content optimization on the long-tail variants first — they are easier to move.",
                "Create dedicated sections or pages targeting clusters of related long-tail queries.",
                "Use the long-tail queries as subheadings (H2/H3) in content targeting the head term.",
                "Build internal links between pages ranking for the long-tail and head term variants.",
                "As long-tail rankings improve, the head term will often follow due to topical authority.",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 14 — High-CTR, Low-Impression Query Expansion
    # ------------------------------------------------------------------ #
    def task_14_high_ctr_low_impression(self) -> list[AuditFinding]:
        """Find queries with high CTR but low impressions — topically resonant content needing more visibility."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        high_ctr = df[
            (df["ctr"] > 0.10) & (df["impressions"] < 500)
        ].sort_values("ctr", ascending=False).copy()

        if high_ctr.empty:
            return [self.create_finding(
                task_id=14,
                severity=Severity.INSIGHT,
                summary="No high-CTR low-impression queries found. "
                        "Either your high-CTR pages already have strong visibility or no queries meet the criteria.",
            )]

        display = high_ctr.head(50).copy()
        display["ctr_pct"] = (display["ctr"] * 100).round(2)
        display["position"] = display["position"].round(1)
        display = display[["query", "impressions", "clicks", "ctr_pct", "position"]]
        display.columns = ["Query", "Impressions", "Clicks", "CTR %", "Avg Position"]

        total_current_clicks = int(high_ctr["clicks"].sum())
        severity = Severity.MEDIUM if len(high_ctr) > 30 else Severity.LOW

        return [self.create_finding(
            task_id=14,
            severity=severity,
            summary=f"Found {len(high_ctr)} queries with CTR above 10% but fewer than 500 impressions. "
                    f"These pages are highly resonant with searchers — users click when they see the result. "
                    f"Increasing visibility through content depth and internal linking could significantly grow traffic.",
            affected_count=len(high_ctr),
            opportunity_value=f"{total_current_clicks:,} current clicks from resonant content",
            data_table=display,
            recommendations=[
                "Expand content depth for these queries to capture more long-tail variations.",
                "Add internal links from high-authority pages to boost these pages' visibility.",
                "Create supporting content (blog posts, guides) that link to these resonant pages.",
                "Consider whether these queries represent untapped topic clusters worth building out.",
                "Improve keyword coverage on these pages by analyzing what top-ranking competitors cover.",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 15 — Seasonality Pattern Mapping
    # ------------------------------------------------------------------ #
    def task_15_seasonality_patterns(self) -> list[AuditFinding]:
        """Identify queries with significant seasonal impression swings using 365-day data."""
        df = self.get_df("query_date_365d")
        if df.empty:
            return []

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")

        # Focus on queries with meaningful total impressions
        total_by_query = df.groupby("query")["impressions"].sum()
        min_impressions = max(200, total_by_query.quantile(0.5))
        significant_queries = total_by_query[total_by_query >= min_impressions].index

        if len(significant_queries) == 0:
            return []

        monthly = df[df["query"].isin(significant_queries)].groupby(
            ["query", "month"]
        )["impressions"].sum().reset_index()

        # Calculate peak and trough months per query
        query_seasonality = monthly.groupby("query")["impressions"].agg(
            peak=("max"),
            trough=("min"),
            mean=("mean"),
        )

        # Avoid division by zero
        query_seasonality["swing_pct"] = query_seasonality.apply(
            lambda r: ((r["peak"] - r["trough"]) / r["trough"] * 100)
            if r["trough"] > 0 else 0,
            axis=1,
        )

        seasonal = query_seasonality[query_seasonality["swing_pct"] > 50].sort_values(
            "swing_pct", ascending=False
        )

        if seasonal.empty:
            return [self.create_finding(
                task_id=15,
                severity=Severity.INSIGHT,
                summary="No significant seasonality patterns detected. Query impressions are relatively stable throughout the year.",
            )]

        # Identify peak months for top seasonal queries
        top_seasonal = seasonal.head(50)
        detail_rows = []
        for query in top_seasonal.index:
            query_monthly = monthly[monthly["query"] == query].sort_values("impressions", ascending=False)
            peak_month = query_monthly.iloc[0]["month"] if not query_monthly.empty else "N/A"
            trough_month = query_monthly.iloc[-1]["month"] if not query_monthly.empty else "N/A"
            detail_rows.append({
                "Query": query,
                "Peak Month": str(peak_month),
                "Trough Month": str(trough_month),
                "Peak Impressions": int(top_seasonal.loc[query, "peak"]),
                "Trough Impressions": int(top_seasonal.loc[query, "trough"]),
                "Swing %": round(top_seasonal.loc[query, "swing_pct"], 1),
            })

        display = pd.DataFrame(detail_rows)
        severity = Severity.MEDIUM if len(seasonal) > 20 else Severity.LOW

        return [self.create_finding(
            task_id=15,
            severity=severity,
            summary=f"Found {len(seasonal)} queries with seasonal impression swings exceeding 50%. "
                    f"Understanding these patterns enables proactive content planning and optimization timing.",
            affected_count=len(seasonal),
            data_table=display,
            recommendations=[
                "Create a content calendar aligned with seasonal demand peaks for these queries.",
                "Refresh and optimize content 4-6 weeks before the expected demand peak.",
                "Plan link-building campaigns to coincide with rising seasonal interest.",
                "Consider creating evergreen content that addresses the topic year-round.",
                "Set up monitoring alerts for queries approaching their seasonal peak.",
            ],
        )]

    # ------------------------------------------------------------------ #
    # Task 16 — Spam Query Contamination Check
    # ------------------------------------------------------------------ #
    def task_16_spam_query_check(self) -> list[AuditFinding]:
        """Scan for queries indicating potential spam, hacking, or irrelevant traffic."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        gambling_terms = [
            "casino", "poker", "slots", "slot", "blackjack", "roulette",
            "betting", "bet365", "sportsbook", "baccarat", "jackpot",
        ]
        pharma_terms = [
            "viagra", "cialis", "pharmacy", "xanax", "tramadol",
            "ambien", "oxycodone", "hydrocodone", "phentermine", "modafinil",
        ]
        adult_terms = [
            "xxx", "porn", "sex video", "nude", "naked", "adult video",
            "onlyfans leak", "escort",
        ]
        hack_indicators = [
            "hacked by", "pwned", "defaced", "eval(", "base64",
            "wp-admin", "shell.php", "backdoor",
        ]

        all_spam_terms = gambling_terms + pharma_terms + adult_terms + hack_indicators
        spam_pattern = "|".join(re.escape(term) for term in all_spam_terms)

        # Check for suspicious foreign character patterns (Cyrillic, CJK, Arabic)
        # that may indicate injected content
        foreign_char_pattern = r"[\u0400-\u04FF\u4E00-\u9FFF\u0600-\u06FF\u3040-\u30FF]"

        spam_by_term = df[df["query"].str.contains(spam_pattern, case=False, na=False, regex=True)].copy()
        spam_by_chars = df[df["query"].str.contains(foreign_char_pattern, na=False, regex=True)].copy()

        # Combine and deduplicate
        spam = pd.concat([spam_by_term, spam_by_chars]).drop_duplicates(subset=["query"])

        if spam.empty:
            return [self.create_finding(
                task_id=16,
                severity=Severity.INSIGHT,
                summary="No spam or suspicious queries detected. Your search query profile appears clean.",
            )]

        # Categorize the spam
        def categorize_spam(query: str) -> str:
            q = query.lower()
            if any(t in q for t in gambling_terms):
                return "Gambling"
            if any(t in q for t in pharma_terms):
                return "Pharmaceutical"
            if any(t in q for t in adult_terms):
                return "Adult"
            if any(t in q for t in hack_indicators):
                return "Hack Indicator"
            if re.search(foreign_char_pattern, q):
                return "Foreign Characters"
            return "Other"

        spam["category"] = spam["query"].apply(categorize_spam)

        category_stats = spam.groupby("category").agg(
            query_count=("query", "count"),
            total_impressions=("impressions", "sum"),
        ).sort_values("query_count", ascending=False).reset_index()
        category_stats.columns = ["Category", "Query Count", "Total Impressions"]

        display = spam.sort_values("impressions", ascending=False).head(50)[
            ["query", "impressions", "clicks", "position"]
        ].copy()
        display["position"] = display["position"].round(1)
        display.columns = ["Query", "Impressions", "Clicks", "Avg Position"]

        severity = Severity.CRITICAL if len(spam) > 20 else Severity.HIGH if len(spam) > 5 else Severity.MEDIUM

        return [self.create_finding(
            task_id=16,
            severity=severity,
            summary=f"Found {len(spam)} suspicious queries in your search data across these categories: "
                    f"{', '.join(category_stats['Category'].tolist())}. "
                    f"This may indicate spammy backlinks, hacked pages, or content injection.",
            affected_count=len(spam),
            data_table=display,
            recommendations=[
                "Immediately audit your site for injected or hacked pages if hack indicators are found.",
                "Check for suspicious backlinks pointing to your site using a backlink analysis tool.",
                "Submit a disavow file for domains sending spammy traffic to your site.",
                "Review your server access logs for unauthorized file modifications.",
                "If foreign character queries appear, verify your hreflang setup isn't attracting unintended markets.",
                "Monitor Google Search Console security issues panel for any flagged problems.",
            ],
        )]
