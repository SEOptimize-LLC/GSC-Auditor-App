"""Data shape definitions for GSC API queries.

Each shape defines a unique combination of dimensions and date range
that gets fetched once and shared across multiple audit tasks.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DataShape:
    name: str
    dimensions: tuple[str, ...]
    days: int
    description: str


SHAPES = {
    "A": DataShape("query_90d", ("query",), 90, "Query-level metrics"),
    "B": DataShape("page_90d", ("page",), 90, "Page-level metrics"),
    "C": DataShape("query_page_90d", ("query", "page"), 90, "Query-to-page mapping"),
    "D": DataShape("query_date_90d", ("query", "date"), 90, "Query trends (daily)"),
    "E": DataShape("page_date_90d", ("page", "date"), 90, "Page trends (daily)"),
    "F": DataShape("query_device_90d", ("query", "device"), 90, "Device-level query perf"),
    "G": DataShape("page_device_90d", ("page", "device"), 90, "Device-level page perf"),
    "H": DataShape("query_country_90d", ("query", "country"), 90, "Country-level query perf"),
    "I": DataShape("page_country_90d", ("page", "country"), 90, "Country-level page perf"),
    "J": DataShape("searchapp_90d", ("searchAppearance",), 90, "SERP feature metrics"),
    "K": DataShape("searchapp_90d", ("searchAppearance",), 90, "SERP feature metrics"),
    "L": DataShape("page_date_365d", ("page", "date"), 365, "Long-term page trends"),
    "M": DataShape("query_date_365d", ("query", "date"), 365, "Long-term query trends"),
}

TASK_SHAPES: dict[int, list[str]] = {
    1: ["A", "B", "C"],
    2: ["B"],
    3: ["E"],
    4: ["C"],
    5: ["A", "C"],
    6: ["A"],
    7: ["A"],
    8: ["A"],
    9: ["D"],
    10: ["A"],
    11: ["A"],
    12: ["C"],
    13: ["A"],
    14: ["A"],
    15: ["M"],
    16: ["A"],
    17: ["B"],
    18: ["B"],  # Also needs N (URL Inspection)
    19: ["E"],
    20: ["C"],
    21: ["C"],
    22: ["B"],
    23: ["C"],
    24: ["E"],
    25: ["K"],
    26: ["B"],  # Also needs N (URL Inspection)
    27: ["A"],
    28: ["A", "B"],
    29: ["F"],
    30: ["H"],
    31: ["J"],
    32: ["K"],
    33: ["J"],
    34: ["K"],
    35: ["D", "J"],
    36: ["K"],
    37: ["J"],
    38: ["H", "I"],
    39: ["G"],
    40: ["I"],  # Also needs N (URL Inspection)
    41: ["I"],
    42: ["G"],
    43: ["B"],  # Also needs O (Sitemaps)
    44: [],     # Needs N (URL Inspection) only
    45: ["B"],  # Also needs O (Sitemaps)
    46: [],     # Needs N (URL Inspection) only
    47: [],     # Needs N (URL Inspection) only
    48: ["E"],  # Also needs P (PageSpeed)
    49: ["B"],  # Also needs P (PageSpeed)
    50: [],     # Needs P (PageSpeed) only
    51: [],     # Needs P (PageSpeed) only
    52: ["L"],
    53: ["M"],
    54: ["L", "B"],
    55: ["E", "L"],
    56: ["M"],
}

TASKS_NEEDING_URL_INSPECTION = {18, 26, 40, 44, 46, 47}
TASKS_NEEDING_SITEMAPS = {43, 45}
TASKS_NEEDING_PAGESPEED = {48, 49, 50, 51}


def get_required_shapes(task_ids: list[int]) -> set[str]:
    shapes: set[str] = set()
    for tid in task_ids:
        shapes.update(TASK_SHAPES.get(tid, []))
    return shapes


def needs_url_inspection(task_ids: list[int]) -> bool:
    return bool(set(task_ids) & TASKS_NEEDING_URL_INSPECTION)


def needs_sitemaps(task_ids: list[int]) -> bool:
    return bool(set(task_ids) & TASKS_NEEDING_SITEMAPS)


def needs_pagespeed(task_ids: list[int]) -> bool:
    return bool(set(task_ids) & TASKS_NEEDING_PAGESPEED)
