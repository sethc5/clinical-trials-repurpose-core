"""
faers_adapter.py — FDA Adverse Event Reporting System (FAERS) adapter.

Pulls adverse event signal data from OpenFDA FAERS endpoint.
Performs disproportionality analysis (Reporting Odds Ratio) for safety profiling.

WARNING: FAERS is spontaneous-report data. Rates are not incidence rates.
         Massive reporting bias exists — drugs in news get more reports.
"""

from __future__ import annotations

import logging
import math
import time
from typing import NamedTuple

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/drug/event.json"


class RORResult(NamedTuple):
    """Reporting Odds Ratio disproportionality result."""
    ae_term: str
    case_count: int      # drug + AE co-reports
    ror: float           # Reporting Odds Ratio
    ror_lower: float     # 95% CI lower
    ror_upper: float     # 95% CI upper
    significant: bool    # ROR lower CI > 1


class FAERSAdapter:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, params: dict) -> dict:
        if self.api_key:
            params["api_key"] = self.api_key
        resp = self.session.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        time.sleep(0.2)
        return resp.json()

    def get_ae_counts(self, drug_name: str, limit: int = 100) -> list[dict]:
        """Return top adverse events for a drug with report counts."""
        try:
            data = self._get({
                "search": f'patient.drug.medicinalproduct:"{drug_name}"',
                "count": "patient.reaction.reactionmeddrapt.exact",
                "limit": limit,
            })
            return data.get("results", [])
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return []
            raise

    def get_total_reports_for_drug(self, drug_name: str) -> int:
        """Return total number of FAERS reports mentioning a drug."""
        try:
            data = self._get({
                "search": f'patient.drug.medicinalproduct:"{drug_name}"',
                "count": "receivedate",
                "limit": 1,
            })
            meta = data.get("meta", {})
            return meta.get("results", {}).get("total", 0)
        except requests.HTTPError:
            return 0

    def compute_ror(
        self,
        drug_name: str,
        ae_term: str,
        total_drug_reports: int | None = None,
        total_ae_reports: int | None = None,
        total_all_reports: int = 10_000_000,  # approximate FAERS total
    ) -> RORResult | None:
        """
        Compute Reporting Odds Ratio for a drug-AE pair.

        Uses standard 2×2 contingency table disproportionality analysis.
        """
        # a: reports with drug AND ae
        try:
            data = self._get({
                "search": (
                    f'patient.drug.medicinalproduct:"{drug_name}" '
                    f'AND patient.reaction.reactionmeddrapt:"{ae_term}"'
                ),
                "count": "receivedate",
                "limit": 1,
            })
            a = data.get("meta", {}).get("results", {}).get("total", 0)
        except requests.HTTPError:
            return None

        if a == 0:
            return None

        n_drug = total_drug_reports or self.get_total_reports_for_drug(drug_name) or 1
        n_ae = total_ae_reports or 1
        n_total = total_all_reports

        b = n_drug - a            # drug, no AE
        c = n_ae - a              # AE, no drug
        d = n_total - n_drug - c  # neither

        if b <= 0 or c <= 0 or d <= 0:
            return None

        ror = (a * d) / (b * c)
        # Woolf CI
        log_ror_se = math.sqrt(1/a + 1/b + 1/c + 1/d)
        ror_lower = math.exp(math.log(ror) - 1.96 * log_ror_se)
        ror_upper = math.exp(math.log(ror) + 1.96 * log_ror_se)

        return RORResult(
            ae_term=ae_term,
            case_count=a,
            ror=round(ror, 3),
            ror_lower=round(ror_lower, 3),
            ror_upper=round(ror_upper, 3),
            significant=ror_lower > 1,
        )
