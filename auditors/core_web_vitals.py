"""Group 8: Core Web Vitals & Experience (Tasks 48-51).

Analyzes CWV regression detection, poor-CWV pages prioritized by traffic,
INP bottlenecks, and mobile vs desktop CWV disparity.
"""

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


# CWV thresholds (Google's published thresholds)
LCP_GOOD = 2500       # ms
LCP_POOR = 4000       # ms
INP_GOOD = 200        # ms
INP_POOR = 500        # ms
CLS_GOOD = 0.1
CLS_POOR = 0.25


class CoreWebVitalsAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        48: "task_48_cwv_regression_detection",
        49: "task_49_poor_cwv_by_traffic",
        50: "task_50_inp_bottleneck",
        51: "task_51_mobile_desktop_cwv_disparity",
    }

    def _get_pagespeed_df(self) -> pd.DataFrame:
        """Convert pagespeed store data to a DataFrame for analysis."""
        pagespeed = self.store.get("pagespeed")
        if not pagespeed:
            return pd.DataFrame()

        rows = []
        for url, data in pagespeed.items():
            if not isinstance(data, dict):
                continue
            row = {"url": url}
            for device in ["mobile", "desktop"]:
                device_data = data.get(device, {})
                if isinstance(device_data, dict):
                    row[f"{device}_lcp"] = device_data.get("lcp")
                    row[f"{device}_inp"] = device_data.get("inp")
                    row[f"{device}_cls"] = device_data.get("cls")
                    row[f"{device}_performance_score"] = device_data.get("performance_score")
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    @staticmethod
    def _classify_cwv(value, good_threshold, poor_threshold) -> str:
        """Classify a CWV metric as Good, Needs Improvement, or Poor."""
        if value is None:
            return "Unknown"
        if value <= good_threshold:
            return "Good"
        elif value <= poor_threshold:
            return "Needs Improvement"
        else:
            return "Poor"

    # -------------------------------------------------------------------
    # Task 48 — CWV Regression Detection Post-Deployment
    # -------------------------------------------------------------------
    def task_48_cwv_regression_detection(self) -> list[AuditFinding]:
        """Correlate CWV scores with traffic trends. Flag pages where poor CWV coincides with traffic drops."""
        pagespeed_df = self._get_pagespeed_df()
        page_date_df = self.get_df("page_date_90d")

        if pagespeed_df.empty:
            return [self.create_finding(
                task_id=48,
                severity=Severity.INSIGHT,
                summary="PageSpeed data is not available. Run PageSpeed Insights tests to enable CWV regression detection.",
                recommendations=[
                    "Collect PageSpeed data for your top traffic pages using the PageSpeed Insights API.",
                    "Focus on pages that have experienced recent traffic changes.",
                ],
            )]

        if page_date_df.empty:
            return [self.create_finding(
                task_id=48,
                severity=Severity.INSIGHT,
                summary="Page date data is not available. Both PageSpeed and traffic trend data are needed for regression analysis.",
            )]

        # Calculate traffic trend per page (first half vs second half)
        page_date_df["date"] = pd.to_datetime(page_date_df["date"])
        date_range = page_date_df["date"].max() - page_date_df["date"].min()

        if date_range.days < 30:
            return [self.create_finding(
                task_id=48,
                severity=Severity.INSIGHT,
                summary="Insufficient date range for CWV regression analysis. Need at least 30 days of data.",
            )]

        midpoint = page_date_df["date"].min() + date_range / 2

        first_half = page_date_df[page_date_df["date"] < midpoint].groupby("page").agg(
            clicks_first=("clicks", "sum"),
        )
        second_half = page_date_df[page_date_df["date"] >= midpoint].groupby("page").agg(
            clicks_second=("clicks", "sum"),
        )
        traffic_trend = first_half.join(second_half, how="inner")
        traffic_trend = traffic_trend[traffic_trend["clicks_first"] >= 5]
        traffic_trend["click_change_pct"] = (
            (traffic_trend["clicks_second"] - traffic_trend["clicks_first"])
            / traffic_trend["clicks_first"]
            * 100
        )

        # Join with pagespeed data
        traffic_trend = traffic_trend.reset_index()
        merged = traffic_trend.merge(pagespeed_df, left_on="page", right_on="url", how="inner")

        if merged.empty:
            return [self.create_finding(
                task_id=48,
                severity=Severity.INSIGHT,
                summary="No overlap between PageSpeed-tested URLs and pages with traffic trend data. "
                        "Ensure PageSpeed tests cover your top traffic pages.",
            )]

        # Flag pages with traffic decline AND poor CWV
        declining = merged[merged["click_change_pct"] < -20].copy()
        if declining.empty:
            return [self.create_finding(
                task_id=48,
                severity=Severity.INSIGHT,
                summary="No pages show both traffic decline and poor CWV scores. "
                        "Traffic trends and Core Web Vitals appear healthy for tested pages.",
            )]

        # Check if declining pages have poor CWV
        poor_cwv_declining = []
        for _, row in declining.iterrows():
            issues = []
            if row.get("mobile_lcp") and row["mobile_lcp"] > LCP_POOR:
                issues.append(f"LCP: {row['mobile_lcp']:.0f}ms")
            if row.get("mobile_inp") and row["mobile_inp"] > INP_POOR:
                issues.append(f"INP: {row['mobile_inp']:.0f}ms")
            if row.get("mobile_cls") and row["mobile_cls"] > CLS_POOR:
                issues.append(f"CLS: {row['mobile_cls']:.3f}")
            if issues:
                poor_cwv_declining.append({
                    "Page URL": row["page"],
                    "Click Change %": round(row["click_change_pct"], 1),
                    "Clicks (First Half)": int(row["clicks_first"]),
                    "Clicks (Second Half)": int(row["clicks_second"]),
                    "CWV Issues (Mobile)": ", ".join(issues),
                    "Perf Score": row.get("mobile_performance_score", "N/A"),
                })

        if not poor_cwv_declining:
            return [self.create_finding(
                task_id=48,
                severity=Severity.INSIGHT,
                summary=f"{len(declining)} pages show traffic decline, but none have critically poor CWV scores. "
                        f"Traffic drops are likely caused by other factors (content, competition, algorithm).",
            )]

        display = pd.DataFrame(poor_cwv_declining).sort_values("Click Change %")

        total_lost = int(
            display["Clicks (First Half)"].sum() - display["Clicks (Second Half)"].sum()
        )

        severity = Severity.HIGH if len(display) > 5 else Severity.MEDIUM

        return [self.create_finding(
            task_id=48,
            severity=severity,
            summary=f"Found {len(display)} pages with both traffic decline (>20%) and poor Core Web Vitals. "
                    f"These pages lost approximately {total_lost:,} clicks — CWV issues may be contributing to ranking drops.",
            affected_count=len(display),
            opportunity_value=f"~{total_lost:,} clicks potentially recoverable",
            data_table=display.head(30),
            recommendations=[
                "Fix CWV issues on declining-traffic pages as a priority — these have the clearest ROI.",
                "Address LCP by optimizing images, reducing server response time, and minimizing render-blocking resources.",
                "Fix INP by reducing JavaScript execution time, breaking up long tasks, and deferring non-critical scripts.",
                "Improve CLS by setting explicit width/height on images/ads and avoiding dynamic content injection above the fold.",
                "Re-test with PageSpeed Insights after fixes and monitor traffic recovery over 4-6 weeks.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 49 — Poor CWV URLs Prioritized by Traffic Value
    # -------------------------------------------------------------------
    def task_49_poor_cwv_by_traffic(self) -> list[AuditFinding]:
        """Prioritize CWV fixes by traffic value. Rank poor-CWV URLs by their click volume."""
        pagespeed_df = self._get_pagespeed_df()
        page_df = self.get_df("page_90d")

        if pagespeed_df.empty:
            return [self.create_finding(
                task_id=49,
                severity=Severity.INSIGHT,
                summary="PageSpeed data is not available. Run PageSpeed Insights tests to prioritize CWV fixes by traffic.",
                recommendations=[
                    "Test your highest-traffic pages with PageSpeed Insights API.",
                    "Focus on pages generating the most clicks and conversions.",
                ],
            )]

        # Identify pages with poor CWV (using mobile metrics primarily)
        poor_pages = []
        for _, row in pagespeed_df.iterrows():
            issues = []
            lcp = row.get("mobile_lcp")
            inp = row.get("mobile_inp")
            cls_val = row.get("mobile_cls")

            if lcp is not None and lcp > LCP_GOOD:
                issues.append(("LCP", f"{lcp:.0f}ms", self._classify_cwv(lcp, LCP_GOOD, LCP_POOR)))
            if inp is not None and inp > INP_GOOD:
                issues.append(("INP", f"{inp:.0f}ms", self._classify_cwv(inp, INP_GOOD, INP_POOR)))
            if cls_val is not None and cls_val > CLS_GOOD:
                issues.append(("CLS", f"{cls_val:.3f}", self._classify_cwv(cls_val, CLS_GOOD, CLS_POOR)))

            if issues:
                poor_pages.append({
                    "url": row["url"],
                    "issues": issues,
                    "issue_summary": "; ".join(f"{i[0]}: {i[1]} ({i[2]})" for i in issues),
                    "performance_score": row.get("mobile_performance_score"),
                    "mobile_lcp": lcp,
                    "mobile_inp": inp,
                    "mobile_cls": cls_val,
                })

        if not poor_pages:
            return [self.create_finding(
                task_id=49,
                severity=Severity.INSIGHT,
                summary="All tested pages pass Core Web Vitals thresholds. No CWV fixes needed.",
            )]

        poor_df = pd.DataFrame(poor_pages)

        # Join with traffic data
        if not page_df.empty:
            merged = poor_df.merge(
                page_df[["page", "clicks", "impressions"]],
                left_on="url",
                right_on="page",
                how="left",
            )
            merged["clicks"] = merged["clicks"].fillna(0).astype(int)
            merged["impressions"] = merged["impressions"].fillna(0).astype(int)
            merged = merged.sort_values("clicks", ascending=False)
        else:
            merged = poor_df.copy()
            merged["clicks"] = 0
            merged["impressions"] = 0

        display = merged[["url", "clicks", "impressions", "issue_summary", "performance_score"]].head(50).copy()
        display.columns = ["Page URL", "Clicks (90d)", "Impressions (90d)", "CWV Issues", "Perf Score"]

        total_affected_clicks = int(merged["clicks"].sum())
        poor_count = len(merged)

        severity = Severity.HIGH if total_affected_clicks > 500 else Severity.MEDIUM if total_affected_clicks > 100 else Severity.LOW

        return [self.create_finding(
            task_id=49,
            severity=severity,
            summary=f"{poor_count} pages have failing Core Web Vitals, collectively receiving {total_affected_clicks:,} clicks. "
                    f"Fixing the top pages by traffic will have the greatest impact on user experience and rankings.",
            affected_count=poor_count,
            opportunity_value=f"{total_affected_clicks:,} clicks on poor-CWV pages",
            data_table=display,
            recommendations=[
                "Fix the highest-traffic poor-CWV pages first for maximum impact.",
                "Group pages by common issues (e.g., all pages with slow LCP) for batch fixes.",
                "Address LCP: optimize images (WebP, lazy loading), preload critical resources, improve TTFB.",
                "Address INP: minimize main-thread JavaScript, use web workers, defer non-essential scripts.",
                "Address CLS: reserve space for ads/embeds, use CSS aspect-ratio, avoid late-loading content shifts.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 50 — INP Bottleneck Page Identification
    # -------------------------------------------------------------------
    def task_50_inp_bottleneck(self) -> list[AuditFinding]:
        """Find pages with poor INP scores (>200ms). These harm conversion-stage pages."""
        pagespeed_df = self._get_pagespeed_df()

        if pagespeed_df.empty:
            return [self.create_finding(
                task_id=50,
                severity=Severity.INSIGHT,
                summary="PageSpeed data is not available. Run PageSpeed Insights tests to identify INP bottlenecks.",
                recommendations=[
                    "Test interactive pages (forms, search, checkout, filters) with PageSpeed Insights.",
                    "INP (Interaction to Next Paint) measures responsiveness to user input.",
                ],
            )]

        # Filter pages with INP data
        inp_pages = pagespeed_df[pagespeed_df["mobile_inp"].notna()].copy()

        if inp_pages.empty:
            return [self.create_finding(
                task_id=50,
                severity=Severity.INSIGHT,
                summary="No INP data available in PageSpeed results. INP requires real-user data (CrUX) "
                        "or lab measurements from PageSpeed Insights.",
            )]

        inp_pages["inp_status"] = inp_pages["mobile_inp"].apply(
            lambda x: self._classify_cwv(x, INP_GOOD, INP_POOR)
        )

        poor_inp = inp_pages[inp_pages["mobile_inp"] > INP_GOOD].sort_values("mobile_inp", ascending=False)

        if poor_inp.empty:
            return [self.create_finding(
                task_id=50,
                severity=Severity.INSIGHT,
                summary=f"All {len(inp_pages)} tested pages have good INP scores (<=200ms). "
                        f"Interactivity responsiveness is healthy.",
            )]

        # Join with traffic data for prioritization
        page_df = self.get_df("page_90d")
        if not page_df.empty:
            poor_inp = poor_inp.merge(
                page_df[["page", "clicks", "impressions"]],
                left_on="url",
                right_on="page",
                how="left",
            )
            poor_inp["clicks"] = poor_inp["clicks"].fillna(0).astype(int)
            poor_inp = poor_inp.sort_values("clicks", ascending=False)
        else:
            poor_inp["clicks"] = 0

        display = poor_inp[["url", "mobile_inp", "inp_status", "clicks"]].head(50).copy()
        display["mobile_inp"] = display["mobile_inp"].round(0).astype(int)
        display.columns = ["Page URL", "INP (ms)", "Status", "Clicks (90d)"]

        critical_count = len(poor_inp[poor_inp["mobile_inp"] > INP_POOR])
        needs_improvement_count = len(poor_inp) - critical_count

        severity = Severity.HIGH if critical_count > 3 else Severity.MEDIUM

        return [self.create_finding(
            task_id=50,
            severity=severity,
            summary=f"Found {len(poor_inp)} pages with INP exceeding 200ms ({critical_count} poor, "
                    f"{needs_improvement_count} needs improvement). Slow interactivity frustrates users "
                    f"and hurts conversion rates, especially on interactive pages like forms and product listings.",
            affected_count=len(poor_inp),
            data_table=display,
            recommendations=[
                "Audit JavaScript execution on the worst INP pages — heavy scripts block the main thread.",
                "Break up long tasks (>50ms) into smaller chunks using requestIdleCallback or scheduler.yield().",
                "Defer or lazy-load non-critical JavaScript (analytics, chat widgets, social embeds).",
                "Reduce DOM size — large DOMs slow down event handling and style recalculation.",
                "Use Chrome DevTools Performance panel to identify specific interaction bottlenecks.",
                "Consider using web workers for computationally intensive operations.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 51 — Mobile vs Desktop CWV Disparity
    # -------------------------------------------------------------------
    def task_51_mobile_desktop_cwv_disparity(self) -> list[AuditFinding]:
        """Find pages passing CWV on desktop but failing on mobile."""
        pagespeed_df = self._get_pagespeed_df()

        if pagespeed_df.empty:
            return [self.create_finding(
                task_id=51,
                severity=Severity.INSIGHT,
                summary="PageSpeed data is not available. Run PageSpeed Insights tests for both mobile and desktop "
                        "to detect CWV disparity.",
                recommendations=[
                    "Test pages on both mobile and desktop with PageSpeed Insights.",
                    "Mobile CWV matters more due to mobile-first indexing.",
                ],
            )]

        # Check each CWV metric for mobile-fail/desktop-pass pattern
        disparity_rows = []
        for _, row in pagespeed_df.iterrows():
            mobile_issues = []
            desktop_ok = []

            # LCP check
            m_lcp = row.get("mobile_lcp")
            d_lcp = row.get("desktop_lcp")
            if m_lcp is not None and d_lcp is not None:
                if m_lcp > LCP_GOOD and d_lcp <= LCP_GOOD:
                    mobile_issues.append(f"LCP: mobile {m_lcp:.0f}ms vs desktop {d_lcp:.0f}ms")
                    desktop_ok.append("LCP")

            # INP check
            m_inp = row.get("mobile_inp")
            d_inp = row.get("desktop_inp")
            if m_inp is not None and d_inp is not None:
                if m_inp > INP_GOOD and d_inp <= INP_GOOD:
                    mobile_issues.append(f"INP: mobile {m_inp:.0f}ms vs desktop {d_inp:.0f}ms")
                    desktop_ok.append("INP")

            # CLS check
            m_cls = row.get("mobile_cls")
            d_cls = row.get("desktop_cls")
            if m_cls is not None and d_cls is not None:
                if m_cls > CLS_GOOD and d_cls <= CLS_GOOD:
                    mobile_issues.append(f"CLS: mobile {m_cls:.3f} vs desktop {d_cls:.3f}")
                    desktop_ok.append("CLS")

            if mobile_issues:
                disparity_rows.append({
                    "Page URL": row["url"],
                    "Mobile Perf Score": row.get("mobile_performance_score", "N/A"),
                    "Desktop Perf Score": row.get("desktop_performance_score", "N/A"),
                    "Failing on Mobile Only": "; ".join(mobile_issues),
                    "Metrics Passing Desktop": ", ".join(desktop_ok),
                })

        if not disparity_rows:
            return [self.create_finding(
                task_id=51,
                severity=Severity.INSIGHT,
                summary="No mobile vs desktop CWV disparity detected. Pages perform consistently across both device types, "
                        "or fail/pass on both equally.",
            )]

        display = pd.DataFrame(disparity_rows)

        # Join with traffic for context
        page_df = self.get_df("page_90d")
        if not page_df.empty:
            display = display.merge(
                page_df[["page", "clicks"]],
                left_on="Page URL",
                right_on="page",
                how="left",
            )
            display["clicks"] = display["clicks"].fillna(0).astype(int)
            display = display.drop(columns=["page"], errors="ignore")
            display = display.rename(columns={"clicks": "Clicks (90d)"})
            display = display.sort_values("Clicks (90d)", ascending=False)

        severity = Severity.HIGH if len(display) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=51,
            severity=severity,
            summary=f"Found {len(display)} pages passing CWV on desktop but failing on mobile. "
                    f"Since Google uses mobile-first indexing, mobile CWV failures directly impact rankings "
                    f"even if desktop scores look healthy.",
            affected_count=len(display),
            data_table=display.head(50),
            recommendations=[
                "Prioritize mobile CWV fixes — desktop scores are misleading if mobile fails.",
                "Common mobile-only LCP issues: unoptimized images, slow mobile networks, render-blocking resources.",
                "Common mobile-only INP issues: heavy JavaScript on limited mobile CPUs.",
                "Common mobile-only CLS issues: ads/images without dimensions that shift more on narrow viewports.",
                "Test fixes using Chrome DevTools mobile emulation with CPU/network throttling enabled.",
                "Consider implementing responsive images (srcset) to serve appropriately sized images per device.",
            ],
        )]
