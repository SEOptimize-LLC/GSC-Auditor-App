"""In-session data cache backed by Streamlit session_state."""

from typing import Any, Optional

import pandas as pd
import streamlit as st


STORE_KEY = "_gsc_data_store"


class DataStore:
    """Manages cached GSC data in Streamlit session state."""

    def __init__(self):
        if STORE_KEY not in st.session_state:
            st.session_state[STORE_KEY] = {}

    @property
    def _store(self) -> dict[str, Any]:
        return st.session_state[STORE_KEY]

    def set(self, shape_name: str, data: pd.DataFrame | dict | list) -> None:
        """Store data for a given shape name."""
        self._store[shape_name] = data

    def get(self, shape_name: str) -> Optional[pd.DataFrame | dict | list]:
        """Retrieve data for a given shape name, or None if not fetched."""
        return self._store.get(shape_name)

    def has(self, shape_name: str) -> bool:
        """Check if a shape has been fetched."""
        return shape_name in self._store

    def get_df(self, shape_name: str) -> pd.DataFrame:
        """Retrieve data as a DataFrame. Returns empty DataFrame if missing."""
        data = self.get(shape_name)
        if data is None or not isinstance(data, pd.DataFrame):
            return pd.DataFrame()
        return data

    def clear(self) -> None:
        """Clear all cached data."""
        st.session_state[STORE_KEY] = {}

    def clear_shape(self, shape_name: str) -> None:
        """Remove a specific shape from the cache."""
        self._store.pop(shape_name, None)

    @property
    def fetched_shapes(self) -> list[str]:
        """List all shape names that have been fetched."""
        return list(self._store.keys())

    @property
    def memory_usage_mb(self) -> float:
        """Estimate memory usage of all cached DataFrames."""
        total = 0
        for data in self._store.values():
            if isinstance(data, pd.DataFrame):
                total += data.memory_usage(deep=True).sum()
        return total / (1024 * 1024)
