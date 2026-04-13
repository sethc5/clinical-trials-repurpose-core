"""
opentargets_adapter.py — Open Targets Platform adapter.

Open Targets provides disease-target association scores with evidence breakdown.
GraphQL API: https://platform.opentargets.org/api

Uses the opentargets Python client or GraphQL directly.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"


DISEASE_TARGET_QUERY = """
query DiseaseTargets($diseaseId: String!, $size: Int!) {
  disease(efoId: $diseaseId) {
    id
    name
    associatedTargets(page: {index: 0, size: $size}) {
      rows {
        target {
          id
          approvedSymbol
          approvedName
        }
        score
        datatypeScores {
          componentId
          score
        }
      }
    }
  }
}
"""

DRUG_DISEASE_QUERY = """
query DrugDiseases($chemblId: String!) {
  drug(chemblId: $chemblId) {
    id
    name
    indications {
      rows {
        disease {
          id
          name
        }
        maxPhaseForIndication
      }
    }
  }
}
"""


class OpenTargetsAdapter:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def _query(self, query: str, variables: dict) -> dict:
        resp = self.session.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("data", {})

    def get_target_associations(self, disease_efo_id: str, top_n: int = 200) -> list[dict]:
        """
        Return disease-target associations from Open Targets.

        Args:
            disease_efo_id: EFO disease ID (e.g. 'EFO_0000249' for Alzheimer's)
            top_n: maximum associations to return

        Returns:
            [{target_id, gene_symbol, score, evidence_by_type}, ...]
        """
        data = self._query(DISEASE_TARGET_QUERY, {"diseaseId": disease_efo_id, "size": top_n})
        disease = data.get("disease", {})
        rows = disease.get("associatedTargets", {}).get("rows", [])
        return [
            {
                "target_id": r["target"]["id"],
                "gene_symbol": r["target"]["approvedSymbol"],
                "gene_name": r["target"]["approvedName"],
                "score": r.get("score"),
                "evidence_by_datatype": {
                    s["componentId"]: s["score"]
                    for s in r.get("datatypeScores", [])
                },
            }
            for r in rows
        ]

    def get_drug_indications(self, chembl_id: str) -> list[dict]:
        """
        Return approved + trial indications for a drug from Open Targets.

        Args:
            chembl_id: ChEMBL compound ID (e.g. 'CHEMBL1431')
        """
        data = self._query(DRUG_DISEASE_QUERY, {"chemblId": chembl_id})
        drug = data.get("drug", {})
        rows = drug.get("indications", {}).get("rows", [])
        return [
            {
                "disease_id": r["disease"]["id"],
                "disease_name": r["disease"]["name"],
                "max_phase": r.get("maxPhaseForIndication"),
            }
            for r in rows
        ]

    def get_drug_target_score(self, chembl_id: str, disease_efo_id: str) -> float | None:
        """
        Return a pragmatic Open Targets evidence proxy for a drug-disease pair.

        This uses drug indication evidence currently available from the Open Targets
        drug endpoint and maps `maxPhaseForIndication` to a normalized [0, 1] score:
          0 -> 0.0, 1 -> 0.25, 2 -> 0.50, 3 -> 0.75, 4 -> 1.0

        Returns None if the pair is not present in Open Targets drug indications.
        """
        indications = self.get_drug_indications(chembl_id)
        if not indications:
            return None

        wanted = self._normalize_disease_id(disease_efo_id)
        phase_values: list[int] = []
        for row in indications:
            disease_id = self._normalize_disease_id(row.get("disease_id", ""))
            if disease_id != wanted:
                continue
            phase_raw = row.get("max_phase")
            try:
                phase = int(phase_raw)
            except (TypeError, ValueError):
                continue
            if phase < 0:
                continue
            phase_values.append(min(phase, 4))

        if not phase_values:
            return None

        best_phase = max(phase_values)
        return round(best_phase / 4.0, 4)

    @staticmethod
    def _normalize_disease_id(value: str) -> str:
        """Normalize common Open Targets disease ID variants for robust matching."""
        return (value or "").strip().upper().replace(":", "_")
