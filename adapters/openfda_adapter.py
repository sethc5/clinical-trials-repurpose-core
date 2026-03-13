"""
openfda_adapter.py — OpenFDA API adapter.

Covers:
  - Drug label API (mechanism, safety, indications)
  - Drug approval API (approval dates, status)
  - FAERS adverse event API (safety signals)

API docs: https://open.fda.gov/apis/
"""

from __future__ import annotations

import logging
import time
from typing import Generator

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov"


class OpenFDAAdapter:
    def __init__(self, api_key: str | None = None, request_delay: float = 0.2) -> None:
        self.api_key = api_key
        self.delay = request_delay
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}{endpoint}.json"
        p = dict(params or {})
        if self.api_key:
            p["api_key"] = self.api_key
        resp = self.session.get(url, params=p, timeout=30)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp.json()

    # ------------------------------------------------------------------
    # Drug labels
    # ------------------------------------------------------------------

    def get_drug_label(self, drug_name: str) -> dict | None:
        """Return parsed drug label for a given drug name."""
        try:
            data = self._get(
                "/drug/label",
                {"search": f'openfda.brand_name:"{drug_name}"', "limit": 1}
            )
            results = data.get("results", [])
            return self._parse_label(results[0]) if results else None
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def _parse_label(self, raw: dict) -> dict:
        openfda = raw.get("openfda", {})
        return {
            "drug_id": openfda.get("application_number", [None])[0],
            "name": openfda.get("brand_name", [None])[0],
            "generic_name": openfda.get("generic_name", [None])[0],
            "mechanism_of_action": self._first(raw.get("mechanism_of_action")),
            "pharmacodynamics": self._first(raw.get("pharmacodynamics")),
            "black_box_warnings": raw.get("boxed_warning", []),
            "contraindications": raw.get("contraindications", []),
            "serious_aes": raw.get("warnings_and_cautions", []),
            "pregnancy_category": self._first(raw.get("pregnancy")),
            "source": "openfda",
        }

    # ------------------------------------------------------------------
    # FAERS adverse events
    # ------------------------------------------------------------------

    def get_adverse_events(
        self,
        drug_name: str,
        limit: int = 100,
    ) -> list[dict]:
        """Return top adverse event reports for a drug."""
        try:
            data = self._get(
                "/drug/event",
                {
                    "search": f'patient.drug.medicinalproduct:"{drug_name}"',
                    "count": "patient.reaction.reactionmeddrapt.exact",
                    "limit": limit,
                }
            )
            return data.get("results", [])
        except requests.HTTPError:
            return []

    # ------------------------------------------------------------------
    # Drug approvals
    # ------------------------------------------------------------------

    def get_approval_dates(self, application_number: str) -> list[dict]:
        """Return approval history for an NDA/ANDA/BLA application number."""
        try:
            data = self._get(
                "/drug/drugsfda",
                {"search": f'application_number:"{application_number}"', "limit": 1}
            )
            results = data.get("results", [])
            if not results:
                return []
            submissions = results[0].get("submissions", [])
            return [
                {
                    "submission_type": s.get("submission_type"),
                    "submission_number": s.get("submission_number"),
                    "submission_status": s.get("submission_status"),
                    "submission_status_date": s.get("submission_status_date"),
                }
                for s in submissions
                if s.get("submission_status") == "AP"
            ]
        except requests.HTTPError:
            return []

    @staticmethod
    def _first(field: list | None) -> str | None:
        if isinstance(field, list) and field:
            return field[0]
        return field
