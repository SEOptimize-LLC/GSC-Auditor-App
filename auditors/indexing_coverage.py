"""Group 7: Indexing & Coverage Diagnostics (Tasks 43-47).

Analyzes index bloat, crawled-not-indexed patterns, sitemap reconciliation,
canonical overrides, and redirect chain click loss.
"""

import re
from urllib.parse import urlparse

import pandas as pd

from auditors.base_auditor import BaseGSCAuditor
from models.audit_finding import AuditFinding, Severity


class IndexingCoverageAuditor(BaseGSCAuditor):

    TASK_REGISTRY = {
        43: "task_43_index_bloat_ratio",
        44: "task_44_crawled_not_indexed",
        45: "task_45_sitemap_reconciliation",
        46: "task_46_canonical_overrides",
        47: "task_47_redirect_chain_loss",
    }

    @staticmethod
    def _extract_directory(url: str) -> str:
        """Extract the first-level directory path from a URL for clustering."""
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                return "/" + path_parts[0] + "/"
            return "/"
        except Exception:
            return "/"

    @staticmethod
    def _extract_url_template(url: str) -> str:
        """Extract a URL template by replacing IDs/slugs with placeholders."""
        try:
            parsed = urlparse(url)
            path = parsed.path
            # Replace numeric segments
            path = re.sub(r'/\d+', '/{id}', path)
            # Replace UUID-like segments
            path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path)
            # Replace very long slug segments (likely dynamic)
            path = re.sub(r'/[^/]{60,}', '/{long-slug}', path)
            return f"{parsed.scheme}://{parsed.netloc}{path}"
        except Exception:
            return url

    # -------------------------------------------------------------------
    # Task 43 — Index Bloat Ratio Calculation
    # -------------------------------------------------------------------
    def task_43_index_bloat_ratio(self) -> list[AuditFinding]:
        """Calculate ratio of performing pages (impressions > 0) vs total indexed."""
        df = self.get_df("page_90d")

        if df.empty:
            return [self.create_finding(
                task_id=43,
                severity=Severity.INSIGHT,
                summary="No page data available for index bloat analysis.",
            )]

        total_pages = len(df)
        performing = df[df["impressions"] > 0]
        performing_count = len(performing)
        non_performing = total_pages - performing_count

        if total_pages == 0:
            return [self.create_finding(
                task_id=43,
                severity=Severity.INSIGHT,
                summary="No indexed pages found in the dataset.",
            )]

        bloat_ratio = (non_performing / total_pages) * 100

        # Breakdown by directory
        df["directory"] = df["page"].apply(self._extract_directory)
        dir_summary = df.groupby("directory").agg(
            total=("page", "count"),
            performing=("impressions", lambda x: (x > 0).sum()),
        ).reset_index()
        dir_summary["non_performing"] = dir_summary["total"] - dir_summary["performing"]
        dir_summary["bloat_pct"] = (dir_summary["non_performing"] / dir_summary["total"] * 100).round(1)
        dir_summary = dir_summary.sort_values("non_performing", ascending=False)
        dir_summary.columns = ["Directory", "Total Pages", "Performing", "Non-Performing", "Bloat %"]

        summary_table = pd.DataFrame({
            "Metric": ["Total Pages in GSC", "Pages with Impressions", "Pages with Zero Impressions", "Bloat Ratio"],
            "Value": [f"{total_pages:,}", f"{performing_count:,}", f"{non_performing:,}", f"{bloat_ratio:.1f}%"],
        })

        if bloat_ratio > 60:
            severity = Severity.CRITICAL
        elif bloat_ratio > 40:
            severity = Severity.HIGH
        elif bloat_ratio > 20:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        findings = [self.create_finding(
            task_id=43,
            severity=severity,
            summary=f"Index bloat ratio is {bloat_ratio:.1f}% — {non_performing:,} of {total_pages:,} indexed pages "
                    f"generated zero impressions in 90 days. "
                    f"{'This is critically high and wastes significant crawl budget.' if bloat_ratio > 40 else 'Monitor and address the largest non-performing directories.'}",
            affected_count=non_performing,
            data_table=summary_table,
            recommendations=[
                "Audit non-performing pages: noindex thin/duplicate content, consolidate similar pages, or remove truly worthless URLs.",
                "Focus on directories with the highest bloat ratios first.",
                "Use robots.txt or meta noindex to prevent crawling/indexing of low-value URL patterns.",
                "Submit updated sitemaps containing only pages worth indexing.",
                "Monitor index bloat monthly to track improvement.",
            ],
        )]

        if not dir_summary.empty:
            findings.append(self.create_finding(
                task_id=43,
                severity=Severity.INSIGHT,
                summary="Index bloat breakdown by directory — highest-bloat directories should be prioritized.",
                data_table=dir_summary.head(30),
            ))

        return findings

    # -------------------------------------------------------------------
    # Task 44 — Crawled — Not Indexed Pattern Clustering
    # -------------------------------------------------------------------
    def task_44_crawled_not_indexed(self) -> list[AuditFinding]:
        """From URL inspection data, cluster unindexed URLs by URL template/directory pattern."""
        url_inspection = self.store.get("url_inspection")

        if not url_inspection:
            return [self.create_finding(
                task_id=44,
                severity=Severity.INSIGHT,
                summary="URL inspection data is not available. Run URL inspections via the GSC API to enable "
                        "crawled-not-indexed pattern clustering.",
                recommendations=[
                    "Use the GSC URL Inspection API to check indexing status of key pages.",
                    "Prioritize inspecting pages from your sitemap that aren't generating impressions.",
                ],
            )]

        # Parse inspection results
        rows = []
        for url, result in url_inspection.items():
            if isinstance(result, dict):
                coverage_state = result.get("coverageState", result.get("indexStatusResult", {}).get("coverageState", ""))
                verdict = result.get("verdict", result.get("indexStatusResult", {}).get("verdict", ""))
                rows.append({
                    "url": url,
                    "coverage_state": str(coverage_state),
                    "verdict": str(verdict),
                })

        if not rows:
            return [self.create_finding(
                task_id=44,
                severity=Severity.INSIGHT,
                summary="URL inspection data is empty or in an unexpected format.",
            )]

        inspection_df = pd.DataFrame(rows)

        # Find crawled-not-indexed pages
        not_indexed_patterns = [
            "crawled - currently not indexed",
            "discovered - currently not indexed",
            "excluded",
        ]
        not_indexed = inspection_df[
            inspection_df["coverage_state"].str.lower().str.contains(
                "|".join(not_indexed_patterns), na=False
            )
        ].copy()

        if not_indexed.empty:
            return [self.create_finding(
                task_id=44,
                severity=Severity.INSIGHT,
                summary=f"All {len(inspection_df)} inspected URLs appear to be indexed. No crawled-not-indexed issues detected.",
            )]

        # Cluster by directory and URL template
        not_indexed["directory"] = not_indexed["url"].apply(self._extract_directory)
        not_indexed["template"] = not_indexed["url"].apply(self._extract_url_template)

        dir_clusters = not_indexed.groupby("directory").agg(
            count=("url", "count"),
            sample_url=("url", "first"),
            coverage_states=("coverage_state", lambda x: ", ".join(x.unique())),
        ).sort_values("count", ascending=False).reset_index()
        dir_clusters.columns = ["Directory", "Unindexed URLs", "Sample URL", "Coverage States"]

        severity = Severity.HIGH if len(not_indexed) > 50 else Severity.MEDIUM

        return [self.create_finding(
            task_id=44,
            severity=severity,
            summary=f"Found {len(not_indexed)} crawled-but-not-indexed URLs across {len(dir_clusters)} directory patterns. "
                    f"These pages consume crawl budget without contributing to organic visibility.",
            affected_count=len(not_indexed),
            data_table=dir_clusters.head(30),
            recommendations=[
                "Investigate the largest clusters first — pattern-level fixes (noindex, robots.txt) are most efficient.",
                "For 'Discovered — currently not indexed', improve page quality and internal linking.",
                "For 'Crawled — currently not indexed', Google chose not to index — content may be thin or duplicate.",
                "Consolidate similar unindexed pages into fewer, more comprehensive pages.",
                "Remove or noindex URL patterns that generate many unindexed pages (faceted navigation, parameter URLs).",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 45 — Sitemap vs Indexed Pages Reconciliation
    # -------------------------------------------------------------------
    def task_45_sitemap_reconciliation(self) -> list[AuditFinding]:
        """Compare sitemap URLs vs pages with impressions. Find gaps."""
        sitemaps = self.store.get("sitemaps")
        df = self.get_df("page_90d")

        if sitemaps is None:
            return [self.create_finding(
                task_id=45,
                severity=Severity.INSIGHT,
                summary="Sitemap data is not available. Connect your sitemaps via the GSC API to enable reconciliation.",
                recommendations=[
                    "Submit your XML sitemap in Google Search Console.",
                    "Ensure your sitemap is referenced in robots.txt.",
                ],
            )]

        if not sitemaps:
            return [self.create_finding(
                task_id=45,
                severity=Severity.MEDIUM,
                summary="No sitemaps found in Google Search Console. Sitemaps help Google discover and index your pages efficiently.",
                recommendations=[
                    "Create and submit an XML sitemap listing all indexable pages.",
                    "Include only canonical, 200-status pages in your sitemap.",
                    "Reference the sitemap in your robots.txt file.",
                ],
            )]

        # Extract sitemap info
        sitemap_summary = []
        all_sitemap_urls: set[str] = set()
        for sm in sitemaps:
            if isinstance(sm, dict):
                sitemap_path = sm.get("path", sm.get("url", "Unknown"))
                submitted = sm.get("contents", [])
                # Some sitemap formats include URL lists; others just metadata
                if isinstance(submitted, list):
                    for item in submitted:
                        if isinstance(item, dict) and "url" in item:
                            all_sitemap_urls.add(item["url"])
                sitemap_summary.append({
                    "Sitemap": sitemap_path,
                    "Type": sm.get("type", "N/A"),
                    "Submitted": sm.get("submitted", "N/A"),
                    "Last Downloaded": sm.get("lastDownloaded", "N/A"),
                    "Warnings": sm.get("warnings", 0),
                    "Errors": sm.get("errors", 0),
                })

        sitemap_display = pd.DataFrame(sitemap_summary) if sitemap_summary else pd.DataFrame()

        if df.empty:
            return [self.create_finding(
                task_id=45,
                severity=Severity.INSIGHT,
                summary=f"Found {len(sitemaps)} sitemaps but no page impression data to reconcile against.",
                data_table=sitemap_display if not sitemap_display.empty else None,
            )]

        gsc_pages = set(df["page"].unique())

        # Pages in GSC data but not in sitemap (if we have sitemap URL details)
        if all_sitemap_urls:
            in_gsc_not_sitemap = gsc_pages - all_sitemap_urls
            in_sitemap_not_gsc = all_sitemap_urls - gsc_pages

            gap_summary = pd.DataFrame({
                "Metric": [
                    "Pages in sitemaps",
                    "Pages with GSC impressions",
                    "In GSC but not in sitemap",
                    "In sitemap but no impressions",
                ],
                "Count": [
                    f"{len(all_sitemap_urls):,}",
                    f"{len(gsc_pages):,}",
                    f"{len(in_gsc_not_sitemap):,}",
                    f"{len(in_sitemap_not_gsc):,}",
                ],
            })

            total_gaps = len(in_gsc_not_sitemap) + len(in_sitemap_not_gsc)
            severity = Severity.HIGH if total_gaps > 100 else Severity.MEDIUM if total_gaps > 20 else Severity.LOW

            return [self.create_finding(
                task_id=45,
                severity=severity,
                summary=f"Sitemap reconciliation: {len(in_gsc_not_sitemap):,} pages get impressions but aren't in your sitemap; "
                        f"{len(in_sitemap_not_gsc):,} sitemap URLs get no impressions. "
                        f"Keep your sitemap aligned with your actual performing pages.",
                affected_count=total_gaps,
                data_table=gap_summary,
                recommendations=[
                    "Add high-performing pages missing from the sitemap.",
                    "Investigate sitemap-listed pages with zero impressions — they may be blocked, redirected, or low quality.",
                    "Remove non-indexable URLs (redirects, noindex, 404s) from your sitemap.",
                    "Automate sitemap generation to keep it current with site changes.",
                    "Monitor sitemap errors in Google Search Console regularly.",
                ],
            )]

        # If we don't have detailed URLs from sitemaps, report what we know
        return [self.create_finding(
            task_id=45,
            severity=Severity.INSIGHT,
            summary=f"Found {len(sitemaps)} sitemaps and {len(gsc_pages):,} pages with GSC impressions. "
                    f"Detailed URL-level sitemap data is not available for full reconciliation.",
            data_table=sitemap_display if not sitemap_display.empty else None,
            recommendations=[
                "Ensure all important pages are included in your XML sitemap.",
                "Cross-reference sitemap URLs with GSC Coverage report for detailed status.",
                "Remove non-canonical and non-indexable URLs from the sitemap.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 46 — Google-Overridden Canonical Audit
    # -------------------------------------------------------------------
    def task_46_canonical_overrides(self) -> list[AuditFinding]:
        """From URL inspection data, find pages where Google's canonical differs from user-declared."""
        url_inspection = self.store.get("url_inspection")

        if not url_inspection:
            return [self.create_finding(
                task_id=46,
                severity=Severity.INSIGHT,
                summary="URL inspection data is not available. Run URL inspections via the GSC API "
                        "to detect canonical overrides.",
                recommendations=[
                    "Use the GSC URL Inspection API to check canonical status of key pages.",
                    "Prioritize inspecting pages where you suspect canonical issues.",
                ],
            )]

        rows = []
        for url, result in url_inspection.items():
            if isinstance(result, dict):
                # Handle different response structures
                index_result = result.get("indexStatusResult", result)
                user_canonical = index_result.get("userCanonical", "")
                google_canonical = index_result.get("googleCanonical", "")
                if user_canonical and google_canonical and user_canonical != google_canonical:
                    rows.append({
                        "url": url,
                        "user_canonical": user_canonical,
                        "google_canonical": google_canonical,
                    })

        if not rows:
            return [self.create_finding(
                task_id=46,
                severity=Severity.INSIGHT,
                summary="No canonical overrides detected. Google is respecting your declared canonical URLs "
                        "for all inspected pages.",
            )]

        override_df = pd.DataFrame(rows)
        override_df.columns = ["Page URL", "Your Canonical", "Google's Canonical"]

        severity = Severity.HIGH if len(override_df) > 10 else Severity.MEDIUM

        return [self.create_finding(
            task_id=46,
            severity=severity,
            summary=f"Found {len(override_df)} pages where Google overrides your declared canonical URL. "
                    f"This means Google disagrees with your canonical signals and is choosing a different page to index.",
            affected_count=len(override_df),
            data_table=override_df.head(50),
            recommendations=[
                "Review each override: if Google's choice is better, update your canonical tags to match.",
                "If your canonical is correct, strengthen signals: internal links, sitemap inclusion, consistent self-referencing canonicals.",
                "Check for conflicting signals: multiple canonical tags, hreflang mismatches, or redirect loops.",
                "Ensure pages declared as canonical are accessible, non-redirecting, and return 200 status.",
                "Consolidate truly duplicate content rather than relying solely on canonical tags.",
            ],
        )]

    # -------------------------------------------------------------------
    # Task 47 — Redirect Chain Click Loss Assessment
    # -------------------------------------------------------------------
    def task_47_redirect_chain_loss(self) -> list[AuditFinding]:
        """From URL inspection data, find pages served via redirects that still get clicks."""
        url_inspection = self.store.get("url_inspection")
        df = self.get_df("page_90d")

        if not url_inspection:
            return [self.create_finding(
                task_id=47,
                severity=Severity.INSIGHT,
                summary="URL inspection data is not available. Run URL inspections via the GSC API "
                        "to detect redirect chain click loss.",
                recommendations=[
                    "Use the GSC URL Inspection API to check redirect status of pages with clicks.",
                ],
            )]

        # Find pages that are redirected
        redirected_urls = []
        for url, result in url_inspection.items():
            if isinstance(result, dict):
                index_result = result.get("indexStatusResult", result)
                page_fetch = result.get("pageFetchState", index_result.get("pageFetchState", ""))
                coverage_state = str(index_result.get("coverageState", ""))
                # Look for redirect indicators
                if any(kw in str(page_fetch).lower() for kw in ["redirect", "301", "302"]) or \
                   "redirect" in coverage_state.lower():
                    redirected_urls.append({
                        "url": url,
                        "fetch_state": str(page_fetch),
                        "coverage_state": coverage_state,
                    })

        if not redirected_urls:
            return [self.create_finding(
                task_id=47,
                severity=Severity.INSIGHT,
                summary="No redirected pages detected in URL inspection data. "
                        "Pages are being served directly without redirect chains.",
            )]

        redirect_df = pd.DataFrame(redirected_urls)

        # Cross-reference with pages that still get clicks
        if not df.empty:
            redirect_with_traffic = redirect_df.merge(
                df[["page", "clicks", "impressions"]],
                left_on="url",
                right_on="page",
                how="inner",
            )
            redirect_with_traffic = redirect_with_traffic[redirect_with_traffic["clicks"] > 0]

            if redirect_with_traffic.empty:
                return [self.create_finding(
                    task_id=47,
                    severity=Severity.LOW,
                    summary=f"Found {len(redirect_df)} redirected URLs, but none are generating clicks. "
                            f"The redirects are functioning but the old URLs are no longer receiving traffic.",
                    affected_count=len(redirect_df),
                    recommendations=[
                        "Update internal links pointing to redirected URLs to target the final destination directly.",
                        "Monitor for external backlinks still pointing to redirected URLs.",
                    ],
                )]

            display = redirect_with_traffic[["url", "fetch_state", "clicks", "impressions"]].copy()
            display = display.sort_values("clicks", ascending=False)
            display.columns = ["Redirected URL", "Fetch State", "Clicks", "Impressions"]

            total_redirect_clicks = int(display["Clicks"].sum())

            severity = Severity.MEDIUM if total_redirect_clicks > 100 else Severity.LOW

            return [self.create_finding(
                task_id=47,
                severity=severity,
                summary=f"Found {len(redirect_with_traffic)} redirected pages still generating {total_redirect_clicks:,} clicks. "
                        f"Each redirect adds latency and may lose PageRank equity. Update links to point directly to final URLs.",
                affected_count=len(redirect_with_traffic),
                opportunity_value=f"{total_redirect_clicks:,} clicks through redirect chains",
                data_table=display.head(50),
                recommendations=[
                    "Update internal links to point directly to the final destination URL, bypassing redirects.",
                    "Ask top referring sites to update their links to the new URLs.",
                    "Ensure redirect chains are no more than one hop (avoid chain: A -> B -> C).",
                    "Update sitemap to reference only final destination URLs.",
                    "Monitor for new redirect chains as site structure evolves.",
                ],
            )]

        # If no page traffic data, report what we found
        display = redirect_df.copy()
        display.columns = ["URL", "Fetch State", "Coverage State"]

        return [self.create_finding(
            task_id=47,
            severity=Severity.LOW,
            summary=f"Found {len(redirect_df)} redirected URLs in inspection data. "
                    f"No page traffic data available to assess click loss.",
            affected_count=len(redirect_df),
            data_table=display.head(50),
            recommendations=[
                "Update internal links to bypass redirect chains.",
                "Ensure redirect chains are resolved to a single hop.",
            ],
        )]
