"""
AI-QMS — Regulatory Storage Module
===================================

Manages storage of regulatory crawl results and user region preference config.
- RegulatoryConfigManager: reads/writes data/regulatory_config.md
- RegulatoryResultStore: saves/loads crawl results as JSON + individual Markdown files
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ============================================================
# Configuration Manager (data/regulatory_config.md)
# ============================================================

_CONFIG_PATH = Path("data/regulatory_config.md")
_RESULTS_PATH = Path("data/regulatory_crawl_results.json")
_UPDATES_DIR = Path("data/regulatory_updates")


class RegulatoryConfigManager:
    """Manages user region preferences stored as a Markdown file."""

    def __init__(self, config_path: Path = _CONFIG_PATH):
        self.config_path = config_path

    def has_config(self) -> bool:
        """Check if config file exists."""
        return self.config_path.exists()

    def load_config(self) -> dict:
        """Read and parse the config markdown file.

        Returns:
            dict with keys:
                'last_updated': str (ISO timestamp)
                'selected_regions': list[str]
                'excluded_regions': list[str]
                'notes': str
        """
        if not self.has_config():
            return {
                "last_updated": None,
                "selected_regions": [],
                "excluded_regions": [],
                "notes": "",
            }

        try:
            content = self.config_path.read_text(encoding="utf-8")
        except Exception:
            return {
                "last_updated": None,
                "selected_regions": [],
                "excluded_regions": [],
                "notes": "",
            }

        selected = []
        excluded = []
        last_updated = None
        notes = ""

        # Parse last updated
        ts_match = re.search(r"##\s*上次更新時間\s*\n\s*(.+)", content)
        if ts_match:
            last_updated = ts_match.group(1).strip()

        # Parse region checkboxes
        for match in re.finditer(r"-\s*\[([ xX])\]\s*(.+)", content):
            checked = match.group(1).lower() == "x"
            region_name = match.group(2).strip()
            if checked:
                selected.append(region_name)
            else:
                excluded.append(region_name)

        # Parse notes
        notes_match = re.search(r"##\s*備註\s*\n(.+?)(?:\n##|\Z)", content, re.DOTALL)
        if notes_match:
            notes = notes_match.group(1).strip()

        return {
            "last_updated": last_updated,
            "selected_regions": selected,
            "excluded_regions": excluded,
            "notes": notes,
        }

    def save_config(self, config: dict) -> None:
        """Write config dict back to markdown file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        selected = config.get("selected_regions", [])
        excluded = config.get("excluded_regions", [])
        notes = config.get("notes", "")
        timestamp = datetime.now(timezone.utc).isoformat()

        lines = [
            "# 法規搜尋偏好設定",
            "",
            "## 上次更新時間",
            timestamp,
            "",
            "## 搜尋地區",
        ]

        for region in selected:
            lines.append(f"- [x] {region}")
        for region in excluded:
            lines.append(f"- [ ] {region}")

        lines.append("")
        lines.append("## 備註")
        lines.append(notes if notes else "用戶自訂的偏好設定")
        lines.append("")

        self.config_path.write_text("\n".join(lines), encoding="utf-8")

    def get_selected_regions(self) -> list:
        """Return list of selected region names."""
        config = self.load_config()
        return config["selected_regions"]

    def get_excluded_regions(self) -> list:
        """Return list of excluded region names."""
        config = self.load_config()
        return config["excluded_regions"]

    def update_regions(self, selected: list, excluded: list, notes: str = "") -> None:
        """Update region selections and save."""
        config = {
            "selected_regions": selected,
            "excluded_regions": excluded,
            "notes": notes,
        }
        self.save_config(config)

    def get_all_regions_with_status(self, available_regions: list) -> list:
        """Return all regions with their checked/unchecked status.

        Args:
            available_regions: list of all available region names from crawler

        Returns:
            list of dicts: [{"region": str, "selected": bool}]
        """
        config = self.load_config()
        selected_set = set(config["selected_regions"])
        excluded_set = set(config["excluded_regions"])

        result = []
        for region in available_regions:
            if region in excluded_set:
                result.append({"region": region, "selected": False})
            elif region in selected_set:
                result.append({"region": region, "selected": True})
            else:
                # New region not in config — default to selected
                result.append({"region": region, "selected": True})
        return result


# ============================================================
# Result Store (JSON + Markdown files)
# ============================================================


class RegulatoryResultStore:
    """Saves and loads regulatory crawl results."""

    def __init__(
        self,
        results_path: Path = _RESULTS_PATH,
        updates_dir: Path = _UPDATES_DIR,
    ):
        self.results_path = results_path
        self.updates_dir = updates_dir
        self.updates_dir.mkdir(parents=True, exist_ok=True)

    def save_crawl_results(self, crawl_data: dict) -> str:
        """Save full crawl results to JSON.

        Args:
            crawl_data: dict with 'results' and 'summary' keys

        Returns:
            filepath string
        """
        self.results_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
            "results": crawl_data.get("results", []),
            "summary": crawl_data.get("summary", {}),
        }

        self.results_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return str(self.results_path)

    def load_last_results(self) -> Optional[dict]:
        """Load most recent crawl results from JSON.

        Returns:
            dict or None if no results exist
        """
        if not self.results_path.exists():
            return None
        try:
            content = self.results_path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception:
            return None

    def save_crawl_markdown(self, region: str, agency: str, content: str) -> str:
        """Save individual crawl result as markdown file.

        Args:
            region: region name
            agency: agency code
            content: markdown content

        Returns:
            filepath string
        """
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize names for filename
        safe_region = re.sub(r"[^\w\-]", "_", region)
        safe_agency = re.sub(r"[^\w\-]", "_", agency)
        filename = f"{safe_region}_{safe_agency}_{timestamp}.md"
        filepath = self.updates_dir / filename

        header = f"# {region} — {agency}\n爬取時間: {timestamp}\n\n---\n\n"
        filepath.write_text(header + content, encoding="utf-8")
        return str(filepath)

    def get_crawl_history(self) -> list:
        """List all previous crawl summaries.

        Returns:
            list of dicts with 'timestamp', 'total_sites', 'success_count', etc.
        """
        data = self.load_last_results()
        if data is None:
            return []
        return [
            {
                "timestamp": data.get("crawl_timestamp", ""),
                "total_sites": data.get("summary", {}).get("total_sites", 0),
                "success_count": data.get("summary", {}).get("success_count", 0),
                "failed_count": data.get("summary", {}).get("failed_count", 0),
                "regions": data.get("summary", {}).get("regions_covered", []),
            }
        ]

    def get_latest_by_region(self, region: str) -> list:
        """Get latest crawl results for a specific region.

        Args:
            region: region name

        Returns:
            list of result dicts for that region
        """
        data = self.load_last_results()
        if data is None:
            return []
        return [r for r in data.get("results", []) if r.get("region", "") == region]


# ============================================================
# Module-level convenience functions (singletons)
# ============================================================

_config_instance: Optional[RegulatoryConfigManager] = None
_store_instance: Optional[RegulatoryResultStore] = None


def get_regulatory_config() -> RegulatoryConfigManager:
    """Get or create singleton config manager."""
    global _config_instance
    if _config_instance is None:
        _config_instance = RegulatoryConfigManager()
    return _config_instance


def get_regulatory_store() -> RegulatoryResultStore:
    """Get or create singleton result store."""
    global _store_instance
    if _store_instance is None:
        _store_instance = RegulatoryResultStore()
    return _store_instance
