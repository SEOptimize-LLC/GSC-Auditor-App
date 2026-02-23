"""PageSpeed Insights API client for Core Web Vitals data."""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

PSI_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedClient:
    """Client for the Google PageSpeed Insights API."""

    def __init__(self, api_key: str = "", delay_seconds: float = 1.5):
        self.api_key = api_key
        self.delay = delay_seconds

    def analyze_url(self, url: str, strategy: str = "mobile") -> dict[str, Any]:
        """Analyze a single URL and return CWV metrics."""
        params: dict[str, str] = {
            "url": url,
            "strategy": strategy,
            "category": "performance",
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            response = requests.get(PSI_API_URL, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            return self._extract_cwv(data, url, strategy)
        except Exception as e:
            logger.warning(f"PageSpeed analysis failed for {url}: {e}")
            return {"url": url, "strategy": strategy, "error": str(e)}

    def analyze_urls(
        self,
        urls: list[str],
        strategies: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Analyze multiple URLs with rate limiting.

        Returns a dict mapping URL to its CWV results.
        """
        if strategies is None:
            strategies = ["mobile", "desktop"]

        results: dict[str, dict[str, Any]] = {}
        for url in urls:
            url_results: dict[str, Any] = {"url": url}
            for strategy in strategies:
                result = self.analyze_url(url, strategy)
                url_results[strategy] = result
                time.sleep(self.delay)
            results[url] = url_results
        return results

    @staticmethod
    def _extract_cwv(data: dict, url: str, strategy: str) -> dict[str, Any]:
        """Extract Core Web Vitals metrics from PSI response."""
        result: dict[str, Any] = {"url": url, "strategy": strategy}

        loading = data.get("loadingExperience", {})
        metrics = loading.get("metrics", {})

        cwv_mapping = {
            "LARGEST_CONTENTFUL_PAINT_MS": "lcp",
            "INTERACTION_TO_NEXT_PAINT": "inp",
            "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
            "FIRST_CONTENTFUL_PAINT_MS": "fcp",
            "FIRST_INPUT_DELAY_MS": "fid",
        }

        for api_name, short_name in cwv_mapping.items():
            metric = metrics.get(api_name, {})
            if metric:
                result[short_name] = metric.get("percentile", None)
                result[f"{short_name}_category"] = metric.get("category", "UNKNOWN")

        result["overall_category"] = loading.get("overall_category", "UNKNOWN")

        lighthouse = data.get("lighthouseResult", {})
        result["performance_score"] = (
            lighthouse.get("categories", {})
            .get("performance", {})
            .get("score", None)
        )

        return result
