"""Group 4: CTR & Position Curve Analysis (Tasks 27-31).

Analyzes click-through rate patterns relative to ranking positions:
site-specific CTR curves, title tag A/B priority, mobile vs. desktop CTR gaps,
country-specific CTR anomalies, and rich result CTR lift quantification.
"""

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


class CTRPositionAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        27: "task_27_site_ctr_curve",
        28: "task_28_title_tag_ab_priority",
        29: "task_29_mobile_vs_desktop_ctr",
        30: "task_30_country_ctr_anomaly",
        31: "task_31_rich_result_ctr_lift",
    }

    # ------------------------------------------------------------------
    # Task 27 — Site-Specific Position-to-CTR Curve
    # ------------------------------------------------------------------
    def task_27_site_ctr_curve(self) -> list[AuditFinding]:
        """Build the site's actual CTR curve and compare against industry benchmarks."""
        df = self.get_df("query_90d")
        if df.empty:
            return []

        # Only include queries with meaningful impressions to avoid noise
        min_impressions = max(10, df["impressions"].quantile(0.25))
        df = df[df["impressions"] >= min_impressions].copy()
        if df.empty:
            return []

        # Assign each query to a position bucket (1-20)
        df["position_bucket"] = df["position"].round(0).astype(int).clip(1, 20)

        # Calculate weighted average CTR per bucket (weight by impressions)
        buckets = df.groupby("position_bucket").apply(
            lambda g: pd.Series({
                "avg_ctr": (g["clicks"].sum() / g["impressions"].sum()) if g["impressions"].sum() > 0 else 0,
                "total_impressions": g["impressions"].sum(),
                "total_clicks": g["clicks"].sum(),
                "query_count": len(g),
            })
        ).reset_index()

        # Add benchmark CTR for each position
        buckets["benchmark_ctr"] = buckets["position_bucket"].apply(self.calculate_expected_ctr)
        buckets["ctr_delta"] = buckets["avg_ctr"] - buckets["benchmark_ctr"]

        # Build display table
        display = buckets.copy()
        display["Actual CTR %"] = (display["avg_ctr"] * 100).round(2)
        display["Benchmark CTR %"] = (display["benchmark_ctr"] * 100).round(2)
        display["Delta %"] = (display["ctr_delta"] * 100).round(2)
        display = display.rename(columns={
            "position_bucket": "Position",
            "total_impressions": "Impressions",
            "total_clicks": "Clicks",
            "query_count": "Queries",
        })
        display = display[["Position", "Actual CTR %", "Benchmark CTR %", "Delta %", "Impressions", "Clicks", "Queries"]]

        # Determine positions where site underperforms
        underperforming = buckets[buckets["ctr_delta"] < -0.01]
        overperforming = buckets[buckets["ctr_delta"] > 0.01]

        # Build chart config for Plotly
        chart_config = {
            "type": "line",
            "data": {
                "x": buckets["position_bucket"].tolist(),
                "y_actual": (buckets["avg_ctr"] * 100).round(2).tolist(),
                "y_benchmark": (buckets["benchmark_ctr"] * 100).round(2).tolist(),
            },
            "title": "Site CTR Curve vs. Industry Benchmark",
            "x_label": "Position",
            "y_label": "CTR %",
        }

        if len(underperforming) > len(overperforming):
            severity = Severity.MEDIUM
            summary = (
                f"Your site underperforms the industry CTR benchmark at {len(underperforming)} out of "
                f"{len(buckets)} position buckets. The biggest gaps are at positions where improved "
                f"titles and descriptions could have the most impact."
            )
        elif not underperforming.empty:
            severity = Severity.LOW
            summary = (
                f"Your site's CTR curve is mostly in line with benchmarks but underperforms at "
                f"{len(underperforming)} position(s). Overall CTR performance is reasonable."
            )
        else:
            severity = Severity.INSIGHT
            summary = (
                "Your site's CTR curve meets or exceeds industry benchmarks across all measured "
                "positions. Your titles and meta descriptions are performing well."
            )

        return [self.create_finding(
            task_id=27,
            severity=severity,
            summary=summary,
            affected_count=len(underperforming),
            data_table=display,
            recommendations=[
                "Focus title and meta description optimization on positions where your CTR falls below the benchmark.",
                "Position 1-3 gaps are highest priority — small CTR improvements here yield the most clicks.",
                "Test adding structured data to improve SERP presentation for underperforming positions.",
                "Monitor the curve monthly to measure the impact of metadata changes.",
            ],
            chart_config=chart_config,
        )]

    # ------------------------------------------------------------------
    # Task 28 — Title Tag A/B Opportunity Prioritization
    # ------------------------------------------------------------------
    def task_28_title_tag_ab_priority(self) -> list[AuditFinding]:
        """Rank pages by CTR gap vs. expected CTR to prioritize title rewrites."""
        query_df = self.get_df("query_90d")
        page_df = self.get_df("page_90d")
        if page_df.empty:
            return []

        # Work with pages that have meaningful data
        min_impressions = max(50, page_df["impressions"].quantile(0.3))
        pages = page_df[page_df["impressions"] >= min_impressions].copy()
        if pages.empty:
            return []

        # Calculate expected CTR and gap for each page based on its average position
        pages["expected_ctr"] = pages["position"].apply(self.calculate_expected_ctr)
        pages["ctr_gap"] = pages["expected_ctr"] - pages["ctr"]

        # Only consider pages underperforming their expected CTR
        underperforming = pages[pages["ctr_gap"] > 0.005].copy()
        if underperforming.empty:
            return [self.create_finding(
                task_id=28,
                severity=Severity.INSIGHT,
                summary="No pages significantly underperform their expected CTR for their position. "
                        "Title tags and meta descriptions appear well-optimized across the site.",
            )]

        # Sort by the largest negative gap (biggest opportunity first)
        underperforming = underperforming.sort_values("ctr_gap", ascending=False)

        # Calculate estimated additional clicks if CTR matched the benchmark
        underperforming["estimated_extra_clicks"] = (
            underperforming["impressions"] * underperforming["ctr_gap"]
        ).round(0).astype(int)

        # Build display table
        top = underperforming.head(50).copy()
        display = pd.DataFrame({
            "Page URL": top["page"].values,
            "Impressions": top["impressions"].values,
            "Clicks": top["clicks"].values,
            "CTR %": (top["ctr"] * 100).round(2).values,
            "Expected CTR %": (top["expected_ctr"] * 100).round(2).values,
            "Gap %": (top["ctr_gap"] * 100).round(2).values,
            "Avg Position": top["position"].round(1).values,
            "Est. Extra Clicks": top["estimated_extra_clicks"].values,
        })

        total_extra_clicks = int(underperforming["estimated_extra_clicks"].sum())
        severity = Severity.HIGH if len(underperforming) > 20 else Severity.MEDIUM

        chart_config = {
            "type": "bar",
            "data": {
                "x": top["page"].str.slice(-60).tolist(),
                "y": (top["ctr_gap"] * 100).round(2).tolist(),
            },
            "title": "Top Pages by CTR Gap (Title Rewrite Priority)",
            "x_label": "Page",
            "y_label": "CTR Gap %",
        }

        return [self.create_finding(
            task_id=28,
            severity=severity,
            summary=f"Found {len(underperforming)} pages with CTR below expected benchmarks for their position. "
                    f"Rewriting titles and meta descriptions for these pages could capture an estimated "
                    f"{total_extra_clicks:,} additional clicks.",
            affected_count=len(underperforming),
            opportunity_value=f"~{total_extra_clicks:,} additional clicks",
            data_table=display,
            recommendations=[
                "Start with the top 10 pages — these have the highest click-recovery potential.",
                "Write compelling, click-worthy titles that match the dominant search intent for each page.",
                "Include power words, numbers, or brackets in titles to stand out in SERPs.",
                "Optimize meta descriptions with clear value propositions and calls to action.",
                "Re-check CTR after 30 days to measure the impact of title changes.",
            ],
            chart_config=chart_config,
        )]

    # ------------------------------------------------------------------
    # Task 29 — Mobile vs. Desktop CTR Gap
    # ------------------------------------------------------------------
    def task_29_mobile_vs_desktop_ctr(self) -> list[AuditFinding]:
        """Compare mobile and desktop CTR for top queries and flag mobile-specific issues."""
        df = self.get_df("query_device_90d")
        if df.empty:
            return []

        # Separate mobile and desktop data
        mobile = df[df["device"] == "MOBILE"].copy()
        desktop = df[df["device"] == "DESKTOP"].copy()

        if mobile.empty or desktop.empty:
            return [self.create_finding(
                task_id=29,
                severity=Severity.INSIGHT,
                summary="Insufficient device-level data to compare mobile vs. desktop CTR. "
                        "Either mobile or desktop data is missing.",
            )]

        # Aggregate by query for each device
        mobile_agg = mobile.groupby("query").agg(
            mobile_clicks=("clicks", "sum"),
            mobile_impressions=("impressions", "sum"),
            mobile_position=("position", "mean"),
        ).reset_index()
        mobile_agg["mobile_ctr"] = (
            mobile_agg["mobile_clicks"] / mobile_agg["mobile_impressions"]
        ).fillna(0)

        desktop_agg = desktop.groupby("query").agg(
            desktop_clicks=("clicks", "sum"),
            desktop_impressions=("impressions", "sum"),
            desktop_position=("position", "mean"),
        ).reset_index()
        desktop_agg["desktop_ctr"] = (
            desktop_agg["desktop_clicks"] / desktop_agg["desktop_impressions"]
        ).fillna(0)

        # Merge on query
        merged = mobile_agg.merge(desktop_agg, on="query", how="inner")
        if merged.empty:
            return []

        # Filter for queries with meaningful volume on both devices
        min_mobile_imp = max(50, merged["mobile_impressions"].quantile(0.3))
        min_desktop_imp = max(50, merged["desktop_impressions"].quantile(0.3))
        merged = merged[
            (merged["mobile_impressions"] >= min_mobile_imp)
            & (merged["desktop_impressions"] >= min_desktop_imp)
        ]
        if merged.empty:
            return []

        # Flag queries where mobile CTR is >30% lower than desktop CTR
        # Use relative comparison: (desktop - mobile) / desktop > 0.30
        merged["ctr_gap_relative"] = (
            (merged["desktop_ctr"] - merged["mobile_ctr"]) / merged["desktop_ctr"]
        ).fillna(0)
        merged["ctr_gap_absolute"] = merged["desktop_ctr"] - merged["mobile_ctr"]

        flagged = merged[
            (merged["ctr_gap_relative"] > 0.30)
            & (merged["desktop_ctr"] > 0.005)  # Avoid flagging near-zero CTR queries
        ].sort_values("ctr_gap_absolute", ascending=False)

        if flagged.empty:
            return [self.create_finding(
                task_id=29,
                severity=Severity.INSIGHT,
                summary="No significant mobile vs. desktop CTR gaps detected. "
                        "Mobile and desktop CTR are well-aligned for your top queries.",
            )]

        # Build display table
        top = flagged.head(50).copy()
        display = pd.DataFrame({
            "Query": top["query"].values,
            "Mobile CTR %": (top["mobile_ctr"] * 100).round(2).values,
            "Desktop CTR %": (top["desktop_ctr"] * 100).round(2).values,
            "Relative Gap %": (top["ctr_gap_relative"] * 100).round(1).values,
            "Mobile Impressions": top["mobile_impressions"].astype(int).values,
            "Desktop Impressions": top["desktop_impressions"].astype(int).values,
            "Mobile Position": top["mobile_position"].round(1).values,
            "Desktop Position": top["desktop_position"].round(1).values,
        })

        lost_mobile_clicks = int(
            (flagged["mobile_impressions"] * flagged["ctr_gap_absolute"]).sum()
        )

        severity = Severity.HIGH if len(flagged) > 15 else Severity.MEDIUM

        chart_config = {
            "type": "bar",
            "data": {
                "x": top["query"].head(20).tolist(),
                "y_mobile": (top["mobile_ctr"].head(20) * 100).round(2).tolist(),
                "y_desktop": (top["desktop_ctr"].head(20) * 100).round(2).tolist(),
            },
            "title": "Mobile vs. Desktop CTR Gap (Top Affected Queries)",
            "x_label": "Query",
            "y_label": "CTR %",
        }

        return [self.create_finding(
            task_id=29,
            severity=severity,
            summary=f"Found {len(flagged)} queries where mobile CTR is >30% lower than desktop CTR. "
                    f"This indicates mobile-specific SERP presentation or UX issues costing an estimated "
                    f"{lost_mobile_clicks:,} mobile clicks.",
            affected_count=len(flagged),
            opportunity_value=f"~{lost_mobile_clicks:,} mobile clicks at risk",
            data_table=display,
            recommendations=[
                "Check if title tags are being truncated on mobile SERPs — keep titles under 55 characters.",
                "Ensure meta descriptions are compelling within mobile's shorter display limit (~120 chars).",
                "Verify mobile page speed — slow-loading pages may get deprioritized in mobile SERPs.",
                "Check for mobile-specific SERP features (ads, featured snippets) pushing organic results down.",
                "Review mobile UX signals — high bounce rates on mobile may feed back into lower CTR over time.",
            ],
            chart_config=chart_config,
        )]

    # ------------------------------------------------------------------
    # Task 30 — Country-Specific CTR Anomaly
    # ------------------------------------------------------------------
    def task_30_country_ctr_anomaly(self) -> list[AuditFinding]:
        """Flag countries where CTR deviates significantly below the site average."""
        df = self.get_df("query_country_90d")
        if df.empty:
            return []

        # Calculate site-wide average CTR
        total_clicks = df["clicks"].sum()
        total_impressions = df["impressions"].sum()
        if total_impressions == 0:
            return []
        site_avg_ctr = total_clicks / total_impressions

        # Aggregate by country
        country_stats = df.groupby("country").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            avg_position=("position", "mean"),
            query_count=("query", "nunique"),
        ).reset_index()
        country_stats["ctr"] = (
            country_stats["clicks"] / country_stats["impressions"]
        ).fillna(0)

        # Filter for countries with meaningful volume
        country_stats = country_stats[country_stats["impressions"] > 1000]
        if country_stats.empty:
            return [self.create_finding(
                task_id=30,
                severity=Severity.INSIGHT,
                summary="Not enough country-level data (>1,000 impressions per country) to perform CTR anomaly analysis.",
            )]

        # Calculate deviation from site average
        country_stats["ctr_deviation"] = (
            (country_stats["ctr"] - site_avg_ctr) / site_avg_ctr
        )

        # Flag countries where CTR is >30% below average
        anomalies = country_stats[country_stats["ctr_deviation"] < -0.30].copy()
        anomalies = anomalies.sort_values("ctr_deviation")

        if anomalies.empty:
            return [self.create_finding(
                task_id=30,
                severity=Severity.INSIGHT,
                summary=f"No country-specific CTR anomalies detected. All countries with significant "
                        f"volume are within 30% of the site average CTR ({site_avg_ctr * 100:.2f}%).",
            )]

        # Build display table
        display = pd.DataFrame({
            "Country": anomalies["country"].values,
            "CTR %": (anomalies["ctr"] * 100).round(2).values,
            "Site Avg CTR %": round(site_avg_ctr * 100, 2),
            "Deviation %": (anomalies["ctr_deviation"] * 100).round(1).values,
            "Impressions": anomalies["impressions"].astype(int).values,
            "Clicks": anomalies["clicks"].astype(int).values,
            "Avg Position": anomalies["avg_position"].round(1).values,
            "Unique Queries": anomalies["query_count"].astype(int).values,
        })

        # Also show all countries for the chart
        chart_countries = country_stats.sort_values("impressions", ascending=False).head(20)
        chart_config = {
            "type": "bar",
            "data": {
                "x": chart_countries["country"].tolist(),
                "y_ctr": (chart_countries["ctr"] * 100).round(2).tolist(),
                "y_benchmark": [round(site_avg_ctr * 100, 2)] * len(chart_countries),
            },
            "title": "CTR by Country vs. Site Average",
            "x_label": "Country",
            "y_label": "CTR %",
        }

        lost_clicks = int(
            (anomalies["impressions"] * (site_avg_ctr - anomalies["ctr"])).sum()
        )
        severity = Severity.MEDIUM if len(anomalies) > 3 else Severity.LOW

        return [self.create_finding(
            task_id=30,
            severity=severity,
            summary=f"Found {len(anomalies)} countries with CTR more than 30% below the site average "
                    f"({site_avg_ctr * 100:.2f}%). This may indicate localization issues, SERP feature "
                    f"differences, or content-market mismatches costing an estimated {lost_clicks:,} clicks.",
            affected_count=len(anomalies),
            opportunity_value=f"~{lost_clicks:,} potential clicks with CTR normalization",
            data_table=display,
            recommendations=[
                "Investigate SERP layouts in underperforming countries — ad density and SERP features vary by region.",
                "Check if titles and meta descriptions resonate with local audiences (language, cultural relevance).",
                "Consider creating localized content or hreflang tags for high-volume underperforming countries.",
                "Verify that ranking positions are similar across countries — lower positions will naturally reduce CTR.",
                "Review if competitors in those countries have stronger SERP presentations (rich results, sitelinks).",
            ],
            chart_config=chart_config,
        )]

    # ------------------------------------------------------------------
    # Task 31 — Rich Result CTR Lift Quantification
    # ------------------------------------------------------------------
    def task_31_rich_result_ctr_lift(self) -> list[AuditFinding]:
        """Compare CTR for queries with rich results vs. without to quantify the lift."""
        df = self.get_df("query_searchapp_90d")
        if df.empty:
            return []

        # Identify rich result types (anything other than plain "WEB" appearance)
        # searchAppearance may contain values like RICH_RESULT, AMP, VIDEO, etc.
        # Queries appearing in this DataFrame have some form of search appearance annotation
        if "searchAppearance" not in df.columns:
            return []

        # Get the set of queries that have rich results
        rich_queries = df[
            df["searchAppearance"].str.upper() != "WEB"
        ]["query"].unique() if not df.empty else []

        if len(rich_queries) == 0:
            return [self.create_finding(
                task_id=31,
                severity=Severity.INSIGHT,
                summary="No rich result search appearances found in the data. "
                        "Consider implementing structured data to qualify for rich results.",
                recommendations=[
                    "Add Schema.org structured data (FAQ, HowTo, Review, Product) to eligible pages.",
                    "Use Google's Rich Results Test to validate your markup.",
                    "Focus on content types most likely to trigger rich results in your niche.",
                ],
            )]

        # Aggregate rich-result queries: total clicks and impressions from rich appearances
        rich_df = df[df["searchAppearance"].str.upper() != "WEB"].copy()
        rich_agg = rich_df.groupby("query").agg(
            rich_clicks=("clicks", "sum"),
            rich_impressions=("impressions", "sum"),
            rich_position=("position", "mean"),
        ).reset_index()
        rich_agg["rich_ctr"] = (
            rich_agg["rich_clicks"] / rich_agg["rich_impressions"]
        ).fillna(0)

        # Get baseline CTR for the same queries from the standard query data
        # to compare apples-to-apples
        query_df = self.get_df("query_90d")
        if query_df.empty:
            # Fall back to using the search appearance data for non-rich comparisons
            non_rich_df = df[df["searchAppearance"].str.upper() == "WEB"]
            if non_rich_df.empty:
                baseline_agg = pd.DataFrame(columns=["query", "baseline_ctr", "baseline_impressions"])
            else:
                baseline_agg = non_rich_df.groupby("query").agg(
                    baseline_clicks=("clicks", "sum"),
                    baseline_impressions=("impressions", "sum"),
                    baseline_position=("position", "mean"),
                ).reset_index()
                baseline_agg["baseline_ctr"] = (
                    baseline_agg["baseline_clicks"] / baseline_agg["baseline_impressions"]
                ).fillna(0)
        else:
            baseline_agg = query_df.rename(columns={
                "clicks": "baseline_clicks",
                "impressions": "baseline_impressions",
                "ctr": "baseline_ctr",
                "position": "baseline_position",
            })

        # Merge rich result data with baseline
        merged = rich_agg.merge(
            baseline_agg[["query", "baseline_ctr", "baseline_impressions", "baseline_position"]],
            on="query",
            how="inner",
        )

        if merged.empty:
            return [self.create_finding(
                task_id=31,
                severity=Severity.INSIGHT,
                summary="Could not match rich result queries to baseline data for CTR comparison.",
                recommendations=["Ensure data is available for both search appearance and standard queries."],
            )]

        # Filter for meaningful volume
        min_impressions = max(20, merged["rich_impressions"].quantile(0.2))
        merged = merged[merged["rich_impressions"] >= min_impressions]
        if merged.empty:
            return []

        # Calculate CTR lift
        merged["ctr_lift"] = merged["rich_ctr"] - merged["baseline_ctr"]
        merged["ctr_lift_pct"] = (
            (merged["ctr_lift"] / merged["baseline_ctr"]) * 100
        ).fillna(0).replace([float("inf"), float("-inf")], 0)

        # Aggregate by rich result type if possible
        rich_type_agg = rich_df.groupby("searchAppearance").agg(
            type_clicks=("clicks", "sum"),
            type_impressions=("impressions", "sum"),
            query_count=("query", "nunique"),
        ).reset_index()
        rich_type_agg["type_ctr"] = (
            rich_type_agg["type_clicks"] / rich_type_agg["type_impressions"]
        ).fillna(0)

        # Calculate overall metrics
        overall_rich_ctr = (
            merged["rich_clicks"].sum() / merged["rich_impressions"].sum()
        ) if merged["rich_impressions"].sum() > 0 else 0

        overall_baseline_ctr = (
            merged["baseline_ctr"].mean()
        )

        avg_lift = overall_rich_ctr - overall_baseline_ctr
        avg_lift_pct = (avg_lift / overall_baseline_ctr * 100) if overall_baseline_ctr > 0 else 0

        # Build per-query display table
        top_queries = merged.sort_values("rich_impressions", ascending=False).head(50)
        display = pd.DataFrame({
            "Query": top_queries["query"].values,
            "Rich CTR %": (top_queries["rich_ctr"] * 100).round(2).values,
            "Baseline CTR %": (top_queries["baseline_ctr"] * 100).round(2).values,
            "CTR Lift %": (top_queries["ctr_lift"] * 100).round(2).values,
            "Relative Lift %": top_queries["ctr_lift_pct"].round(1).values,
            "Rich Impressions": top_queries["rich_impressions"].astype(int).values,
            "Avg Position": top_queries["rich_position"].round(1).values,
        })

        # Build chart config by rich result type
        chart_config = {
            "type": "bar",
            "data": {
                "x": rich_type_agg["searchAppearance"].tolist(),
                "y_ctr": (rich_type_agg["type_ctr"] * 100).round(2).tolist(),
                "y_queries": rich_type_agg["query_count"].tolist(),
            },
            "title": "CTR by Rich Result Type",
            "x_label": "Search Appearance Type",
            "y_label": "CTR %",
        }

        if avg_lift > 0:
            severity = Severity.INSIGHT
            summary = (
                f"Rich results provide a {avg_lift_pct:.1f}% relative CTR lift "
                f"({overall_rich_ctr * 100:.2f}% rich vs. {overall_baseline_ctr * 100:.2f}% baseline) "
                f"across {len(merged)} queries. Expanding structured data coverage can increase overall CTR."
            )
        else:
            severity = Severity.MEDIUM
            summary = (
                f"Rich results show a negative CTR impact ({avg_lift_pct:.1f}% relative change) "
                f"across {len(merged)} queries. This may indicate that rich result features are "
                f"consuming clicks (e.g., zero-click answers) rather than driving them."
            )

        extra_clicks = int(
            (merged[merged["ctr_lift"] > 0]["rich_impressions"] * merged[merged["ctr_lift"] > 0]["ctr_lift"]).sum()
        )

        return [self.create_finding(
            task_id=31,
            severity=severity,
            summary=summary,
            affected_count=len(merged),
            opportunity_value=f"~{extra_clicks:,} extra clicks from rich results" if extra_clicks > 0 else None,
            data_table=display,
            recommendations=[
                "Expand structured data to more pages to increase rich result eligibility.",
                "Focus on rich result types with the highest CTR lift for your site.",
                "Monitor for zero-click rich results (e.g., FAQ snippets) that may reduce clicks — consider adjusting markup strategy.",
                "Use Google Search Console's Search Appearance report to track rich result growth.",
                "Validate all structured data with Google's Rich Results Test before deploying.",
            ],
            chart_config=chart_config,
        )]
