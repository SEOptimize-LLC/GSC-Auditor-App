"""Group 9: Trend & Strategic Analysis (Tasks 52-56).

Analyzes algorithm update impact, year-over-year demand shifts,
post-migration reconciliation, content freshness decay, and
query impression share trends.
"""

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


# Known Google algorithm update dates
ALGORITHM_UPDATES = [
    {"date": "2025-03-13", "name": "March 2025 Core Update"},
    {"date": "2025-06-01", "name": "June 2025 Core Update"},
    {"date": "2025-08-15", "name": "August 2025 Core Update"},
    {"date": "2025-11-01", "name": "November 2025 Core Update"},
]


class TrendStrategicAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        52: "task_52_algorithm_update_impact",
        53: "task_53_yoy_query_demand_shift",
        54: "task_54_post_migration_reconciliation",
        55: "task_55_content_freshness_decay",
        56: "task_56_query_impression_share",
    }

    # -------------------------------------------------------------------
    # Task 52 — Algorithm Update Impact Segmentation
    # -------------------------------------------------------------------
    def task_52_algorithm_update_impact(self) -> list[AuditFinding]:
        """Overlay known Google algorithm update dates against traffic timeline.

        Calculate traffic change within 14 days of each update.
        """
        df = self.get_df("page_date_365d")

        if df.empty:
            return [self.create_finding(
                task_id=52,
                severity=Severity.INSIGHT,
                summary="No 365-day page date data available for algorithm update impact analysis.",
            )]

        df["date"] = pd.to_datetime(df["date"])
        date_min = df["date"].min()
        date_max = df["date"].max()

        # Aggregate daily site-wide traffic
        daily_traffic = df.groupby("date").agg(
            total_clicks=("clicks", "sum"),
            total_impressions=("impressions", "sum"),
        ).sort_index()

        update_impacts = []
        for update in ALGORITHM_UPDATES:
            update_date = pd.Timestamp(update["date"])

            # Skip updates outside our data range
            if update_date < date_min or update_date > date_max:
                continue

            # 14 days before and after the update
            pre_start = update_date - pd.Timedelta(days=14)
            pre_end = update_date - pd.Timedelta(days=1)
            post_start = update_date
            post_end = update_date + pd.Timedelta(days=14)

            pre_data = daily_traffic.loc[
                (daily_traffic.index >= pre_start) & (daily_traffic.index <= pre_end)
            ]
            post_data = daily_traffic.loc[
                (daily_traffic.index >= post_start) & (daily_traffic.index <= post_end)
            ]

            if pre_data.empty or post_data.empty:
                continue

            pre_avg_clicks = pre_data["total_clicks"].mean()
            post_avg_clicks = post_data["total_clicks"].mean()
            pre_avg_impressions = pre_data["total_impressions"].mean()
            post_avg_impressions = post_data["total_impressions"].mean()

            click_change = (
                (post_avg_clicks - pre_avg_clicks) / max(pre_avg_clicks, 1) * 100
            )
            impression_change = (
                (post_avg_impressions - pre_avg_impressions) / max(pre_avg_impressions, 1) * 100
            )

            update_impacts.append({
                "Update": update["name"],
                "Date": update["date"],
                "Avg Daily Clicks (Before)": round(pre_avg_clicks, 1),
                "Avg Daily Clicks (After)": round(post_avg_clicks, 1),
                "Click Change %": round(click_change, 1),
                "Avg Daily Impressions (Before)": round(pre_avg_impressions, 1),
                "Avg Daily Impressions (After)": round(post_avg_impressions, 1),
                "Impression Change %": round(impression_change, 1),
            })

        if not update_impacts:
            return [self.create_finding(
                task_id=52,
                severity=Severity.INSIGHT,
                summary="No algorithm updates fall within the available data range. "
                        f"Data covers {date_min.strftime('%Y-%m-%d')} to {date_max.strftime('%Y-%m-%d')}.",
            )]

        display = pd.DataFrame(update_impacts)

        # Determine overall impact
        negative_updates = [u for u in update_impacts if u["Click Change %"] < -10]
        positive_updates = [u for u in update_impacts if u["Click Change %"] > 10]

        if negative_updates:
            worst = min(update_impacts, key=lambda x: x["Click Change %"])
            severity = Severity.HIGH if worst["Click Change %"] < -20 else Severity.MEDIUM
            summary_text = (
                f"Analyzed {len(update_impacts)} algorithm updates within your data period. "
                f"{len(negative_updates)} update(s) correlated with traffic decline. "
                f"Worst impact: {worst['Update']} ({worst['Click Change %']:+.1f}% click change)."
            )
        elif positive_updates:
            best = max(update_impacts, key=lambda x: x["Click Change %"])
            severity = Severity.INSIGHT
            summary_text = (
                f"Analyzed {len(update_impacts)} algorithm updates. "
                f"{len(positive_updates)} update(s) correlated with traffic gains. "
                f"Best impact: {best['Update']} ({best['Click Change %']:+.1f}% click change)."
            )
        else:
            severity = Severity.INSIGHT
            summary_text = (
                f"Analyzed {len(update_impacts)} algorithm updates. "
                f"No significant traffic changes (>10%) correlated with any update."
            )

        # Build chart config for timeline visualization
        chart_config = {
            "type": "line",
            "title": "Daily Clicks with Algorithm Update Markers",
            "x": "date",
            "y": "total_clicks",
            "annotations": [
                {"date": u["date"], "label": u["name"]} for u in ALGORITHM_UPDATES
                if pd.Timestamp(u["date"]) >= date_min and pd.Timestamp(u["date"]) <= date_max
            ],
        }

        return [self.create_finding(
            task_id=52,
            severity=severity,
            summary=summary_text,
            affected_count=len(update_impacts),
            data_table=display,
            chart_config=chart_config,
            recommendations=[
                "For negative-impact updates, audit affected pages for thin content, low E-E-A-T signals, or spammy patterns.",
                "Compare content quality against the stated goals of each core update (Google publishes guidance).",
                "Focus on improving helpfulness, originality, and expertise signals across your content.",
                "Track recovery after subsequent updates — sites often recover if underlying issues are fixed.",
                "Diversify traffic sources to reduce vulnerability to algorithm volatility.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 53 — Year-Over-Year Query Demand Shift
    # -------------------------------------------------------------------
    def task_53_yoy_query_demand_shift(self) -> list[AuditFinding]:
        """Compare same 90-day window current vs prior year for top queries."""
        df_365 = self.get_df("query_date_365d")

        if df_365.empty:
            return [self.create_finding(
                task_id=53,
                severity=Severity.INSIGHT,
                summary="No 365-day query date data available for year-over-year comparison.",
            )]

        df_365["date"] = pd.to_datetime(df_365["date"])
        date_max = df_365["date"].max()
        date_min = df_365["date"].min()

        # We need roughly a year of data
        if (date_max - date_min).days < 300:
            return [self.create_finding(
                task_id=53,
                severity=Severity.INSIGHT,
                summary=f"Only {(date_max - date_min).days} days of data available. "
                        f"Need approximately 365 days for meaningful year-over-year comparison.",
            )]

        # Define current 90-day window and prior-year equivalent
        current_end = date_max
        current_start = current_end - pd.Timedelta(days=90)
        prior_end = current_end - pd.Timedelta(days=365)
        prior_start = prior_end - pd.Timedelta(days=90)

        current_data = df_365[
            (df_365["date"] >= current_start) & (df_365["date"] <= current_end)
        ].groupby("query").agg(
            current_impressions=("impressions", "sum"),
            current_clicks=("clicks", "sum"),
        )

        prior_data = df_365[
            (df_365["date"] >= prior_start) & (df_365["date"] <= prior_end)
        ].groupby("query").agg(
            prior_impressions=("impressions", "sum"),
            prior_clicks=("clicks", "sum"),
        )

        if prior_data.empty:
            return [self.create_finding(
                task_id=53,
                severity=Severity.INSIGHT,
                summary="No data available for the prior-year comparison window. "
                        "Need data from at least one year ago.",
            )]

        comparison = current_data.join(prior_data, how="inner")
        comparison = comparison[comparison["prior_impressions"] >= 50]

        if comparison.empty:
            return [self.create_finding(
                task_id=53,
                severity=Severity.INSIGHT,
                summary="No queries with sufficient prior-year impressions for comparison.",
            )]

        comparison["impression_change_pct"] = (
            (comparison["current_impressions"] - comparison["prior_impressions"])
            / comparison["prior_impressions"]
            * 100
        ).round(1)

        comparison["click_change_pct"] = (
            (comparison["current_clicks"] - comparison["prior_clicks"])
            / comparison["prior_clicks"].replace(0, 1)
            * 100
        ).round(1)

        # Top gainers and losers
        gainers = comparison.nlargest(25, "impression_change_pct").reset_index()
        losers = comparison.nsmallest(25, "impression_change_pct").reset_index()

        gainers_display = gainers[["query", "prior_impressions", "current_impressions", "impression_change_pct", "click_change_pct"]].copy()
        gainers_display.columns = ["Query", "Prior Impressions", "Current Impressions", "Impression Change %", "Click Change %"]

        losers_display = losers[["query", "prior_impressions", "current_impressions", "impression_change_pct", "click_change_pct"]].copy()
        losers_display.columns = ["Query", "Prior Impressions", "Current Impressions", "Impression Change %", "Click Change %"]

        total_growing = len(comparison[comparison["impression_change_pct"] > 10])
        total_declining = len(comparison[comparison["impression_change_pct"] < -10])

        severity = Severity.MEDIUM if total_declining > total_growing else Severity.INSIGHT

        findings = [self.create_finding(
            task_id=53,
            severity=severity,
            summary=f"Year-over-year comparison for {len(comparison)} queries: {total_growing} growing (>10%), "
                    f"{total_declining} declining (>10%). "
                    f"{'More queries declining than growing — investigate competitive threats and content freshness.' if total_declining > total_growing else 'Healthy growth trajectory for most query topics.'}",
            affected_count=total_declining,
            data_table=losers_display,
            recommendations=[
                "Double down on gaining queries — create supporting content and strengthen internal linking.",
                "Investigate losing queries: has search intent changed? Are competitors outranking you?",
                "Refresh content for declining queries with updated information and expanded coverage.",
                "Check if declining queries are seasonal and expected to recover naturally.",
                "Reallocate resources from permanently declining topics to growing opportunities.",
            ],
        )]

        if not gainers_display.empty:
            findings.append(self.create_finding(
                task_id=53,
                severity=Severity.INSIGHT,
                summary=f"Top {len(gainers_display)} queries gaining impression share year-over-year.",
                data_table=gainers_display,
            ))

        return findings

    # -------------------------------------------------------------------
    # Task 54 — Post-Migration Performance Reconciliation
    # -------------------------------------------------------------------
    def task_54_post_migration_reconciliation(self) -> list[AuditFinding]:
        """Compare page performance across two halves of the data period.

        Flag pages that experienced sudden drops suggesting migration issues.
        """
        df = self.get_df("page_date_90d")

        if df.empty:
            return [self.create_finding(
                task_id=54,
                severity=Severity.INSIGHT,
                summary="No page date data available for post-migration reconciliation.",
            )]

        df["date"] = pd.to_datetime(df["date"])
        date_range = df["date"].max() - df["date"].min()
        if date_range.days < 30:
            return [self.create_finding(
                task_id=54,
                severity=Severity.INSIGHT,
                summary="Insufficient date range for migration analysis. Need at least 30 days of data.",
            )]

        midpoint = df["date"].min() + date_range / 2

        first_half = df[df["date"] < midpoint].groupby("page").agg(
            clicks_first=("clicks", "sum"),
            impressions_first=("impressions", "sum"),
        )
        second_half = df[df["date"] >= midpoint].groupby("page").agg(
            clicks_second=("clicks", "sum"),
            impressions_second=("impressions", "sum"),
        )

        # Pages in first half that disappeared or dropped drastically in second half
        comparison = first_half.join(second_half, how="left")
        comparison["clicks_second"] = comparison["clicks_second"].fillna(0)
        comparison["impressions_second"] = comparison["impressions_second"].fillna(0)

        # Require meaningful first-half traffic
        comparison = comparison[comparison["clicks_first"] >= 10]

        comparison["click_change_pct"] = (
            (comparison["clicks_second"] - comparison["clicks_first"])
            / comparison["clicks_first"]
            * 100
        )

        # Flag pages with sudden, severe drops (>50% decline)
        migration_issues = comparison[comparison["click_change_pct"] < -50].sort_values("click_change_pct")

        # Also find pages that appeared only in second half (new URLs, possibly from migration)
        second_only = df[df["date"] >= midpoint].groupby("page").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        )
        first_pages = set(first_half.index)
        new_pages = second_only[~second_only.index.isin(first_pages)]
        new_pages = new_pages[new_pages["clicks"] >= 5].sort_values("clicks", ascending=False)

        if migration_issues.empty and new_pages.empty:
            return [self.create_finding(
                task_id=54,
                severity=Severity.INSIGHT,
                summary="No migration-pattern disruptions detected. Page performance is consistent across the analysis period.",
            )]

        findings = []

        if not migration_issues.empty:
            display = migration_issues.reset_index().copy()
            display["click_change_pct"] = display["click_change_pct"].round(1)
            display = display[[
                "page", "clicks_first", "clicks_second", "click_change_pct",
                "impressions_first", "impressions_second"
            ]].copy()
            display.columns = [
                "Page URL", "Clicks (First Half)", "Clicks (Second Half)",
                "Click Change %", "Impressions (First Half)", "Impressions (Second Half)"
            ]

            total_lost = int(migration_issues["clicks_first"].sum() - migration_issues["clicks_second"].sum())

            severity = Severity.HIGH if len(migration_issues) > 10 else Severity.MEDIUM

            findings.append(self.create_finding(
                task_id=54,
                severity=severity,
                summary=f"Found {len(migration_issues)} pages with >50% click decline between first and second half of the period. "
                        f"This pattern may indicate migration issues, URL changes, or content removal. "
                        f"Estimated {total_lost:,} clicks lost.",
                affected_count=len(migration_issues),
                opportunity_value=f"~{total_lost:,} clicks to recover",
                data_table=display.head(50),
                recommendations=[
                    "Check if dropped pages have been redirected — missing or broken redirects cause traffic loss.",
                    "Verify that internal links still point to the correct URLs after any URL structure changes.",
                    "Check for 404 errors in Google Search Console for these dropped URLs.",
                    "Ensure canonical tags on new URLs properly resolve and aren't pointing to old URLs.",
                    "If pages were intentionally removed, ensure proper 301 redirects to the best alternative pages.",
                ],
            ))

        if not new_pages.empty:
            new_display = new_pages.reset_index().head(30).copy()
            new_display.columns = ["Page URL", "Clicks", "Impressions"]

            findings.append(self.create_finding(
                task_id=54,
                severity=Severity.INSIGHT,
                summary=f"{len(new_pages)} new pages appeared in the second half of the period. "
                        f"If a migration occurred, verify these are the correct replacement pages.",
                affected_count=len(new_pages),
                data_table=new_display,
            ))

        return findings

    # -------------------------------------------------------------------
    # Task 55 — Content Freshness Decay Rate Benchmarking
    # -------------------------------------------------------------------
    def task_55_content_freshness_decay(self) -> list[AuditFinding]:
        """Measure month-over-month impression decline for content at different ages.

        Based on when pages first appeared in the data.
        """
        df = self.get_df("page_date_365d")

        if df.empty:
            df = self.get_df("page_date_90d")

        if df.empty:
            return [self.create_finding(
                task_id=55,
                severity=Severity.INSIGHT,
                summary="No page date data available for content freshness decay analysis.",
            )]

        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")

        # Determine when each page first appeared in data (proxy for publish/index date)
        first_seen = df.groupby("page")["date"].min().reset_index()
        first_seen.columns = ["page", "first_seen"]
        first_seen["first_seen_month"] = first_seen["first_seen"].dt.to_period("M")

        # Calculate monthly impressions per page
        monthly = df.groupby(["page", "month"]).agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
        ).reset_index()

        monthly = monthly.merge(first_seen[["page", "first_seen_month"]], on="page")

        # Calculate content age in months
        monthly["age_months"] = (monthly["month"] - monthly["first_seen_month"]).apply(lambda x: x.n if hasattr(x, 'n') else 0)
        monthly = monthly[monthly["age_months"] >= 0]

        # Aggregate by age cohort
        age_cohort = monthly.groupby("age_months").agg(
            pages=("page", "nunique"),
            avg_impressions=("impressions", "mean"),
            total_impressions=("impressions", "sum"),
        ).reset_index()

        if len(age_cohort) < 2:
            return [self.create_finding(
                task_id=55,
                severity=Severity.INSIGHT,
                summary="Insufficient data to measure content freshness decay. Need at least 2 months of data.",
            )]

        age_cohort["avg_impressions"] = age_cohort["avg_impressions"].round(1)
        age_cohort = age_cohort.sort_values("age_months")

        # Calculate decay rate (month-over-month change)
        age_cohort["mom_change_pct"] = age_cohort["avg_impressions"].pct_change() * 100
        age_cohort["mom_change_pct"] = age_cohort["mom_change_pct"].round(1)

        display = age_cohort.copy()
        display.columns = ["Content Age (Months)", "Active Pages", "Avg Monthly Impressions", "Total Impressions", "MoM Change %"]

        # Find the steepest decay point
        decay_rows = age_cohort[age_cohort["mom_change_pct"] < 0]
        if not decay_rows.empty:
            worst_decay_month = decay_rows.loc[decay_rows["mom_change_pct"].idxmin()]
            severity = Severity.MEDIUM if worst_decay_month["mom_change_pct"] < -20 else Severity.LOW
            decay_note = f"Steepest decay occurs at month {int(worst_decay_month['age_months'])} ({worst_decay_month['mom_change_pct']:.1f}% drop)."
        else:
            severity = Severity.INSIGHT
            decay_note = "No significant month-over-month decay detected."

        # Calculate average decay for content older than 3 months
        older_content = age_cohort[age_cohort["age_months"] > 3]
        avg_decay = older_content["mom_change_pct"].mean() if not older_content.empty else 0

        chart_config = {
            "type": "line",
            "title": "Average Impressions by Content Age",
            "x": "Content Age (Months)",
            "y": "Avg Monthly Impressions",
        }

        return [self.create_finding(
            task_id=55,
            severity=severity,
            summary=f"Content freshness analysis across {len(age_cohort)} month cohorts. {decay_note} "
                    f"Average monthly decay rate for content >3 months old: {avg_decay:.1f}%. "
                    f"{'Content decays rapidly — implement a refresh schedule for older pages.' if avg_decay < -10 else 'Decay rate is within normal range.'}",
            affected_count=len(first_seen),
            data_table=display,
            chart_config=chart_config,
            recommendations=[
                "Establish a content refresh calendar — prioritize pages showing the steepest decay.",
                "Update outdated statistics, examples, and references in aging content.",
                "Add new sections covering recent developments in the topic.",
                "Republish refreshed content with updated publication dates (if factually updated).",
                "Interlink new content to older pages to pass fresh authority signals.",
                "Monitor which content types decay fastest to inform future content strategy.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 56 — Query Impression Share Trend for Core Topics
    # -------------------------------------------------------------------
    def task_56_query_impression_share(self) -> list[AuditFinding]:
        """Track total impressions for top query clusters over time.

        Show if core topics are gaining or losing visibility.
        """
        df = self.get_df("query_date_365d")

        if df.empty:
            df = self.get_df("page_date_90d")
            if df.empty:
                return [self.create_finding(
                    task_id=56,
                    severity=Severity.INSIGHT,
                    summary="No query date data available for impression share trend analysis.",
                )]
            # Fall back with less resolution
            return [self.create_finding(
                task_id=56,
                severity=Severity.INSIGHT,
                summary="Only page-level data available. Query-level date data is needed for impression share trending.",
            )]

        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")

        # Identify top query clusters by extracting the first meaningful word(s)
        # Group queries by their primary keyword (first 1-2 words)
        total_by_query = df.groupby("query")["impressions"].sum()
        top_queries = total_by_query.nlargest(200).index.tolist()

        # Simple clustering: group by first word for broad topic clusters
        df_top = df[df["query"].isin(top_queries)].copy()
        df_top["topic_word"] = df_top["query"].str.split().str[0].str.lower()

        # Get the most common topic words as cluster representatives
        topic_counts = df_top.groupby("topic_word")["impressions"].sum()
        top_topics = topic_counts.nlargest(15).index.tolist()

        if not top_topics:
            return [self.create_finding(
                task_id=56,
                severity=Severity.INSIGHT,
                summary="Could not identify meaningful query clusters for impression share analysis.",
            )]

        df_topics = df_top[df_top["topic_word"].isin(top_topics)].copy()

        # Monthly impression share by topic
        monthly_topics = df_topics.groupby(["topic_word", "month"]).agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            queries=("query", "nunique"),
        ).reset_index()

        # Calculate trend for each topic (first quarter vs last quarter of available data)
        months_sorted = sorted(monthly_topics["month"].unique())
        if len(months_sorted) < 3:
            return [self.create_finding(
                task_id=56,
                severity=Severity.INSIGHT,
                summary="Need at least 3 months of data for meaningful impression share trending.",
            )]

        quarter_size = max(1, len(months_sorted) // 4)
        early_months = set(months_sorted[:quarter_size])
        late_months = set(months_sorted[-quarter_size:])

        topic_trends = []
        for topic in top_topics:
            topic_data = monthly_topics[monthly_topics["topic_word"] == topic]

            early = topic_data[topic_data["month"].isin(early_months)]["impressions"].sum()
            late = topic_data[topic_data["month"].isin(late_months)]["impressions"].sum()

            if early > 0:
                change_pct = ((late - early) / early) * 100
            elif late > 0:
                change_pct = 100.0
            else:
                change_pct = 0.0

            total_impressions = int(topic_data["impressions"].sum())
            total_clicks = int(topic_data["clicks"].sum())
            query_count = int(topic_data["queries"].max())

            topic_trends.append({
                "Topic": topic,
                "Queries": query_count,
                "Total Impressions": total_impressions,
                "Total Clicks": total_clicks,
                "Early Period Impressions": int(early),
                "Late Period Impressions": int(late),
                "Change %": round(change_pct, 1),
            })

        trends_df = pd.DataFrame(topic_trends).sort_values("Change %")

        growing = [t for t in topic_trends if t["Change %"] > 10]
        declining = [t for t in topic_trends if t["Change %"] < -10]

        severity = Severity.MEDIUM if len(declining) > len(growing) else Severity.INSIGHT

        chart_config = {
            "type": "line",
            "title": "Impression Share Trends by Topic Cluster",
            "x": "month",
            "y": "impressions",
            "color": "topic_word",
        }

        return [self.create_finding(
            task_id=56,
            severity=severity,
            summary=f"Tracked impression share for {len(top_topics)} core topic clusters. "
                    f"{len(growing)} topics growing, {len(declining)} declining, "
                    f"{len(top_topics) - len(growing) - len(declining)} stable. "
                    f"{'More topics declining than growing — assess competitive landscape and content investment priorities.' if len(declining) > len(growing) else 'Healthy trend direction for most core topics.'}",
            affected_count=len(declining),
            data_table=trends_df,
            chart_config=chart_config,
            recommendations=[
                "Invest in growing topics — create more supporting content and build topical authority.",
                "Investigate declining topics: check competitor activity, SERP feature changes, and search intent evolution.",
                "For stable topics, look for opportunities to capture additional long-tail queries.",
                "Align content calendar with topic trend data — prioritize topics with positive momentum.",
                "Review declining topics for possible content consolidation or strategic abandonment.",
                "Cross-reference topic trends with business revenue data to prioritize commercial topics.",
            ],
        )]
