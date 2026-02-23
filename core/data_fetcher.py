"""Smart data fetching orchestrator.

Determines which GSC API calls are needed based on selected tasks,
fetches each unique data shape once, and stores results in DataStore.
"""

import logging
import time
from typing import Optional

import pandas as pd
import streamlit as st

from core.data_store import DataStore
from core.gsc_client import GSCClient
from models.gsc_data import (
    SHAPES,
    TASKS_NEEDING_PAGESPEED,
    TASKS_NEEDING_SITEMAPS,
    TASKS_NEEDING_URL_INSPECTION,
    get_required_shapes,
    needs_pagespeed,
    needs_sitemaps,
    needs_url_inspection,
)
from utils.date_utils import get_date_range

logger = logging.getLogger(__name__)


class DataFetcher:
    """Orchestrates all GSC data fetching based on selected audit tasks."""

    def __init__(
        self,
        client: GSCClient,
        store: DataStore,
        site_url: str,
    ):
        self.client = client
        self.store = store
        self.site_url = site_url

    def fetch_for_tasks(
        self,
        task_ids: list[int],
        progress_callback=None,
    ) -> None:
        """Fetch all data shapes required by the given task IDs.

        Args:
            task_ids: List of audit task IDs to fetch data for.
            progress_callback: Optional callable(current, total, message).
        """
        required = get_required_shapes(task_ids)
        shapes_to_fetch = [s for s in required if not self.store.has(SHAPES[s].name)]

        needs_inspection = needs_url_inspection(task_ids) and not self.store.has("url_inspection")
        needs_sitemap = needs_sitemaps(task_ids) and not self.store.has("sitemaps")
        needs_psi = needs_pagespeed(task_ids) and not self.store.has("pagespeed")

        total_steps = len(shapes_to_fetch) + int(needs_inspection) + int(needs_sitemap) + int(needs_psi)
        current_step = 0

        def _progress(msg: str):
            nonlocal current_step
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, msg)

        for shape_key in shapes_to_fetch:
            shape = SHAPES[shape_key]
            start_date, end_date = get_date_range(shape.days)
            logger.info(f"Fetching shape {shape_key}: {shape.description}")

            try:
                df = self.client.query_search_analytics_all(
                    site_url=self.site_url,
                    start_date=start_date,
                    end_date=end_date,
                    dimensions=list(shape.dimensions),
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch shape {shape_key} "
                    f"({shape.description}): {e}"
                )
                df = pd.DataFrame(
                    columns=list(shape.dimensions)
                    + ["clicks", "impressions", "ctr", "position"]
                )
            self.store.set(shape.name, df)
            _progress(f"Fetched {shape.description} ({len(df):,} rows)")

        if needs_sitemap:
            self._fetch_sitemaps()
            _progress("Fetched sitemap data")

        if needs_inspection:
            self._fetch_url_inspections(progress_callback=progress_callback)
            _progress("Fetched URL inspection data")

        if needs_psi:
            self._fetch_pagespeed()
            _progress("Fetched PageSpeed data")

    def _fetch_sitemaps(self) -> None:
        """Fetch sitemap data from GSC."""
        try:
            sitemaps = self.client.list_sitemaps(self.site_url)
            self.store.set("sitemaps", sitemaps)
        except Exception as e:
            logger.error(f"Failed to fetch sitemaps: {e}")
            self.store.set("sitemaps", [])

    def _fetch_url_inspections(self, progress_callback=None) -> None:
        """Fetch URL inspection data for a sample of URLs.

        Samples URLs from the page-level data that have zero or very low
        impressions, as these are most likely to have indexing issues.
        Limited to 500 URLs to stay within API quotas.
        """
        page_df = self.store.get_df("page_90d")
        if page_df.empty:
            self.store.set("url_inspection", {})
            return

        low_impression_pages = page_df[page_df["impressions"] <= 5]
        sample_urls = low_impression_pages["page"].head(500).tolist()

        if not sample_urls:
            sample_urls = page_df["page"].head(100).tolist()

        results = self.client.inspect_urls_batch(
            site_url=self.site_url,
            urls=sample_urls,
        )
        self.store.set("url_inspection", results)

    def _fetch_pagespeed(self) -> None:
        """Fetch PageSpeed Insights data for top pages by traffic.

        Limited to top 50 pages to stay within rate limits.
        """
        try:
            from core.pagespeed_client import PageSpeedClient

            page_df = self.store.get_df("page_90d")
            if page_df.empty:
                self.store.set("pagespeed", {})
                return

            top_pages = (
                page_df.sort_values("clicks", ascending=False)
                .head(50)["page"]
                .tolist()
            )

            psi_client = PageSpeedClient(
                api_key=st.secrets.get("pagespeed", {}).get("api_key", "")
            )
            results = psi_client.analyze_urls(top_pages)
            self.store.set("pagespeed", results)
        except Exception as e:
            logger.error(f"Failed to fetch PageSpeed data: {e}")
            self.store.set("pagespeed", {})
