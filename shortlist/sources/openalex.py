from __future__ import annotations

import os
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .cache import Cache

BASE = "https://api.openalex.org"


class OpenAlex:
    def __init__(self, cache: Optional[Cache] = None):
        self.cache = cache or Cache()
        self.email = os.environ.get("OPENALEX_EMAIL")
        self.session = requests.Session()

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20))
    def _get(self, path: str, params: dict[str, Any]) -> dict:
        if self.email:
            params = {**params, "mailto": self.email}
        url = f"{BASE}/{path}?{urlencode(params)}"

        cached = self.cache.get(url)
        if cached is not None:
            return cached

        resp = self.session.get(url, timeout=30)
        if resp.status_code == 429:
            time.sleep(2)
            resp.raise_for_status()
        resp.raise_for_status()
        data = resp.json()
        self.cache.set(url, data)
        return data

    def works_by_topic_country(self,topic_id: str,country_codes: list[str],from_year: int,per_page: int = 200,max_pages: int = 3,) -> list[dict]:
        country_filter = "|".join(c.lower() for c in country_codes)
        results: list[dict] = []
        cursor = "*"
        for _ in range(max_pages):
            page = self._get(
                "works",
                {
                    "filter": (
                        f"topics.id:{topic_id},"
                        f"institutions.country_code:{country_filter},"
                        f"from_publication_date:{from_year}-01-01"
                    ),
                    "sort": "cited_by_count:desc",  # quality-bias the retrieval
                    "per_page": per_page,
                    "cursor": cursor,
                    "select": "id,title,publication_year,doi,authorships,topics,primary_location",
                },
            )
            batch = page.get("results", [])
            results.extend(batch)
            cursor = page.get("meta", {}).get("next_cursor")
            if not cursor or not batch:
                break
        return results

    def works_by_search_country(self, query: str, country_codes: list[str], from_year: int, per_page: int = 100, max_pages: int = 2) -> list[dict]:
        country_filter = "|".join(c.lower() for c in country_codes)
        results: list[dict] = []
        cursor = "*"
        for _ in range(max_pages):
            page = self._get(
                "works",
                {
                    "search": query,
                    "filter": (
                        f"institutions.country_code:{country_filter},"
                        f"from_publication_date:{from_year}-01-01"
                    ),
                    "sort": "relevance_score:desc",
                    "per_page": per_page,
                    "cursor": cursor,
                    "select": "id,title,publication_year,doi,authorships,topics,"
                              "primary_location,awards",
                },
            )
            batch = page.get("results", [])
            results.extend(batch)
            cursor = page.get("meta", {}).get("next_cursor")
            if not cursor or not batch:
                break
        return results

    def author(self, author_id: str) -> dict:
        aid = author_id.rsplit("/", 1)[-1]
        return self._get(
            f"authors/{aid}",
            {"select": "id,display_name,works_count,topics,affiliations," "summary_stats,counts_by_year,ids"},)

    def award(self, award_id: str) -> dict:
        gid = award_id.rsplit("/", 1)[-1]
        return self._get(f"awards/{gid}", {})
