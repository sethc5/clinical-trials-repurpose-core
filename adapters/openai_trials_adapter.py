"""
openai_trials_adapter.py — OpenTrials / EU Clinical Trials Register adapter.

Covers EU CTR (https://www.clinicaltrialsregister.eu/) as a supplement
to ClinicalTrials.gov for European trials not registered in the US.

EU CTR does not have an official API — this adapter scrapes the public
search interface within rate limits, or uses data exports when available.

Alternative: ISRCTN registry (https://www.isrctn.com/api/query)
"""

from __future__ import annotations

import logging
import time
from typing import Generator

import requests

log = logging.getLogger(__name__)

EU_CTR_BASE = "https://www.clinicaltrialsregister.eu/ctr-search/rest/search"
ISRCTN_API = "https://www.isrctn.com/api/query"


class OpenTrialsAdapter:
    """
    Adapter for non-ClinicalTrials.gov registries:
      - EU Clinical Trials Register (EU-CTR)
      - ISRCTN registry
    """

    def __init__(self, request_delay: float = 1.0) -> None:
        self.delay = request_delay
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "repurposing-pipeline/0.1 (research use)"

    # ------------------------------------------------------------------
    # EU CTR
    # ------------------------------------------------------------------

    def search_euctr(
        self,
        drug_name: str | None = None,
        condition: str | None = None,
        page_size: int = 100,
    ) -> Generator[dict, None, None]:
        """Yield EU CTR trial records matching a query."""
        params: dict = {"pageSize": page_size, "page": 1}
        query_parts = []
        if drug_name:
            query_parts.append(drug_name)
        if condition:
            query_parts.append(condition)
        if query_parts:
            params["query"] = " ".join(query_parts)

        while True:
            try:
                resp = self.session.get(EU_CTR_BASE, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.error(f"EU CTR query failed: {e}")
                break

            trials = data.get("content", [])
            for trial in trials:
                yield self._parse_euctr_trial(trial)

            time.sleep(self.delay)

            if data.get("last", True) or not trials:
                break
            params["page"] += 1

    def _parse_euctr_trial(self, raw: dict) -> dict:
        return {
            "trial_id": raw.get("eudractNumber"),
            "title": raw.get("trialTitle"),
            "status": raw.get("trialStatus"),
            "phase": raw.get("trialPhase"),
            "start_date": raw.get("startDate"),
            "completion_date": raw.get("completionDate"),
            "sponsor": raw.get("sponsorName"),
            "source": "euctr",
        }

    # ------------------------------------------------------------------
    # ISRCTN
    # ------------------------------------------------------------------

    def search_isrctn(
        self,
        drug_name: str | None = None,
        condition: str | None = None,
        page_size: int = 100,
    ) -> Generator[dict, None, None]:
        """Yield ISRCTN trial records."""
        q_parts = []
        if drug_name:
            q_parts.append(f'intervention:"{drug_name}"')
        if condition:
            q_parts.append(f'condition:"{condition}"')

        params = {
            "q": " AND ".join(q_parts) if q_parts else "*:*",
            "page_size": page_size,
            "page": 1,
            "output_format": "json",
        }

        while True:
            try:
                resp = self.session.get(ISRCTN_API, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.error(f"ISRCTN query failed: {e}")
                break

            trials = data.get("items", [])
            for trial in trials:
                yield self._parse_isrctn_trial(trial)

            time.sleep(self.delay)
            if len(trials) < page_size:
                break
            params["page"] += 1

    def _parse_isrctn_trial(self, raw: dict) -> dict:
        return {
            "trial_id": raw.get("isrctn"),
            "title": raw.get("title"),
            "status": raw.get("overallStatus"),
            "phase": raw.get("phase"),
            "start_date": raw.get("startDate"),
            "completion_date": raw.get("studyCompletionDate"),
            "sponsor": raw.get("primarySponsor"),
            "source": "isrctn",
        }
