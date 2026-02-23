def format_number(n: int | float) -> str:
    """Format a number with comma separators."""
    if isinstance(n, float):
        if n == int(n):
            return f"{int(n):,}"
        return f"{n:,.2f}"
    return f"{n:,}"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a float as a percentage string."""
    return f"{value:.{decimals}f}%"


def format_position(pos: float) -> str:
    """Format an average position value."""
    return f"{pos:.1f}"


def severity_badge_md(severity_value: str) -> str:
    """Return a markdown-formatted severity badge."""
    labels = {
        "critical": "🔴 CRITICAL",
        "high": "🟠 HIGH",
        "medium": "🟡 MEDIUM",
        "low": "🔵 LOW",
        "insight": "⚪ INSIGHT",
    }
    return labels.get(severity_value, severity_value.upper())


def truncate_url(url: str, max_length: int = 80) -> str:
    """Truncate a URL for display purposes."""
    if len(url) <= max_length:
        return url
    return url[: max_length - 3] + "..."
