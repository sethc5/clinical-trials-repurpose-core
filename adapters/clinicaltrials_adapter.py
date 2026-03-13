"""
clinicaltrials_adapter.py — ClinicalTrials.gov v2 API adapter.

Fetches trial records for drug-indication pairs and bulk-ingests
the full registry for failed trial classification.

API docs: https://clinicaltrials.gov/data-api/api
"""

from __future__ import annotations

import logging
import time
from typing import Generator

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2"
DEFAULT_PAGE_SIZE = 1000
REQUEST_DELAY = 0.3  # seconds between requests (be polite)


class ClinicalTrialsAdapter:
    def __init__(self, request_delay: float = REQUEST_DELAY) -> None:
        self.delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "repurposing-pipeline/0.1"})

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}{endpoint}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp.json()

    # ------------------------------------------------------------------
    # Study search
    # ------------------------------------------------------------------

    def search_studies(
        self,
        drug_name: str | None = None,
        condition: str | None = None,
        status: list[str] | None = None,
        phase: list[str] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Generator[dict, None, None]:
        """
        Yield study records matching the query.

        Args:
            drug_name: intervention/drug name to search for
            condition: disease/condition to search for
            status: e.g. ['COMPLETED', 'TERMINATED']
            phase: e.g. ['PHASE2', 'PHASE3']
        """
        params: dict = {"pageSize": page_size, "format": "json"}
        query_parts = []
        if drug_name:
            query_parts.append(drug_name)
        if condition:
            query_parts.append(condition)
        if query_parts:
            params["query.term"] = " AND ".join(query_parts)
        if status:
            params["filter.overallStatus"] = "|".join(status)
        if phase:
            params["filter.phase"] = "|".join(phase)

        next_token = None
        while True:
            if next_token:
                params["pageToken"] = next_token
            data = self._get("/studies", params)
            studies = data.get("studies", [])
            for study in studies:
                yield self._parse_study(study)
            next_token = data.get("nextPageToken")
            if not next_token:
                break

    def get_study(self, nct_id: str) -> dict:
        """Fetch a single study by NCT ID."""
        data = self._get(f"/studies/{nct_id}")
        return self._parse_study(data)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_study(self, raw: dict) -> dict:
        proto = raw.get("protocolSection", {})
        id_module = proto.get("identificationModule", {})
        status_module = proto.get("statusModule", {})
        design_module = proto.get("designModule", {})
        outcomes_module = proto.get("outcomesModule", {})
        sponsor_module = proto.get("sponsorCollaboratorsModule", {})
        arms_module = proto.get("armsInterventionsModule", {})

        # Extract drug names from interventions
        interventions = arms_module.get("interventions", [])
        drug_names = [
            iv.get("name", "")
            for iv in interventions
            if iv.get("type", "").upper() == "DRUG"
        ]

        return {
            "trial_id": id_module.get("nctId"),
            "title": id_module.get("briefTitle"),
            "status": status_module.get("overallStatus"),
            "phase": design_module.get("phases", [None])[0],
            "start_date": status_module.get("startDateStruct", {}).get("date"),
            "completion_date": status_module.get("completionDateStruct", {}).get("date"),
            "enrollment": design_module.get("enrollmentInfo", {}).get("count"),
            "primary_outcome": self._extract_primary_outcome(outcomes_module),
            "sponsor": sponsor_module.get("leadSponsor", {}).get("name"),
            "drug_names": drug_names,
            "source": "clinicaltrials_gov",
        }

    @staticmethod
    def _extract_primary_outcome(outcomes_module: dict) -> str | None:
        primary = outcomes_module.get("primaryOutcomes", [])
        if primary:
            return primary[0].get("measure")
        return None

    # ------------------------------------------------------------------
    # Bulk download helpers
    # ------------------------------------------------------------------

    def iter_terminated_trials(self, phase: list[str] | None = None) -> Generator[dict, None, None]:
        """Iterate all TERMINATED trials — core of the failed trial database."""
        yield from self.search_studies(
            status=["TERMINATED", "WITHDRAWN"],
            phase=phase or ["PHASE2", "PHASE3"]
        )

    def iter_completed_trials(self, phase: list[str] | None = None) -> Generator[dict, None, None]:
        """Iterate all COMPLETED trials."""
        yield from self.search_studies(
            status=["COMPLETED"],
            phase=phase or ["PHASE2", "PHASE3"]
        )
