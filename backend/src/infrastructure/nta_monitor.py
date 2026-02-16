"""NTA (National Tax Agency) law change monitor.

Skeleton implementation. Checks a target URL for content changes
by comparing content hashes.
"""
import hashlib

import httpx

from src.logging_config import get_logger

logger = get_logger(__name__)

# Target pages to monitor (expand as needed)
NTA_TARGETS = [
    {
        "name": "income_tax_rates",
        "url": "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        "description": "Income tax rate table",
    },
    {
        "name": "salary_deduction",
        "url": "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm",
        "description": "Salary income deduction table",
    },
]


class NtaMonitor:
    """Monitors NTA website pages for content changes."""

    def __init__(self):
        self._known_hashes: dict[str, str] = {}

    async def check_for_changes(self) -> list[dict]:
        """Check all target pages for changes.

        Returns:
            List of dicts with 'name', 'url', and 'new_hash' for pages that changed.
        """
        changes = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for target in NTA_TARGETS:
                try:
                    response = await client.get(target["url"])
                    response.raise_for_status()
                    content_hash = hashlib.sha256(response.content).hexdigest()

                    previous_hash = self._known_hashes.get(target["name"])
                    if previous_hash is not None and previous_hash != content_hash:
                        logger.warning(
                            "NTA change detected: %s (%s)", target["name"], target["description"]
                        )
                        changes.append({
                            "name": target["name"],
                            "url": target["url"],
                            "previous_hash": previous_hash,
                            "new_hash": content_hash,
                        })

                    self._known_hashes[target["name"]] = content_hash

                except Exception as e:
                    logger.error("Failed to check NTA page '%s': %s", target["name"], e)

        return changes

    def get_known_hashes(self) -> dict[str, str]:
        """Return current known hashes for all monitored pages."""
        return dict(self._known_hashes)
