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
        Look up Open Targets overall evidence score for a specific drug-disease pair.
        Returns None if not found.
        """
        targets = self.get_target_associations(disease_efo_id, top_n=500)
        # Find targets affected by this drug via target lookup
        # (simplified — full implementation joins drug targets to disease targets)
        return None  # stub; implement with drug→target→disease association join
