"""Image URL collection helpers for listing exports."""

from __future__ import annotations

import re
from typing import Iterable


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def extract_first_number(value: str) -> int:
    """Return the first number in a filename or URL; unnumbered files sort last."""
    filename = value.rsplit("/", maxsplit=1)[-1]
    match = re.search(r"(\d+)", filename)
    return int(match.group(1)) if match else 999999


def collect_sorted_image_urls(blobs: Iterable, bucket_name: str) -> list[str]:
    """Build public GCS image URLs and sort them by the number in their file name."""
    image_urls = [
        f"https://storage.googleapis.com/{bucket_name}/{blob.name}"
        for blob in blobs
        if blob.name.lower().endswith(IMAGE_EXTENSIONS)
    ]
    return sorted(image_urls, key=extract_first_number)
