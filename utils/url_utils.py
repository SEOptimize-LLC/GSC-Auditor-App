from urllib.parse import urlparse, parse_qs


def is_parameterized(url: str) -> bool:
    """Check if a URL contains query parameters."""
    parsed = urlparse(url)
    return bool(parsed.query)


def get_url_path(url: str) -> str:
    """Extract the path from a URL, stripping scheme and domain."""
    parsed = urlparse(url)
    return parsed.path


def get_url_directory(url: str) -> str:
    """Extract the top-level directory from a URL path.

    Example: https://example.com/blog/post-1 -> /blog/
    """
    path = get_url_path(url)
    parts = [p for p in path.split("/") if p]
    if parts:
        return f"/{parts[0]}/"
    return "/"


def normalize_url(url: str) -> str:
    """Normalize a URL by removing trailing slashes and fragments."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc
