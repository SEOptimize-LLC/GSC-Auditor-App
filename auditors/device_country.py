"""Group 6: Device & Country Segmentation (Tasks 38-42).

Analyzes geographic demand gaps, mobile vs desktop position deltas,
hreflang validation, high-value country crawl, and tablet traffic.
"""

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


class DeviceCountryAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        38: "task_38_geographic_demand_gap",
        39: "task_39_mobile_desktop_position_delta",
        40: "task_40_hreflang_validation",
        41: "task_41_high_value_country_crawl",
        42: "task_42_tablet_assessment",
    }

    # -------------------------------------------------------------------
    # Task 38 — Geographic Demand vs Content Coverage Gap
    # -------------------------------------------------------------------
    def task_38_geographic_demand_gap(self) -> list[AuditFinding]:
        """Find countries with high impressions but disproportionately low CTR/clicks."""
        df = self.get_df("query_country_90d")

        if df.empty:
            return [self.create_finding(
                task_id=38,
                severity=Severity.INSIGHT,
                summary="No country-level query data available for geographic demand analysis.",
            )]

        country_summary = df.groupby("country").agg(
            queries=("query", "nunique"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        ).reset_index()

        country_summary["ctr"] = country_summary["clicks"] / country_summary["impressions"].replace(0, 1)
        country_summary = country_summary[country_summary["impressions"] >= 100]

        if country_summary.empty:
            return [self.create_finding(
                task_id=38,
                severity=Severity.INSIGHT,
                summary="No countries have sufficient impression volume (100+) for meaningful gap analysis.",
            )]

        # Calculate site-wide average CTR as benchmark
        overall_ctr = country_summary["clicks"].sum() / max(country_summary["impressions"].sum(), 1)

        # Flag countries where CTR is less than half the site average and impressions are significant
        country_summary["ctr_ratio"] = country_summary["ctr"] / max(overall_ctr, 0.001)
        gap_countries = country_summary[
            (country_summary["ctr_ratio"] < 0.5)
            & (country_summary["impressions"] >= country_summary["impressions"].quantile(0.25))
        ].sort_values("impressions", ascending=False)

        if gap_countries.empty:
            return [self.create_finding(
                task_id=38,
                severity=Severity.INSIGHT,
                summary="No significant geographic demand gaps detected. CTR is reasonably consistent across countries with meaningful traffic.",
            )]

        display = gap_countries.copy()
        display["ctr_pct"] = (display["ctr"] * 100).round(2)
        display["site_avg_ctr_pct"] = round(overall_ctr * 100, 2)
        display = display[["country", "queries", "impressions", "clicks", "ctr_pct", "site_avg_ctr_pct"]].copy()
        display.columns = ["Country", "Queries", "Impressions", "Clicks", "CTR %", "Site Avg CTR %"]

        total_missed_clicks = int(
            (gap_countries["impressions"] * overall_ctr - gap_countries["clicks"]).clip(lower=0).sum()
        )

        severity = Severity.HIGH if len(gap_countries) > 5 else Severity.MEDIUM

        return [self.create_finding(
            task_id=38,
            severity=severity,
            summary=f"Found {len(gap_countries)} countries with high impressions but CTR less than half the site average. "
                    f"These markets have demand but your content may not resonate locally. "
                    f"Estimated {total_missed_clicks:,} missed clicks.",
            affected_count=len(gap_countries),
            opportunity_value=f"~{total_missed_clicks:,} potential clicks with localized content",
            data_table=display.head(30),
            recommendations=[
                "Create or localize content for high-impression, low-CTR countries.",
                "Translate and culturally adapt titles and meta descriptions for target markets.",
                "Consider implementing hreflang tags for multi-language targeting.",
                "Analyze top queries in each gap country to understand local search intent.",
                "Evaluate whether ccTLD or subdirectory approaches are appropriate for priority markets.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 39 — Mobile vs Desktop Position Delta
    # -------------------------------------------------------------------
    def task_39_mobile_desktop_position_delta(self) -> list[AuditFinding]:
        """Compare mobile vs desktop average position for top pages. Flag 3+ position gaps."""
        df = self.get_df("page_device_90d")

        if df.empty:
            return [self.create_finding(
                task_id=39,
                severity=Severity.INSIGHT,
                summary="No device-level page data available for mobile vs desktop position analysis.",
            )]

        # Separate mobile and desktop
        mobile = df[df["device"].str.upper() == "MOBILE"].groupby("page").agg(
            mobile_clicks=("clicks", "sum"),
            mobile_impressions=("impressions", "sum"),
            mobile_position=("position", "mean"),
        )
        desktop = df[df["device"].str.upper() == "DESKTOP"].groupby("page").agg(
            desktop_clicks=("clicks", "sum"),
            desktop_impressions=("impressions", "sum"),
            desktop_position=("position", "mean"),
        )

        comparison = mobile.join(desktop, how="inner")
        # Require minimum impressions on both devices
        comparison = comparison[
            (comparison["mobile_impressions"] >= 50)
            & (comparison["desktop_impressions"] >= 50)
        ]

        if comparison.empty:
            return [self.create_finding(
                task_id=39,
                severity=Severity.INSIGHT,
                summary="Insufficient data for mobile vs desktop position comparison. "
                        "Need pages with 50+ impressions on both devices.",
            )]

        comparison["position_delta"] = comparison["mobile_position"] - comparison["desktop_position"]
        comparison["abs_delta"] = comparison["position_delta"].abs()

        # Flag pages with 3+ position gap
        flagged = comparison[comparison["abs_delta"] >= 3].sort_values("abs_delta", ascending=False)

        if flagged.empty:
            return [self.create_finding(
                task_id=39,
                severity=Severity.INSIGHT,
                summary="No significant mobile vs desktop position gaps detected. "
                        "Pages rank consistently across both device types (within 3 positions).",
            )]

        display = flagged.reset_index().copy()
        display["mobile_position"] = display["mobile_position"].round(1)
        display["desktop_position"] = display["desktop_position"].round(1)
        display["position_delta"] = display["position_delta"].round(1)
        display = display[[
            "page", "mobile_position", "desktop_position", "position_delta",
            "mobile_clicks", "desktop_clicks"
        ]].copy()
        display.columns = [
            "Page URL", "Mobile Position", "Desktop Position", "Delta",
            "Mobile Clicks", "Desktop Clicks"
        ]

        mobile_worse = len(flagged[flagged["position_delta"] > 0])
        desktop_worse = len(flagged[flagged["position_delta"] < 0])

        severity = Severity.HIGH if len(flagged) > 20 else Severity.MEDIUM

        return [self.create_finding(
            task_id=39,
            severity=severity,
            summary=f"Found {len(flagged)} pages with 3+ position gap between mobile and desktop. "
                    f"{mobile_worse} pages rank worse on mobile; {desktop_worse} rank worse on desktop. "
                    f"Mobile-first indexing means mobile performance directly impacts desktop rankings.",
            affected_count=len(flagged),
            data_table=display.head(50),
            recommendations=[
                "For pages ranking worse on mobile, check mobile usability issues (viewport, tap targets, font size).",
                "Run PageSpeed Insights for flagged pages — mobile-specific performance issues may cause ranking drops.",
                "Ensure content parity between mobile and desktop versions of all pages.",
                "Check for mobile interstitials or pop-ups that may trigger Google penalties.",
                "Prioritize fixing pages where mobile position is significantly worse, as mobile-first indexing prevails.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 40 — Hreflang Delivery Validation
    # -------------------------------------------------------------------
    def task_40_hreflang_validation(self) -> list[AuditFinding]:
        """Check if country-specific pages receive impressions in their target market. Flag cross-contamination."""
        page_country = self.get_df("page_country_90d")

        if page_country.empty:
            return [self.create_finding(
                task_id=40,
                severity=Severity.INSIGHT,
                summary="No country-level page data available for hreflang validation.",
            )]

        # Detect localized URL patterns: /en/, /de/, /fr/, /es/, etc. or subdomains like en.site.com
        locale_pattern = r'(?:/([a-z]{2})(?:-[a-z]{2})?/)|(?://([a-z]{2})\.[^/]+)'
        page_country["locale_match"] = page_country["page"].str.extract(locale_pattern, expand=False)[0]

        localized_pages = page_country[page_country["locale_match"].notna()].copy()

        if localized_pages.empty:
            return [self.create_finding(
                task_id=40,
                severity=Severity.INSIGHT,
                summary="No localized URL patterns detected (e.g., /en/, /de/, /fr/). "
                        "If your site targets multiple countries, consider implementing hreflang tags and localized URL structures.",
                recommendations=[
                    "Implement hreflang tags if targeting multiple languages or countries.",
                    "Use consistent URL structures for localized content (subdirectories or subdomains).",
                ],
            )]

        # Map common locale codes to expected countries (ISO 3166-1 alpha-3)
        locale_to_country = {
            "en": ["USA", "GBR", "AUS", "CAN", "NZL", "IRL", "ZAF"],
            "de": ["DEU", "AUT", "CHE"],
            "fr": ["FRA", "BEL", "CHE", "CAN"],
            "es": ["ESP", "MEX", "ARG", "COL", "CHL", "PER"],
            "pt": ["BRA", "PRT"],
            "it": ["ITA", "CHE"],
            "nl": ["NLD", "BEL"],
            "ja": ["JPN"],
            "ko": ["KOR"],
            "zh": ["CHN", "TWN", "HKG", "SGP"],
            "ru": ["RUS"],
            "ar": ["SAU", "ARE", "EGY"],
            "sv": ["SWE"],
            "da": ["DNK"],
            "no": ["NOR"],
            "fi": ["FIN"],
            "pl": ["POL"],
            "tr": ["TUR"],
        }

        cross_contamination = []
        for locale, expected_countries in locale_to_country.items():
            locale_pages = localized_pages[localized_pages["locale_match"] == locale]
            if locale_pages.empty:
                continue
            # Impressions from NON-target countries
            wrong_country = locale_pages[~locale_pages["country"].isin(expected_countries)]
            if not wrong_country.empty:
                wrong_agg = wrong_country.groupby(["page", "country"]).agg(
                    impressions=("impressions", "sum"),
                    clicks=("clicks", "sum"),
                ).reset_index()
                wrong_agg["target_locale"] = locale
                cross_contamination.append(wrong_agg)

        if not cross_contamination:
            return [self.create_finding(
                task_id=40,
                severity=Severity.INSIGHT,
                summary="No hreflang cross-contamination detected. Localized pages are primarily showing in their expected markets.",
            )]

        contamination_df = pd.concat(cross_contamination, ignore_index=True)
        contamination_df = contamination_df.sort_values("impressions", ascending=False)

        display = contamination_df[["page", "target_locale", "country", "impressions", "clicks"]].head(50).copy()
        display.columns = ["Page URL", "Target Locale", "Showing In Country", "Impressions", "Clicks"]

        total_misplaced = int(contamination_df["impressions"].sum())

        severity = Severity.MEDIUM if total_misplaced > 1000 else Severity.LOW

        return [self.create_finding(
            task_id=40,
            severity=severity,
            summary=f"Detected {len(contamination_df)} instances of hreflang cross-contamination — "
                    f"localized pages showing in non-target countries with {total_misplaced:,} impressions. "
                    f"This dilutes relevance and wastes crawl budget.",
            affected_count=len(contamination_df),
            opportunity_value=f"{total_misplaced:,} misplaced impressions",
            data_table=display,
            recommendations=[
                "Verify hreflang tags are correctly implemented with reciprocal references.",
                "Ensure x-default hreflang is set for the primary/fallback language version.",
                "Check that hreflang annotations are consistent across HTML tags, HTTP headers, and sitemaps.",
                "Use Google Search Console's International Targeting report to identify hreflang errors.",
                "Consider adding country-specific content signals (local addresses, phone numbers, currency).",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 41 — High-Value Country Crawl Budget Check
    # -------------------------------------------------------------------
    def task_41_high_value_country_crawl(self) -> list[AuditFinding]:
        """Identify countries generating high impressions relative to clicks. Investigate friction."""
        df = self.get_df("query_country_90d")

        if df.empty:
            return [self.create_finding(
                task_id=41,
                severity=Severity.INSIGHT,
                summary="No country-level query data available for high-value country analysis.",
            )]

        country_agg = df.groupby("country").agg(
            queries=("query", "nunique"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            avg_position=("position", "mean"),
        ).reset_index()

        country_agg["ctr"] = country_agg["clicks"] / country_agg["impressions"].replace(0, 1)
        country_agg = country_agg[country_agg["impressions"] >= 200]
        country_agg = country_agg.sort_values("impressions", ascending=False)

        if country_agg.empty:
            return [self.create_finding(
                task_id=41,
                severity=Severity.INSIGHT,
                summary="No countries with sufficient impression volume (200+) for analysis.",
            )]

        # Calculate impression-to-click ratio — high ratio = high friction
        country_agg["imp_per_click"] = (
            country_agg["impressions"] / country_agg["clicks"].replace(0, 1)
        ).round(1)

        # Flag countries with impressions-per-click ratio above the 75th percentile
        high_friction_threshold = country_agg["imp_per_click"].quantile(0.75)
        high_friction = country_agg[
            country_agg["imp_per_click"] >= high_friction_threshold
        ].sort_values("impressions", ascending=False)

        display = high_friction.copy()
        display["ctr_pct"] = (display["ctr"] * 100).round(2)
        display["avg_position"] = display["avg_position"].round(1)
        display = display[[
            "country", "queries", "impressions", "clicks", "ctr_pct", "avg_position", "imp_per_click"
        ]].copy()
        display.columns = [
            "Country", "Queries", "Impressions", "Clicks", "CTR %", "Avg Position", "Impressions per Click"
        ]

        potential_clicks = int(
            (high_friction["impressions"] * country_agg["ctr"].median() - high_friction["clicks"]).clip(lower=0).sum()
        )

        severity = Severity.MEDIUM if len(high_friction) > 3 else Severity.LOW

        return [self.create_finding(
            task_id=41,
            severity=severity,
            summary=f"Found {len(high_friction)} high-friction countries where impressions significantly exceed clicks. "
                    f"These markets show demand but users are not clicking through. "
                    f"Fixing friction could recover ~{potential_clicks:,} clicks.",
            affected_count=len(high_friction),
            opportunity_value=f"~{potential_clicks:,} potential clicks",
            data_table=display.head(20),
            recommendations=[
                "Analyze SERP appearance for top queries in high-friction countries — poor snippet quality may be the issue.",
                "Check if language mismatch is causing low CTR (English content showing in non-English markets).",
                "Evaluate whether content topics align with local market interests and terminology.",
                "Consider creating country-specific landing pages with localized messaging.",
                "Review title tag and meta description length — some languages require different character counts.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 42 — Tablet Traffic Viability Assessment
    # -------------------------------------------------------------------
    def task_42_tablet_assessment(self) -> list[AuditFinding]:
        """Analyze tablet-segmented traffic viability."""
        df = self.get_df("page_device_90d")

        if df.empty:
            return [self.create_finding(
                task_id=42,
                severity=Severity.INSIGHT,
                summary="No device-level page data available for tablet assessment.",
            )]

        # Separate device segments
        device_summary = df.groupby("device").agg(
            pages=("page", "nunique"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            avg_position=("position", "mean"),
        ).reset_index()

        device_summary["ctr"] = device_summary["clicks"] / device_summary["impressions"].replace(0, 1)
        device_summary["ctr_pct"] = (device_summary["ctr"] * 100).round(2)
        device_summary["avg_position"] = device_summary["avg_position"].round(1)

        tablet_data = device_summary[device_summary["device"].str.upper() == "TABLET"]

        if tablet_data.empty:
            return [self.create_finding(
                task_id=42,
                severity=Severity.INSIGHT,
                summary="No tablet traffic detected in the data. Tablet usage may be negligible for your audience.",
            )]

        total_clicks = int(device_summary["clicks"].sum())
        tablet_clicks = int(tablet_data["clicks"].sum())
        tablet_pct = (tablet_clicks / max(total_clicks, 1)) * 100

        # Full device comparison table
        display = device_summary[["device", "pages", "clicks", "impressions", "ctr_pct", "avg_position"]].copy()
        display.columns = ["Device", "Active Pages", "Clicks", "Impressions", "CTR %", "Avg Position"]

        # Find top tablet pages
        tablet_pages = df[df["device"].str.upper() == "TABLET"].copy()
        top_tablet = tablet_pages.groupby("page").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        ).sort_values("clicks", ascending=False).reset_index().head(20)
        top_tablet.columns = ["Page URL", "Tablet Clicks", "Tablet Impressions"]

        if tablet_pct < 5:
            severity = Severity.INSIGHT
            summary_text = (
                f"Tablet traffic accounts for only {tablet_pct:.1f}% of total clicks ({tablet_clicks:,} clicks). "
                f"Tablet-specific optimization is unlikely to yield significant returns."
            )
        elif tablet_pct < 15:
            severity = Severity.LOW
            summary_text = (
                f"Tablet traffic accounts for {tablet_pct:.1f}% of clicks ({tablet_clicks:,} clicks). "
                f"Moderate tablet usage warrants ensuring responsive design works well at tablet viewport sizes."
            )
        else:
            severity = Severity.MEDIUM
            summary_text = (
                f"Tablet traffic is significant at {tablet_pct:.1f}% of clicks ({tablet_clicks:,} clicks). "
                f"Ensure tablet-specific UX is optimized for this meaningful audience segment."
            )

        findings = [self.create_finding(
            task_id=42,
            severity=severity,
            summary=summary_text,
            affected_count=tablet_clicks,
            data_table=display,
            recommendations=[
                "Test your site at common tablet viewport sizes (768px-1024px) for layout issues.",
                "Ensure touch targets are appropriately sized for tablet interaction.",
                "Check that responsive images serve appropriate sizes for tablet screens.",
                "Monitor tablet-specific Core Web Vitals separately from mobile and desktop.",
                "If tablet traffic is minimal, focus optimization efforts on mobile and desktop instead.",
            ],
        )]

        if not top_tablet.empty:
            findings.append(self.create_finding(
                task_id=42,
                severity=Severity.INSIGHT,
                summary=f"Top {len(top_tablet)} pages by tablet clicks for targeted optimization.",
                data_table=top_tablet,
            ))

        return findings
