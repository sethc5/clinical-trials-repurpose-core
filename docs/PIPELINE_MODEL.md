# Pipeline Model Reference — Seth's Computational Science Stack

> **Purpose:** Chemical process model reference for every pipeline tier and component,
> the ideal/optimal design for each pipeline, and an honest delta map of where the
> current implementation diverges and why.
>
> **Covers:** biochem · clinical-repurposing · genomics · (and design notes for materials)
> **Last updated:** March 2026

---

## Visual Reference — Pipeline Diagrams

Quick reference Mermaid diagrams for each pipeline. For the full optimal model, delta analysis, and build priority, see Parts I–VII below.

### Biochem — Computational Drug Discovery

_Small molecule library → ADMET filters → pharmacophore → molecular docking → MD stability → FTO._

```mermaid
flowchart TD
    subgraph SRC["📦 Compound Sources"]
        direction LR
        C1["ChEMBL API\n~1.9M compounds"]
        C2["ZINC Database"]
        C3["PubChem"]
        C4["Local SDF"]
    end

    SRC --> ADP["Compound Adapter\niter_compounds\n── --limit N · --resume ──"]

    ADP --> T0

    subgraph TIER0["🔵 T0 — ADMET Pre-filter  (~0.1 s · RDKit)"]
        T0{{"T0 Filter"}}
        T0D["MW ≤ 500 Da · LogP ≤ 5.0 · TPSA ≤ 140 Å²\nRotBonds ≤ 10 · HBD 0–5 · HBA ≤ 10\nPAINS flag · hERG exclusion\nBBB estimate (CNS targets only)\n→ composite ADMET score 0–1"]
        T0 --- T0D
    end

    T0 -->|"❌ fail (reason logged)"| R0["Rejected"]
    T0 -->|"✅ pass"| T025

    subgraph TIER025["🟡 T0.25 — Pharmacophore / Shape  (~0.5 s · ODDT)"]
        T025{{"T0.25 Filter"}}
        T025D["Pharmacophore match vs known actives SDF\nShape + fingerprint similarity (RDKit)\nMin match score ≥ 0.6\n→ skipped if pharmacophore_ref: null"]
        T025 --- T025D
    end

    T025 -->|"❌ score < 0.6"| R025["Rejected"]
    T025 -->|"✅ pass / skip"| T1

    subgraph TIER1["🟠 T1 — Molecular Docking  (~3 s · GPU · parallel)"]
        T1{{"T1 Docking"}}
        T1D["Engine: Vina / GNINA / SMINA\nReceptor PDBQT pre-warmed (shared across workers)\nBinding box: center (x,y,z) + size 25³ Å\nExhaustiveness 4–8 · n_poses 9\nProcessPoolExecutor — N workers\n→ best score kcal/mol + pose JSON"]
        T1 --- T1D
    end

    T1 -->|"❌ score ≥ threshold\n(e.g. −9.0 kcal/mol)"| R1["Rejected"]
    T1 -->|"✅ score < threshold"| T2

    subgraph TIER2["🔴 T2 — MD Stability  (~30 s · GPU)"]
        T2{{"T2 Dynamics"}}
        T2D["Engine: GROMACS / OpenMM\nInput: T1 docked pose · 10 ns sim\nRMSD ≤ 3.0 Å · Persistence ≥ 0.6\nSelectivity vs off-target PDBs (optional)\n→ RMSD · persistence · selectivity"]
        T2 --- T2D
    end

    T2 -->|"❌ RMSD > 3.0 Å\nor persist < 0.6"| R2["Rejected"]
    T2 -->|"✅ stable"| FTO

    subgraph FTOB["⚖️ FTO — Patent Check"]
        FTO{{"patent-fto-core\n:8010"}}
        FTOD["SMILES + indication → risk score\nHIGH / MEDIUM / LOW\nblocking patents · design-around suggestions\n→ graceful skip if offline"]
        FTO --- FTOD
    end

    FTO -->|"LOW"| HIT["✅ Confirmed Hit"]
    FTO -->|"MEDIUM"| MED["⚠️ Flagged for Review"]
    FTO -->|"HIGH"| HIGH["🚫 HIGH FTO RISK"]
    FTO -->|"offline"| HIT

    subgraph STORE["💾 Persistence"]
        DB[("SQLite · landscape.db\ncompounds · runs · targets")]
        RCP["ReceiptWriter\nJSON checkpoint every N compounds"]
    end

    R0 & R025 & R1 & R2 & HIT & MED & HIGH --> DB
    DB --> RCP
    DB --> FG["findings_generator.py\nTop-N JOIN compounds\nMW · LogP · SMILES · Score"]

    subgraph OUT["📊 Outputs"]
        direction LR
        O1["FINDINGS.md\nranked hit table"]
        O2["scaffold_map.py"]
        O3["funnel_stats.py"]
        O4["binding_plot.py"]
    end

    FG --> OUT

    classDef tier fill:#1a3a5c,stroke:#4a9edd,color:#e8f4fd,font-weight:bold
    classDef rej fill:#4a1515,stroke:#c0392b,color:#fdd
    classDef hit fill:#1a4a1a,stroke:#27ae60,color:#dfd,font-weight:bold
    classDef med fill:#4a3a00,stroke:#f39c12,color:#ffe
    classDef db fill:#2a2a4a,stroke:#8e44ad,color:#ece
    classDef out fill:#1a3a3a,stroke:#16a085,color:#dfe
    classDef adp fill:#3a2a0a,stroke:#e67e22,color:#fec

    class T0,T025,T1,T2,FTO tier
    class R0,R025,R1,R2 rej
    class HIT hit
    class MED,HIGH med
    class DB,RCP db
    class FG,O1,O2,O3,O4 out
    class ADP adp
```

| Tier | Stage | Runtime | Tool | Key Threshold |
|---|---|---|---|---|
| T0 | ADMET / Lipinski | ~0.1 s | RDKit | MW ≤ 500, LogP ≤ 5 |
| T0.25 | Pharmacophore / Shape | ~0.5 s | ODDT | match ≥ 0.6 |
| T1 | Molecular Docking | ~3 s · GPU | Vina / GNINA | score ≤ −9.0 kcal/mol |
| T2 | MD Stability | ~30 s · GPU | GROMACS / OpenMM | RMSD ≤ 3.0 Å, persist ≥ 0.6 |
| FTO | Patent Check | async · HTTP | patent-fto-core | LOW / MEDIUM / HIGH |

---

### Clinical — Drug Repurposing

_Approved/investigational drug × indication pairs → mechanism overlap → network biology → deep mechanistic evidence → dossier synthesis._

```mermaid
flowchart TD
    subgraph SRC2["📦 Drug × Indication Pairs"]
        direction LR
        D1["DrugBank\napproved drugs"]
        D2["ChEMBL · OpenFDA\nclinical compounds"]
        D3["ClinicalTrials.gov\ninvestigational drugs"]
        D4["Custom pair list\n(CSV / YAML)"]
    end

    SRC2 --> ADP2["Repurposing Adapter\niter_pairs · drug × indication"]

    ADP2 --> T0C

    subgraph T0CB["🔵 T0 — Mechanism + Safety Screen  (~seconds)"]
        T0C{{"T0 Screen"}}
        T0CD["mechanism_overlap: MOA target ∩ disease pathway\n  (KEGG / Reactome / GO)\nsafety_filter: contraindication check vs\n  target population comorbidities\ntrial_history_checker: prior failed trials\n  in same drug × indication space\nmesh_distance: semantic drug class ↔ disease\n→ composite feasibility score"]
        T0C --- T0CD
    end

    T0C -->|"❌ low overlap\nor contraindicated"| R0C["Rejected"]
    T0C -->|"✅ plausible"| T025C

    subgraph T025CB["🟡 T0.25 — Network Biology + Literature  (~minutes)"]
        T025C{{"T0.25 Screen"}}
        T025CD["network_proximity: shortest path drug target → disease\n  gene in STRING PPI network (< 2 hops = plausible)\nlincs_scorer: LINCS L1000 transcriptomic reversal\n  (does drug signature reverse disease signature?)\nliterature_cooccurrence: PubMed co-occurrence count\nfailed_trial_classifier: classify failure mode\n  (safety / efficacy / trial design / commercial)"]
        T025C --- T025CD
    end

    T025C -->|"❌ poor proximity\nor weak reversal"| R025C["Rejected"]
    T025C -->|"✅ supported"| T1C

    subgraph T1CB["🟠 T1 — Deep Mechanistic Analysis  (~minutes · parallel)"]
        T1C{{"T1 Analysis"}}
        T1CD["pathway_analyzer: Reactome / KEGG enrichment overlap\npolypharmacology_scorer: multi-target benefit score\nfaers_miner: FAERS disproportionality analysis\n  (post-market adverse event signal mining)\nevidence_extractor: mechanistic evidence from\n  PubMed · ClinicalTrials.gov · OpenFDA\nevidence_scorer: weight by study design\n  (RCT > cohort > case study > in vitro)"]
        T1C --- T1CD
    end

    T1C -->|"❌ insufficient\nevidence"| R1C["Rejected"]
    T1C -->|"✅ strong evidence"| T2C

    subgraph T2CB["🔴 T2 — Dossier Synthesis  (~hours · LLM)"]
        T2C{{"T2 Synthesis"}}
        T2CD["evidence_synthesizer: LLM narrative synthesis\nbiomarker_identifier: patient stratification markers\n  (genomic · proteomic · imaging)\ndose_analyzer: PK/PD translation to new indication\ntrial_designer: Phase II protocol draft\n  (endpoints · N · duration · incl/excl criteria)\ncompetitive_landscape: current treatments + pipeline\ndossier_generator: full repurposing dossier\n  (PDF / Markdown / IND-ready sections)"]
        T2C --- T2CD
    end

    T2C -->|"❌ fails synthesis"| R2C["Rejected"]
    T2C -->|"✅ actionable"| FTOC

    subgraph FTOCB["⚖️ FTO — Patent Check"]
        FTOC{{"patent-fto-core\n:8010"}}
        FTOCD["SMILES + indication → risk score\ncomposition-of-matter + method-of-use claims\nHIGH / MEDIUM / LOW\nclear territories · design-around suggestions"]
        FTOC --- FTOCD
    end

    FTOC -->|"LOW / MEDIUM"| HITC["✅ Repurposing Candidate\nDossier + Trial Design ready"]
    FTOC -->|"HIGH"| HIGHC["🚫 HIGH FTO RISK"]
    FTOC -->|"offline"| HITC

    subgraph STOREC["💾 Persistence"]
        DBC[("SQLite · repurposing.db\ndrugs · pairs · runs · evidence")]
        RCPC["ReceiptSystem · batch checkpoint"]
    end

    R0C & R025C & R1C & R2C & HITC & HIGHC --> DBC
    DBC --> RCPC
    DBC --> FGC["findings_generator.py\nTop-N pairs ranked by evidence score"]

    subgraph OUTC["📊 Outputs"]
        direction LR
        OC1["REPURPOSING_FINDINGS.md"]
        OC2["cross_indication_analysis.py"]
        OC3["dossier/ (PDF per candidate)"]
        OC4["mechanism_clustering.py"]
    end

    FGC --> OUTC

    classDef tier fill:#1a3a5c,stroke:#4a9edd,color:#e8f4fd,font-weight:bold
    classDef rej fill:#4a1515,stroke:#c0392b,color:#fdd
    classDef hit fill:#1a4a1a,stroke:#27ae60,color:#dfd,font-weight:bold
    classDef med fill:#4a3a00,stroke:#f39c12,color:#ffe
    classDef db fill:#2a2a4a,stroke:#8e44ad,color:#ece
    classDef out fill:#1a3a3a,stroke:#16a085,color:#dfe
    classDef adp fill:#3a2a0a,stroke:#e67e22,color:#fec

    class T0C,T025C,T1C,T2C,FTOC tier
    class R0C,R025C,R1C,R2C rej
    class HITC hit
    class HIGHC med
    class DBC,RCPC db
    class FGC,OC1,OC2,OC3,OC4 out
    class ADP2 adp
```

| Tier | Stage | Runtime | Key Modules | Key Signal |
|---|---|---|---|---|
| T0 | Mechanism + Safety | seconds | mechanism_overlap · safety_filter · trial_history | MOA overlap + no contraindication |
| T0.25 | Network + Literature | minutes | network_proximity · lincs_scorer · pubmed_cooccurrence | proximity ↑ + transcriptomic reversal |
| T1 | Deep Mechanistic | minutes · parallel | pathway_analyzer · faers_miner · evidence_scorer | RCT + cohort evidence weight |
| T2 | Dossier Synthesis | hours · LLM | evidence_synthesizer · trial_designer · dossier_generator | actionable Phase II protocol |
| FTO | Patent Check | async · HTTP | patent-fto-core | method-of-use patent risk |

---

### Genomics — Sequence Space Screening

_Peptide / guide-RNA candidates → physicochemical filters → ML prediction → structure prediction → high-accuracy validation._

```mermaid
flowchart TD
    subgraph SRC3["📦 Sequence Sources"]
        direction LR
        G1["Local FASTA\nmetagenomic ORFs"]
        G2["NCBI / UniProt\nbulk download"]
        G3["De novo generation\n(combinatorial / model)"]
    end

    SRC3 --> ADP3["Sequence Adapter\niter_sequences · peptide / guide-RNA"]

    ADP3 --> SEQ_ROUTE{"Sequence\ntype?"}
    SEQ_ROUTE -->|"peptide / protein / AMP"| T0_AMP
    SEQ_ROUTE -->|"guide_rna / dna / rna"| T0_CRISPR

    subgraph T0AB["🔵 T0 — Physicochemical Filters  (~µs · pure Python)"]
        T0_AMP{{"T0 · AMP"}}
        T0_AMPD["Length 10–50 aa · canonical AAs only\nNet charge ≥ +2 at pH 7\nGRAVY hydrophobicity −2.5 to +2.5\nInstability index ≤ 40\nShannon entropy ≥ 2.0 bits/residue\nHemolysis heuristic flag"]
        T0_AMP --- T0_AMPD

        T0_CRISPR{{"T0 · CRISPR"}}
        T0_CRISPRD["Guide length · PAM site presence\nGC content 40–70%\nSeed region uniqueness\nPolyN repeat exclusion\nFast BLAST off-target estimate"]
        T0_CRISPR --- T0_CRISPRD
    end

    T0_AMP & T0_CRISPR -->|"❌ fail"| R0G["Rejected"]
    T0_AMP & T0_CRISPR -->|"✅ pass"| T025G

    subgraph T025GB["🟡 T0.25 — ML Prediction + Alignment  (~seconds)"]
        T025G{{"T0.25 Screen"}}
        T025GD["AMP: ESM-2 embedding + RF activity classifier\nCRISPR: Cas-OFFinder off-target alignment\n  + on-target efficiency score (DeepCpf1)\nMMseqs2 deduplication (near-identical collapse)\n→ predicted activity / specificity score"]
        T025G --- T025GD
    end

    T025G -->|"❌ low predicted\nactivity"| R025G["Rejected"]
    T025G -->|"✅ pass"| T1G

    subgraph T1GB["🟠 T1 — Structure + Function  (~minutes · GPU)"]
        T1G{{"T1 Analysis"}}
        T1GD["AMP: AlphaFold2 / ESMFold structure pred.\n  pLDDT quality filter\n  Amphipathic helix detection\n  Implicit bilayer membrane interaction model\nCRISPR: RNAfold binding energy\n  Cas-OFFinder genome-wide off-target\n  DeepCpf1 / RuleSet3 efficiency\n→ structural fitness + specificity score"]
        T1G --- T1GD
    end

    T1G -->|"❌ poor structure\nor off-target risk"| R1G["Rejected"]
    T1G -->|"✅ structurally sound"| T2G

    subgraph T2GB["🔴 T2 — High-Accuracy Validation  (~hours · GPU)"]
        T2G{{"T2 Validation"}}
        T2GD["AMP: all-atom MD (GROMACS)\n  hemolysis + mammalian toxicity in silico\n  biofilm penetration model\n  resistance mutation resilience\nCRISPR: high-fidelity CRISPOR scoring\n  Cas9-guide-target energy minimization\n  delivery feasibility (AAV / LNP)\n→ validated candidate profile"]
        T2G --- T2GD
    end

    T2G -->|"❌ fails validation"| R2G["Rejected"]
    T2G -->|"✅ validated"| FTOG

    subgraph FTOGB["⚖️ FTO — Patent Check"]
        FTOG{{"patent-fto-core\n:8010"}}
        FTOGD["Sequence → InChIKey (peptides)\nUSPTO + EPO OPS + SureChEMBL\ncomposition + method-of-use claims\nHIGH / MEDIUM / LOW"]
        FTOG --- FTOGD
    end

    FTOG -->|"LOW / MEDIUM"| HITG["✅ Candidate\nfor synthesis / ordering"]
    FTOG -->|"HIGH"| HIGHG["🚫 HIGH FTO RISK"]
    FTOG -->|"offline"| HITG

    subgraph STOREG["💾 Persistence"]
        DBG[("SQLite · results.db\nsequences · runs · targets")]
        RCPG["ReceiptSystem · batch checkpoint"]
    end

    R0G & R025G & R1G & R2G & HITG & HIGHG --> DBG
    DBG --> RCPG
    DBG --> FGG["findings_generator\nTop-N sequences ranked by score"]

    subgraph OUTG["📊 Outputs"]
        direction LR
        OG1["FINDINGS.md"]
        OG2["Structure predictions\n(PDB / CIF)"]
        OG3["correlation_scanner\nsequence landscape"]
    end

    FGG --> OUTG

    classDef tier fill:#1a3a5c,stroke:#4a9edd,color:#e8f4fd,font-weight:bold
    classDef rej fill:#4a1515,stroke:#c0392b,color:#fdd
    classDef hit fill:#1a4a1a,stroke:#27ae60,color:#dfd,font-weight:bold
    classDef med fill:#4a3a00,stroke:#f39c12,color:#ffe
    classDef db fill:#2a2a4a,stroke:#8e44ad,color:#ece
    classDef out fill:#1a3a3a,stroke:#16a085,color:#dfe
    classDef adp fill:#3a2a0a,stroke:#e67e22,color:#fec
    classDef route fill:#3a3a1a,stroke:#d4ac0d,color:#fff

    class T0_AMP,T0_CRISPR,T025G,T1G,T2G,FTOG tier
    class R0G,R025G,R1G,R2G rej
    class HITG hit
    class HIGHG med
    class DBG,RCPG db
    class FGG,OG1,OG2,OG3 out
    class ADP3 adp
    class SEQ_ROUTE route
```

| Tier | Stage | Runtime | AMP Path | CRISPR / gRNA Path |
|---|---|---|---|---|
| T0 | Physicochemical | ~µs | length · charge · GRAVY · instability · entropy · hemolysis | length · PAM · GC% · polyN · BLAST off-target |
| T0.25 | ML + Alignment | seconds | ESM-2/RF classifier · MMseqs2 dedup | Cas-OFFinder alignment · DeepCpf1 efficiency |
| T1 | Structure + Function | minutes · GPU | AlphaFold2 · amphipathicity · membrane MD | RNAfold · DeepCpf1 · genome-wide off-target |
| T2 | Full Validation | hours · GPU | all-atom MD · hemolysis in silico · resistance | CRISPOR · Cas9 energy · delivery feasibility |
| FTO | Patent Check | async · HTTP | sequence composition claim search | guide + target claim search |

---

### Patent FTO — Freedom-to-Operate Analysis

_Compound SMILES + indication → multi-database patent search → claim extraction + structure matching → LLM analysis → risk verdict + report._

```mermaid
flowchart TD
    subgraph INPUT["📥 Input  POST /fto/compound"]
        IN["smiles: str\nindication: str\njurisdictions: list\nclaim_types: [composition_of_matter,\n  method_of_use]\nuse_cache: bool"]
    end

    IN --> CACHE{"Cache\nhit?"}
    CACHE -->|"✅ yes"| CACHED["Return cached FTOResult\n(SQLite lookup by InChIKey)"]
    CACHE -->|"❌ no"| RESOLVE

    subgraph CORE["⚙️ Processing Pipeline"]
        RESOLVE["compound_resolver.py\nSMILES → canonical SMILES\n→ InChI → InChIKey\n→ molecular formula + MW\n(RDKit · no network)"]

        RESOLVE --> SEARCH

        SEARCH["patent_search adapters\n── parallel fetch ──\nUSPTO full-text + claims API\nEPO OPS (European Patent Office)\nSureChEMBL chemical entity index\nPubChem patent cross-ref\n→ patent list + raw claim text"]

        SEARCH --> EXTRACT

        EXTRACT["claim_extractor.py\nParse claim grammar:\n  comprising / consisting of\n  Markush structures (R-groups)\n  composition_of_matter\n  method_of_use\nOutputs structured Claim objects\n(regex · no LLM · fast)"]

        EXTRACT --> MATCH

        MATCH["structure_matcher.py\nTanimoto fingerprint similarity\nSubstructure match (RDKit)\nMarkush expansion + match\nPer-claim MatchResult:\n  overlap_score 0–1\n  overlap_reasoning\n  claim_type"]

        MATCH --> LLM

        LLM["llm_analyzer.py\nLLM (GPT-4o / Claude)\nevaluates borderline matches\n(Tanimoto 0.5–0.85)\nAssesses:\n  literal infringement\n  doctrine of equivalents\n  claim scope interpretation\n→ infringes [true/false/null]\n  confidence · design-around"]

        LLM --> TERM

        TERM["patent_term_calculator.py\nExpiry per jurisdiction:\n  US: filing + 20 yr + PTA\n  EP: grant + 20 yr + SPC\nExpired → clear territory\n(non-blocking)"]

        TERM --> SCORE

        SCORE["risk_scorer.py\nHIGH: composition/Markush\n  infringes=True · confidence≥medium\n  not expired\nMEDIUM: method-of-use infringes=True\n  OR composition low-confidence\n  OR Tanimoto≥0.85 inconclusive\nLOW: no hits · OR all expired\n\n→ blocking_patents []\n  clear_territories []\n  design_around_suggestions []"]
    end

    SCORE --> RENDER

    RENDER["report_renderer.py\nJinja2 → PDF / HTML\n  Executive Summary (risk verdict)\n  Blocking Patents (claim text + expiry)\n  Clear Territories\n  Design-Around Suggestions\n  Search Metadata"]

    subgraph RESP["📤 FTOResponse"]
        direction LR
        R1["request_id · inchikey\nrisk_level: HIGH/MEDIUM/LOW\nblocking_patents []"]
        R2["clear_territories []\ndesign_around_suggestions []\ncached: bool"]
    end

    RENDER --> RESP

    subgraph STORE4["💾 Persistence + Async"]
        DB4[("SQLite · fto.db\nanalyses · patents\ncompounds · Markush cache")]
        ASYNC["GET /fto/status/{request_id}\nAsync poll for long searches"]
    end

    RESP --> DB4
    DB4 --> ASYNC

    subgraph SRCS["🔍 Patent DB Adapters"]
        direction LR
        P1["uspto_adapter.py"]
        P2["epo_ops_adapter.py"]
        P3["surechembl_adapter.py"]
        P4["pubchem_adapter.py"]
    end

    SEARCH -.->|"parallel"| SRCS

    classDef core fill:#1a3a5c,stroke:#4a9edd,color:#e8f4fd,font-weight:bold
    classDef out fill:#1a4a1a,stroke:#27ae60,color:#dfd,font-weight:bold
    classDef db fill:#2a2a4a,stroke:#8e44ad,color:#ece
    classDef inp fill:#3a2a0a,stroke:#e67e22,color:#fec
    classDef src fill:#2a1a3a,stroke:#9b59b6,color:#ede
    classDef cached fill:#1a3a3a,stroke:#16a085,color:#dfe

    class RESOLVE,SEARCH,EXTRACT,MATCH,LLM,TERM,SCORE core
    class RENDER,R1,R2 out
    class DB4,ASYNC db
    class IN,INPUT inp
    class P1,P2,P3,P4 src
    class CACHED cached
```

| Stage | Module | Runtime | Method | Output |
|---|---|---|---|---|
| Resolve | compound_resolver | ~ms | RDKit canonical + InChIKey | compound identity |
| Search | patent_search adapters | 5–30 s | USPTO · EPO OPS · SureChEMBL (parallel) | patent list + raw claims |
| Extract | claim_extractor | ~ms | regex grammar parser | structured Claim objects |
| Match | structure_matcher | ~ms–s | Tanimoto + substructure + Markush | overlap_score per claim |
| Analyze | llm_analyzer | 5–20 s | GPT-4o / Claude | infringes + confidence + design-around |
| Score | risk_scorer | ~ms | rule aggregation | HIGH / MEDIUM / LOW |
| Render | report_renderer | ~s | Jinja2 → PDF / HTML | full FTO report |

---

## Part I — Universal Architecture (All Pipelines)

All pipelines in this stack share a single design pattern: a **4-tier screening funnel**
backed by a SQLite database, receipt system for distributed compute, and automated
findings generation. The pattern is domain-agnostic at the infrastructure level and
instantiated per application via `config.yaml`.

### The Canonical 4-Tier Model

```
                  ┌─────────────────────────────────────────────────────────┐
  Input space     │  Millions of candidates (compounds, drugs, sequences,   │
  (database or    │  materials compositions)                                 │
   de novo)       └─────────────────────────────────────────────────────────┘
                                          │
                           T0 — Fast filter (cheap, local)
                           ├─ <1ms (genomics) · ~0.1s (biochem) · ~0.1s (clinical)
                           ├─ No external calls, no GPU
                           ├─ ~10–30% pass rate
                           └─ KILL: composition/property/safety constraint violations
                                          │
                         T0.25 — Medium filter (ML or network)
                         ├─ ~0.5s (biochem) · ~1–5s (genomics/clinical)
                         ├─ ML inference, network proximity, fingerprint similarity
                         ├─ ~10% pass rate
                         └─ KILL: mechanistic implausibility, poor predicted affinity
                                          │
                             T1 — Expensive simulation
                             ├─ ~3–35s (biochem) · seconds (clinical) · 10–60min (materials)
                             ├─ Molecular docking, transcriptomic matching, structure pred.
                             ├─ ~10% pass rate
                             └─ KILL: score below binding/affinity/mechanistic threshold
                                          │
                               T2 — High-accuracy validation
                               ├─ ~30s–10min (biochem MD) · hours (materials DFT)
                               ├─ MD stability, selectivity, evidence synthesis
                               ├─ ~10% pass rate
                               └─ PROMOTE: final ranked candidates for experimental work
                                          │
                          rank_candidates.py → FINDINGS.md → IND/patent/report
```

### Shared Infrastructure Components

| Component | File | Role |
|---|---|---|
| Config validation | `config_schema.py` | Pydantic v2; fails fast before any compute |
| SQLite persistence | `db_utils.py` | `LandscapeDB`; upsert-safe; WAL mode |
| Receipt system | `receipt_system.py` | JSON checkpoint per N compounds; enables distributed/resumable runs |
| Batch runner | `batch_runner.py` | Splits library for multi-machine distribution |
| Merge receipts | `merge_receipts.py` | Ingests remote receipt JSONs into local DB |
| Findings generator | `findings_generator.py` | Pulls DB → FINDINGS.md |
| Correlation scanner | `correlation_scanner.py` | Nightly anomaly detection on accumulated DB |
| Rank candidates | `rank_candidates.py` | Composite score + rank of T2+ survivors |
| Validate pipeline | `validate_pipeline.py` | Known-actives recovery test before full scan |
| LLM client | `llm_client.py` | OpenRouter wrapper; narrative generation |

---

## Part II — Biochem Pipeline (biochem-pipeline-core)

### Problem domain

Screen novel small molecules from public compound libraries (ChEMBL, ZINC, PubChem)
against a protein target. Output: ranked list of docking hits with ADMET profiles,
MD stability data, and FTO risk assessment — suitable for IND pre-application.

**Active instantiations:**
- EGFR / lung cancer — 10,000 compounds **complete**, 1,512 T1 hits, best -11.59 kcal/mol (CHEMBL418534)
- BCR-ABL / CML — 10,000 compounds **complete** (10 Mar 2026), 32 T1 hits, best -10.03 kcal/mol (CHEMBL10250)
- Mpro / COVID-19 — 10,000 compounds **complete** (10 Mar 2026), 4 T1 hits, best -8.66 kcal/mol (CHEMBL12139)
- InhA / TB (NTD) — 10,000 compounds **running** as of 10 Mar 2026; cutoff −7.0 kcal/mol

### Optimal Model

```
Compound library (ChEMBL bulk .gz — 2.3M entries, local parse, no API latency)
    │
    ↓ T0: RDKit ADMET (Lipinski Ro5 + Veber + TPSA + hERG SMARTS + PAINS)
    │     Target: ~0.05s/compound · 20–30% pass
    │
    ↓ T0.25: ODDT pharmacophore matching against known actives SDF
    │        OR Morgan fingerprint Tanimoto similarity (fast proxy)
    │        Target: ~0.5s/compound · 10% pass
    │
    ↓ T1: AutoDock-GPU or GNINA (neural-network docking)
    │     Parallel: ProcessPoolExecutor, 8+ workers, batch 10 compounds/worker
    │     Share: Vina init + receptor prep + affinity maps across batch
    │     Target: ~3–10s/compound (GPU) · ~35s/compound (CPU, current)
    │     exhaustiveness=8 for accuracy; 4 acceptable for hit-finding screens
    │
    ↓ T2: OpenMM MD (AMBER ff14SB + GAFF2, TIP3P, PME, 10ns)
    │     OR GROMACS via gromacs-studio HTTP API (faster, better force fields)
    │     Metrics: ligand RMSD, binding persistence, off-target selectivity
    │     Target: ~30s/compound (GPU) · 10% pass
    │
    ↓ FTO: Patent structure-to-claim matching (USPTO/EPO API + RDKit + LLM)
    │
    ↓ IND draft: findings + T0 ADMET + T1 scores → Section 6/7 narrative (LLM)
    │
    rank_candidates.py → scaffold_analysis.py → FINDINGS.md
```

### Current Implementation vs Optimal

| Tier | Optimal | Current (March 2026) | Delta | Why |
|---|---|---|---|---|
| **Compound source** | ChEMBL bulk .gz (local, 2.3M, no latency) | ChEMBL REST API (streaming, network-dependent) | ⚠️ Suboptimal | No `local_path` configured in production configs; REST is fine for 10k, bottleneck at 100k+ |
| **T0** | Full RDKit ADMET + ML hERG model | RDKit ADMET + SMARTS-based hERG flag | ✅ Near-optimal | SMARTS hERG is fast and good enough for screening; ML hERG marginal gain |
| **T0.25** | ODDT 3D pharmacophore matching | Morgan fingerprint Tanimoto (fast proxy) | ⚠️ Degraded | ODDT NotImplementedError exists; Tanimoto works but misses 3D shape complementarity |
| **T1 engine** | GNINA (CNN scoring, higher accuracy) or AutoDock-GPU | AutoDock Vina (Python bindings, CPU) | ⚠️ Degraded | No GPU on Hetzner i9-9900K node; GNINA subprocess path implemented but not primary |
| **T1 parallelism** | Batch workers (10 cmpd/worker, amortised Vina init) | ✅ Batch workers — implemented Mar 2026 | ✅ Optimal | `_dock_worker_batch` + `ProcessPoolExecutor(8)` |
| **T1 exhaustiveness** | 8 (discovery), 16–32 (validation) | 4 (current production) | ✅ Acceptable | Halved for speed; hit-finding tolerance acceptable; increase to 8 for top-50 re-dock |
| **T2** | OpenMM (GAFF2 ligand, AMBER protein, 10ns, ligand RMSD) | `NotImplementedError` stub | ❌ Not implemented | Force field parameterisation (GAFF2 via OpenFF) not yet built |
| **T2 alt** | GROMACS via gromacs-studio HTTP | `_run_gromacs` implemented but GAFF2 not supported upstream | ⚠️ Partial | gromacs-studio does backbone-only RMSD; ligand-specific MD blocked on upstream feature |
| **FTO** | Structure-to-claim matching + LLM risk scorer | patent-fto-core FastAPI :8010; PubChem + EPO OPS live; LLM risk scorer wired | ✅ Wired | patent-fto-core smoke tested Mar 2026; pipeline_core.py uses `is_fto_service_available()` flag |
| **IND generator** | Template renderer + LLM drafting all 13 sections | `last_mile/ind_draft.py` — Sections 6, 7, 11; live LLM tested 10 Mar 2026 | ✅ Done | Tested on BCR-ABL CHEMBL10250; T2 still stub so Sec 6 omits MD RMSD data |
| **Scaffold analysis** | Bemis-Murcko clusters + UMAP chemical space | `scaffold_analysis.py` exists; "0 unique scaffolds" in output | ⚠️ Bug | DB diversity score 0.000 — likely compounds table not populated; scaffold_map.py calls `scaffold_analysis.py` |

---

## Part III — Clinical Repurposing Pipeline (clinical-trials-repurpose-core)

### Problem domain

Screen approved/shelved drugs against novel disease indications using mechanism overlap,
network proximity, transcriptomic signature reversal, and evidence synthesis.

**Search space:** ~20,000 approved drugs × disease indications = mechanistic proximity pairs
**Key advantage:** Safety data pre-exists. Repurposing cost ~$300M/7yr vs $2.6B/15yr de novo.

### Optimal Model

```
Drug library (DrugBank + ChEMBL approved + OpenFDA)
    │
    ↓ T0: Mechanism overlap + safety compatibility filter
    │     - MeSH/GO pathway overlap score
    │     - Black box warning incompatibility check vs target population
    │     - Drug already approved/trialled for this indication? → skip
    │     Target: milliseconds/pair · 20–30% pass
    │
    ↓ T0.25: Network proximity + transcriptomic signature matching
    │         - Network proximity: shortest path in PPI graph (STRING DB)
    │           (drug target genes → disease genes; < 2 hops = plausible)
    │         - LINCS L1000: does drug's gene expression signature reverse disease sig?
    │         Target: seconds/pair · 10% pass
    │
    ↓ T1: Binding site compatibility + clinical evidence scan
    │     - Re-docking against disease target (if structural data available)
    │     - PubMed NLP: extract drug × indication co-occurrence + sentiment
    │     - ClinicalTrials.gov: scan for related/adjacent trials
    │     Target: seconds–minutes/pair · 10% pass
    │
    ↓ T2: Evidence synthesis + trial design generation
    │     - LLM evidence chain: mechanistic → clinical → epidemiological
    │     - Phase II protocol draft (dose, endpoints, eligibility, power)
    │     - Safety compatibility deep analysis (age, comorbidities, DDIs)
    │     Target: minutes/pair (LLM) · top 5–20% of T1 survivors
    │
    rank_candidates.py → FINDINGS.md → clinical brief
```

### Current Implementation vs Optimal

| Tier | Optimal | Current (March 2026) | Delta | Why |
|---|---|---|---|---|
| **T0** | DrugBank mechanism lookup + MeSH pathway overlap + safety flag | Pathway Jaccard overlap + active trial exclusion | ✅ Mostly built | `validate_pipeline.py` 8/8 pairs recovering — core logic functional |
| **T0.25** | STRING network proximity + LINCS L1000 signature reversal | Network proximity via STRING; LINCS partial | ⚠️ Partial | LINCS L1000 integration stubbed; STRING working |
| **T1** | PubMed NLP + ClinicalTrials scan + docking (if structure available) | ClinicalTrials API scan + basic evidence retrieval | ⚠️ Partial | LLM evidence extraction in `pipeline_core.py` exists but LLM calls are compute-expensive at scale |
| **T2** | Full LLM evidence synthesis + Phase II trial draft | LLM synthesis implemented via `llm_client.py` | ✅ Mostly built | Most sophisticated T2 in any pipeline; LLM calls via OpenRouter |
| **LLM client** | OpenRouter / Claude Sonnet with retry + cost tracking | `llm_client.py` exists, OpenRouter wrapper | ✅ Built | Only pipeline with LLM integrated at the compute tier level |
| **Cross-indication** | `cross_indication_analysis.py` finding shared mechanisms | `cross_indication_analysis.py` exists | ✅ Exists | Not yet regularly run as part of standard findings |
| **Mechanism clustering** | Cluster candidates by MoA for portfolio diversity | `mechanism_clustering.py` exists | ✅ Exists | Integration with findings generator unclear |

---

## Part IV — Genomics Pipeline (genomics-pipeline-core)

### Problem domain

Screen sequence space — metagenomic ORFs, NCBI proteins, de novo peptide enumeration,
genome-wide k-mers — for functional properties. Primary instantiation: antimicrobial
peptide (AMP) discovery from metagenomic data.

**Key architectural difference from biochem:** T0 is microseconds/sequence (not 0.1s/compound)
because sequence composition features (length, charge, hydrophobicity, GC content) are
trivially cheap. This means T0 can scan **billions** of sequences — the funnel shape is
dramatically different. T1 (structure prediction) is the bottleneck, not T0.

### Optimal Model

```
Sequence source:
  - NCBI/UniProt database (bulk FASTA download, 500M+ entries)
  - Metagenomic assembly ORFs (local FASTA)
  - De novo k-mer enumeration (combinatorial)
    │
    ↓ T0: Sequence composition filters (MICROSECONDS — scan billions)
    │     - Length gate: [min_len, max_len]
    │     - Charge: net charge at pH 7.4 (AMP: typically +2 to +9)
    │     - Hydrophobicity: Kyte-Doolittle, Eisenberg scale
    │     - Low-complexity filter: DUST / SEG (exclude repeats)
    │     - Toxic motif exclusion (configurable per application)
    │     - Signal peptide, TM domain exclusion (SignalP/TMHMM SMARTS equiv)
    │     Target: <1μs/sequence · 10% pass
    │
    ↓ T0.25: ML property prediction + fast alignment (MILLISECONDS)
    │         - ESM-2 (or ProtTrans) embedding + trained classifier
    │           (AMP: antimicrobial probability; CRISPR: on-target efficiency)
    │         - MMseqs2 homology check: similarity to known positives
    │         - No structure prediction yet — sequence-space only
    │         Target: ~1ms/sequence · 10% pass
    │
    ↓ T1: Structure prediction + functional site check (SECONDS)
    │     - ESMFold (fast, CPU/GPU, good for AMP-length peptides)
    │       OR AlphaFold2 (slower, more accurate, multi-GPU)
    │     - pLDDT quality filter: reject low-confidence structures
    │     - Amphipathic helix detection (AMP), active site geometry (enzymes)
    │     - Basic secondary structure composition
    │     Target: ~5–60s/sequence · 10% pass
    │
    ↓ T2: Full AlphaFold2 + MD stability + selectivity (MINUTES)
    │     - RoseTTAFold2 or full AF2 with templates
    │     - OpenMM MD: membrane interaction (AMP), binding stability
    │     - Off-target screen: selectivity vs human cell proteome
    │     - MIC/toxicity prediction ML model
    │     Target: 5–30min/sequence · top 10% → synthesis candidates
    │
    rank_candidates.py → FINDINGS.md → synthesis shortlist
```

### Funnel Scales (Optimal)

| Application | T0 input | →T0.25 | →T1 | →T2 | Output |
|---|---|---|---|---|---|
| AMP from metagenome | 50M ORFs | 5M | 500K | 50K | 5K for MIC testing |
| CRISPR guide design | 3M 20-mers | 900K | 180K | 18K | 200 guides/target gene |
| Variant effect scan | 10K SNPs | 8K | 3K | 300 | 30 for functional validation |
| De novo AMP design | 10²⁰ (enumerable) | scan NR × model | 500K | 50K | 500 for synthesis |

### Current Implementation vs Optimal

| Tier | Optimal | Current (March 2026) | Delta | Why |
|---|---|---|---|---|
| **Repo status** | Full implementation | Architecture defined; adapters/compute stubs | ❌ Not built | Design complete; no active instantiation yet |
| **Adapters** | NCBI, UniProt, Ensembl, gnomAD, PATRIC, MG-RAST, local FASTA, de novo | Listed in README, not implemented | ❌ Stubs | First instantiation (AMP pipeline) will drive implementation |
| **T0** | Charge/hydrophobicity/length/complexity (μs, vectorized numpy) | Not implemented | ❌ Not built | Straightforward — 1 day of work |
| **T0.25** | ESM-2 embedding + trained classifier + MMseqs2 | Not implemented | ❌ Not built | Requires training data per application |
| **T1** | ESMFold (fast) as primary | Not implemented | ❌ Not built | ESMFold pip-installable; highest-value next step |
| **T2** | AlphaFold2 + OpenMM membrane simulation | Not implemented | ❌ Not built | Blocked on T1 |
| **Key advantage** | T0 at μs/sequence → scan billions cheap | — | — | This is where genomics diverges most from biochem |

### Why Genomics T0 Is Architecturally Different

In biochem, T0 (RDKit ADMET) costs ~0.1s/compound because it computes molecular
descriptors (MW, logP, TPSA) that require graph traversal on an RDKit mol object.
In genomics, T0 costs <1μs/sequence because the features are simple string/array
operations on amino acid sequences — length, charge sum, mean hydrophobicity index.
This means genomics T0 can scan **50 million ORFs in under a minute** on a single CPU.
The funnel inversion: genomics T0 is practically free; T1 (ESMFold) is the bottleneck.

**Implementation implication:** genomics T0 should be vectorized across the full sequence
array (numpy/pandas) rather than a per-sequence Python function, to fully exploit the
microsecond-scale compute.

---

## Part V — Cross-Pipeline Integration (Optimal Full Stack)

The pipelines are designed to interoperate. The ideal full discovery stack:

```
                         ┌─────────────────────────────────┐
                         │   GENOMICS PIPELINE              │
                         │   Target identification:         │
                         │   - Novel AMPs (antibiotic)      │
                         │   - Resistance gene targets      │
                         │   - CRISPR therapeutic guides    │
                         └───────────────┬─────────────────┘
                                         │ target protein → PDB / sequence
                                         ↓
                         ┌─────────────────────────────────┐
                         │   BIOCHEM PIPELINE               │
                         │   Small molecule discovery:      │
                         │   - Screen 10k–1M compounds      │
                         │   - T1 docking against target    │
                         │   - T2 MD stability              │
                         │   - FTO scan on hits             │
                         └───────────────┬─────────────────┘
                                         │ validated hits → SMILES + scores
                                         ↓
                         ┌─────────────────────────────────┐
                         │   CLINICAL REPURPOSING PIPELINE  │
                         │   Parallel/complementary:        │
                         │   - Check if approved drugs      │
                         │     already hit biochem targets  │
                         │   - Generate repurposing leads   │
                         │     alongside de novo screen     │
                         └───────────────┬─────────────────┘
                                         │ repurposing candidates
                                         ↓
                         ┌─────────────────────────────────┐
                         │   LAST MILE MODULES              │
                         │   - patent-fto-core (FTO scan)   │
                         │   - IND generator (Sec 6/7/11)   │
                         │   - Findings narrative (LLM)     │
                         └─────────────────────────────────┘
```

**What exists today:** each pipeline runs independently, outputs to its own SQLite DB.
No cross-pipeline query or handoff is implemented.

**Optimal:** shared `compound_id` / `target_id` namespace across pipelines so a biochem
T2 survivor can be automatically queried in the clinical pipeline ("is there an approved
drug that hits the same target?"). This requires a shared compound registry — a single
`compounds` table that all pipelines write to, rather than isolated per-pipeline DBs.

---

## Part VI — Delta Map: Current vs Primary Model

This section is a consolidated honest diff — every place the current implementation
diverges from the optimal model, with root cause.

### Structural/Architecture Deltas

| Item | Model | Current | Root cause |
|---|---|---|---|
| **ChEMBL source** | Local bulk .gz, no API latency | REST API streaming | No `local_path` set in configs; easy fix |
| **T0.25 scoring** | ODDT 3D pharmacophore | Morgan fingerprint Tanimoto | ODDT `NotImplementedError`; Tanimoto is a valid fast proxy but ignores 3D shape |
| **T1 engine** | GNINA (neural net, higher accuracy) | Vina (classical) | No GPU on Hetzner compute node; GNINA subprocess path exists but unused |
| **T1 with GPU** | GNINA/AutoDock-GPU (3–5s/compound, GPU) | Vina CPU (35s/compound) | Hetzner i9-9900K has no CUDA GPU; 7× slower than GPU target |
| **T2 (biochem)** | OpenMM full MD with GAFF2+AMBER | `NotImplementedError` | Force field parameterisation (OpenFF/GAFF2) not built |
| **T2 ligand RMSD** | Ligand-specific RMSD from docked pose | gromacs-studio backbone-only RMSD (stub) | Upstream gromacs-studio lacks GAFF2 ligand support |
| **FTO module** | Structure-to-claim match + LLM risk score | ✅ Live — patent-fto-core FastAPI :8010; PubChem + EPO OPS tested Mar 2026 | patent-fto-core built + smoke tested; pipeline_core.py wired via `is_fto_service_available()` |
| **IND generator** | All 13 sections; LLM narrative + ASKCOS | ✅ Built — `last_mile/ind_draft.py`; Sections 6, 7, 11 live-LLM tested 10 Mar 2026 | T2 still stub (Sec 6 MD omitted); ASKCOS (Sec 8 CMC) not yet integrated |
| **Scaffold analysis** | Bemis-Murcko clusters + UMAP | "0 unique scaffolds" in output | Compounds table likely not populated; scaffold_analysis call bug |
| **Cross-pipeline DB** | Shared compound registry across all pipelines | Isolated SQLite per pipeline | Architectural decision needed before merging DBs |
| **Genomics pipeline** | Full 4-tier sequence screen | Design only; no implementation | No active instantiation driving development |
| **T0 vectorisation (genomics)** | Numpy batch over full sequence array | Per-sequence Python call (model) | Not yet implemented |

### Performance Deltas

| Metric | Optimal target | Current (March 2026) | Factor |
|---|---|---|---|
| T1 throughput (Vina, CPU) | ~5s/compound (AutoDock-GPU) | ~35s/compound (Vina, CPU) | 7× slower |
| T1 throughput (batched) | ~3s/compound (shared Vina init, batch=10) | ~35s/compound → ~3.5s/compound with batch | ✅ Batching closes gap |
| Workers (Hetzner 16-thread) | 8 per scan (×2 scans = 16 threads) | ✅ 8/scan active | ✅ Optimal |
| 10k compound scan ETA | ~2h (GPU) | ~3.5h (CPU, batch+exh=4) | 1.75× from GPU target |
| T0 (genomics, sequences) | <1μs (vectorised numpy) | Not implemented | — |
| T1 (genomics, ESMFold) | ~5–10s/sequence | Not implemented | — |

### Why These Deltas Exist (Priority Order)

1. **No GPU compute (T1 speed)** — deliberate infrastructure choice. Hetzner dedicated i9-9900K
   is €44/mo; a Hetzner GPU server (RTX 4000 SFF) is €250+/mo. For hit-finding screens at
   10k compounds, the current CPU + batch approach is cost-optimal. Upgrade path: add one
   GPU node for top-50 re-dock validation at exhaustiveness=32.

2. **T2 not implemented** — GAFF2 ligand parameterisation is the blocking step. `openff-toolkit`
   + `openmmforcefields` are pip-installable. The simulation loop is 2–3 days of engineering.
   Blocked on prioritisation, not technical difficulty. The T2 stub's `NotImplementedError`
   is intentional — it fails loud rather than returning false results.

3. **ODDT pharmacophore** — Tanimoto fingerprint similarity is a valid, fast proxy for
   pharmacophore screening. The delta from true 3D pharmacophore matching is real but
   acceptable for large-scale hit-finding. Upgrade is 1–2 days once known-actives SDFs are
   assembled per target.

4. **Genomics not implemented** — no active research instantiation pulling it forward. All
   pipeline development is driven by concrete active scans (EGFR, BCR-ABL, Mpro, clinical
   longevity). Genomics needs a target application: AMP discovery from a specific metagenome,
   or CRISPR guide design for a specific bacterial pathogen.

5. **FTO / IND** — last-mile modules. Every prerequisite (compound SMILES in DB, T0 ADMET
   flags, T1 docking scores) is now populated from EGFR scan. The FTO and IND modules can
   be built against real data. Highest ROI next engineering sprint after T2.

---

## Part VII — Priority Build Order (What to Build Next)

```
NOW (data exists, enables everything downstream):
  ├─ T2 OpenMM implementation (3 days)
  │   → unblocks T2 → IND Sections 6+7 → real regulatory artifact
  │   → GAFF2 via openff-toolkit; simulation loop already scaffolded
  └─ Scaffold analysis fix (2 hours)
      → fix "0 unique scaffolds" bug → actual diversity metrics on EGFR 1,512 hits

DONE (completed Mar 2026):
  ├─ FTO module: patent-fto-core FastAPI :8010 ✅
  │   → PubChem + EPO OPS live; LLM risk scorer wired
  │   → Next: customer outreach + Stripe payment link
  └─ IND generator: last_mile/ind_draft.py Sections 6, 7, 11 ✅
      → live LLM tested; DOCX + MD output
      → Next: Section 8 CMC (ASKCOS); T2 MD for Sec 6 RMSD data

SOON (high ROI, data is ready):
  └─ ChEMBL local bulk download (1 day)
      → eliminate API latency; enables 100k+ compound scans

MEDIUM (correct the design gaps):
  ├─ ODDT pharmacophore (2 days)
  │   → requires known-actives SDFs per target from ChEMBL bioactivity data
  ├─ GNINA integration as primary T1 engine (2 days)
  │   → subprocess path exists; needs GPU node or fallback benchmarking
  └─ Genomics first instantiation: AMP screen (1–2 weeks)
      → pick one metagenomic dataset; build T0+T0.25+T1(ESMFold) only

LONG TERM (infrastructure):
  └─ Shared compound registry across all pipelines
      → enables biochem ↔ clinical cross-query
      → requires namespace unification + migration of existing DBs
```

---

*Reference document — auto-maintained. Update when implementation catches up to model.*
