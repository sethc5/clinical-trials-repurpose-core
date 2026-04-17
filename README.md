# clinical-trial-repurposing-pipeline-core

**A systematic computational pipeline for drug repurposing discovery — scanning approved drugs, failed trials, shelved compounds, and high-availability OTC candidates (supplements, vitamins, minerals) against unmet disease indications using mechanism overlap, safety profiles, and literature evidence.**

The FDA has approved ~20,000 drugs and biologics. Another ~4,000 compounds have completed Phase II or Phase III trials and been shelved — not because they failed completely, but because they failed for a specific indication, at a specific dose, in a specific population. The global cost of bringing a new drug from discovery to approval is ~$2.6 billion and 12-15 years. Repurposing an approved drug costs ~$300 million and 3-7 years because safety data already exists. The opportunity is enormous and systematically underexplored.

ClinicalTrials.gov has 480,000+ registered trials. PubMed has 35 million papers. OpenFDA has complete adverse event and approval databases. The data to identify repurposing opportunities computationally is public, comprehensive, and largely unscanned at the systematic pipeline level.

This pipeline provides that systematic scanning layer. Unlike biochem-pipeline-core (which screens novel compounds against targets) this pipeline screens **known compounds against novel indications** — the search space is approved drugs × untested disease contexts, filtered by mechanistic plausibility, safety compatibility, and evidence strength.

### OTC / Nutraceutical Intent (Explicit Scope)

This pipeline also supports a dedicated OTC lane for:
- Widely available supplements
- Vitamins
- Minerals
- Other over-the-counter compounds with public exposure/safety history

Use case:
- Evaluate these candidates against disease-compromised health vectors (for example, mitochondrial dysfunction, inflammatory burden, metabolic stress, neurocognitive resilience) using the same reproducible T0→T2 evidence flow.

Guardrails:
- This is evidence triage, not direct treatment advice.
- Outputs must retain evidence quality labels, contraindication checks, and uncertainty annotations.
- Clinical actionability requires clinician review and jurisdiction-aware regulatory/safety checks.

Same architectural pattern as [biochem-pipeline-core](https://github.com/sethc5/biochem-pipeline-core), [materials-pipeline-core](https://github.com/sethc5/materials-pipeline-core), [genomics-pipeline-core](https://github.com/sethc5/genomics-pipeline-core), and [soil-microbiome-pipeline-core](https://github.com/sethc5/soil-microbiome-pipeline-core) — 4-tier funnel, SQLite database, receipt system, automated findings generation. The compute layer here is predominantly literature synthesis and network analysis rather than molecular simulation — closer to Athanor's core methodology but structured as a systematic screening pipeline with explicit tiers, database accumulation, and ranked outputs.

> **Status**: Architecture defined · Core pipeline in development · First instantiation: [longevity-repurposing-pipeline](https://github.com/sethc5/longevity-repurposing-pipeline) · [Contributors welcome](CONTRIBUTING.md)

Documentation map:
- `docs/DOCS_INDEX.md` (canonical doc/artifact index)
- `/home/seth/dev/medicine/biochem-pipeline-core/docs/SUITE_CANONICAL_HIERARCHY.md` (suite source-of-truth and anti-drift rules)
- `/home/seth/dev/medicine/biochem-pipeline-core/docs/PIPELINE_CANONICAL_STATE.md` (live shared tier/runtime state)
- `/home/seth/dev/medicine/biochem-pipeline-core/docs/SUITE_PACKAGE_CONTRACT.md` (shared handoff package contract checklist)
- `reference/README.md` (evidence/decision ledger contract)

---

## What Problem This Solves

Drug repurposing has two layers with the same infrastructure gap as every other domain in this pipeline family:

1. **Data layer** — ClinicalTrials.gov, OpenFDA, DrugBank, ChEMBL, PubMed, OMIM, DisGeNET, STRING, LINCS L1000. Extraordinary public data, well-maintained APIs, largely machine-readable.

2. **Pipeline layer** — systematic scanning infrastructure that maps drugs to mechanisms, mechanisms to diseases, diseases to safety compatibility, and surfaces ranked repurposing candidates with evidence chains. **This layer barely exists in open source.**

Academic repurposing studies exist — they are almost universally one-off analyses of a specific drug class against a specific disease, not reusable infrastructure. Commercial platforms (Recursion, BenchSci, Insilico Medicine) do systematic repurposing but are closed, expensive, and not accessible to academic groups or small biotech.

The specific gap this fills: **a clean, reusable, open-source pipeline that takes a target disease as input and returns ranked repurposing candidates with mechanistic justification, safety assessment, and trial design recommendations** — output that a clinician or small biotech could act on.

---

## Why This Is Architecturally Distinct From biochem-pipeline-core

biochem-pipeline-core screens novel compounds. This pipeline screens known compounds. The distinction matters for every tier:

**T0:** Instead of ADMET filters on novel molecules, you're filtering by existing safety profile, approved indication proximity, and mechanism database overlap. The filtering logic is database lookup, not molecular property calculation.

**T0.25:** Instead of pharmacophore matching, you're doing network proximity analysis — how close is the drug's known mechanism to the target disease pathway in a protein interaction network? Short network distance = mechanistic plausibility.

**T1:** Instead of docking simulation, you're doing transcriptomic signature matching (LINCS L1000) — does the drug's gene expression signature reverse the disease signature? This is a validated computational repurposing method with multiple FDA-approved successes.

**T2:** Instead of MD stability, you're doing evidence synthesis — how strong is the existing clinical, epidemiological, and mechanistic evidence? And trial design — what would a Phase II look like given the existing safety data?

The compute is predominantly network analysis, NLP, and statistical evidence synthesis rather than molecular simulation. This makes the pipeline significantly faster and cheaper to run than biochem — a full scan can complete on a laptop in hours rather than requiring GPU nodes for weeks.

---

## Architecture

### The 4-Tier Screening Funnel

```
T0   (milliseconds/drug-indication pair): Mechanism overlap + basic safety filter
  └─ SKIP if: drug has black box warning incompatible with target population
  └─ SKIP if: known contraindication for target disease context
  └─ SKIP if: mechanism has zero overlap with target disease pathway (MeSH/GO)
  └─ SKIP if: drug already approved or in active trials for this indication
  └─ COMPUTE: mechanism overlap score, safety compatibility flag

T0.25 (seconds/pair):   Network proximity + transcriptomic signature matching
  └─ PROMOTE if: drug-target network proximity to disease genes < threshold
  └─ PROMOTE if: LINCS L1000 transcriptomic reversal score > threshold
  └─ Fast literature co-occurrence: drug name + disease name in PubMed abstracts
  └─ Check failed trial database: has this been tried and definitively failed?

T1   (minutes/pair):    Deep mechanistic analysis + evidence extraction
  └─ Full pathway overlap analysis (KEGG, Reactome, GO enrichment)
  └─ Polypharmacology profile: all known targets, ranked by affinity
  └─ Adverse event profile mining (FAERS, VAERS, WHO VigiBase)
  └─ LLM-assisted evidence extraction from top 20 papers
  └─ Score by: mechanistic coherence + evidence strength + safety compatibility

T2   (hours/pair):      Full evidence synthesis + trial design
  └─ Systematic literature review across all evidence types
  └─ Biomarker identification for patient stratification
  └─ Dose-indication analysis: what dose works for the target mechanism?
  └─ Trial design recommendation: Phase II design, endpoints, population
  └─ Competitive landscape: who else is working on this?
  └─ Output: full repurposing dossier with evidence chain
```

### What "Candidate" Means at Each Tier

**T0 candidate:** A drug-indication pair — one approved or shelved compound × one target disease — that passes basic mechanism overlap and safety compatibility. At scale across all approved drugs × all diseases, this is a very large space (20,000 × 10,000 = 200 million pairs). T0 reduces this to tractable scale quickly.

**T0.25 candidate:** A pair with computational evidence of mechanistic plausibility — either via protein interaction network proximity or transcriptomic signature reversal. These are the pairs where the biology says "this could work" before anyone reads a paper.

**T1 candidate:** A pair with mechanistic coherence AND evidence in the literature AND acceptable safety profile. Roughly: "there's a reason to think this works and nothing obvious would kill it."

**T2 candidate:** A pair ready for a repurposing dossier — full evidence synthesis, trial design, and competitive landscape analysis. Output that a clinical team or small biotech could use directly.

### Screening Funnel at Scale

**Example: longevity / healthspan target scan**
```
~4,500   approved small molecule drugs (FDA + EMA)
  × ~50    longevity-relevant targets/pathways (mTOR, AMPK, sirtuins, senolysis, etc.)
= ~225,000 drug-indication pairs

  └─ ~22,500   pass T0 mechanism overlap + safety filter (10%)
      └─ ~4,500    pass T0.25 network proximity + transcriptomic reversal (20%)
          └─ ~450     pass T1 deep mechanistic analysis + evidence threshold (10%)
              └─ ~45      pass T2 full evidence synthesis (10%)
                  └─ top 20-30 repurposing candidates with full dossiers
```

**Example: rare disease orphan indication scan**
```
~4,500   approved drugs
  × 1     specific rare disease target
= ~4,500  drug-indication pairs

  └─ ~450    pass T0 (10%)
      └─ ~90     pass T0.25 (20%)
          └─ ~18     pass T1 (20% — evidence bar lower for rare disease)
              └─ 3-8    pass T2 with full dossiers
```

---

## Instantiation Model

```
clinical-trial-repurposing-pipeline-core/   ← this repo (the template)
  pipeline_core.py
  db_utils.py
  receipt_system.py
  config_schema.py
  adapters/
    clinicaltrials_adapter.py       ← ClinicalTrials.gov API
    openfda_adapter.py              ← FDA drug approval + adverse events
    drugbank_adapter.py             ← DrugBank mechanism + target data
    chembl_adapter.py               ← ChEMBL bioactivity data
    pubmed_adapter.py               ← PubMed literature
    lincs_adapter.py                ← LINCS L1000 transcriptomic signatures
    disgenet_adapter.py             ← DisGeNET disease-gene associations
    string_adapter.py               ← STRING protein interaction network
    omim_adapter.py                 ← OMIM genetic disease database
    faers_adapter.py                ← FDA Adverse Event Reporting System
    openai_trials_adapter.py        ← OpenTrials / EU Clinical Trials Register

longevity-repurposing-pipeline/
  config.yaml                       ← mTOR/AMPK/sirtuin/senolysis targets
  longevity_repurposing.db
  FINDINGS.md

als-repurposing-pipeline/
  config.yaml                       ← TDP-43/FUS pathways, neurodegeneration
  als_repurposing.db
  FINDINGS.md

rare-disease-repurposing-pipeline/
  config.yaml                       ← specific orphan indication
  rare_disease.db
  FINDINGS.md

antimicrobial-resistance-repurposing-pipeline/
  config.yaml                       ← novel antibiotic mechanisms, resistance targets
  amr_repurposing.db
  FINDINGS.md
```

---

## Database Schema

```sql
-- Core tables
CREATE TABLE drugs (
    drug_id             TEXT PRIMARY KEY,   -- DrugBank ID e.g. 'DB00945'
    name                TEXT NOT NULL,
    generic_name        TEXT,
    brand_names         TEXT,               -- JSON array
    drug_type           TEXT,               -- 'small_molecule', 'biologic', 'peptide'
    status              TEXT,               -- 'approved', 'investigational', 'withdrawn'
    approval_date       TEXT,
    approved_indications TEXT,              -- JSON array of MeSH disease terms
    mechanism_of_action TEXT,               -- narrative
    pharmacodynamics    TEXT,
    half_life           TEXT,
    bioavailability     REAL,
    protein_binding     REAL,
    molecular_formula   TEXT,
    mw                  REAL,
    logp                REAL,
    smiles              TEXT,
    inchi_key           TEXT,

    -- Safety profile
    black_box_warnings  TEXT,               -- JSON array
    contraindications   TEXT,               -- JSON array
    serious_aes         TEXT,               -- JSON: AE → frequency
    pregnancy_category  TEXT,
    controlled_substance TEXT,

    -- Targets
    primary_targets     TEXT,               -- JSON: [{uniprot_id, gene_name, affinity}]
    all_targets         TEXT,               -- JSON: full polypharmacology profile
    pathway_ids         TEXT,               -- JSON: KEGG/Reactome pathway IDs

    source              TEXT,               -- 'drugbank', 'chembl', 'fda'
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE indications (
    indication_id       TEXT PRIMARY KEY,   -- MeSH ID or OMIM ID
    name                TEXT NOT NULL,
    mesh_id             TEXT,
    omim_id             TEXT,
    orphanet_id         TEXT,               -- for rare diseases
    icd10_code          TEXT,
    disease_genes       TEXT,               -- JSON: [{gene_name, uniprot_id, evidence}]
    pathway_ids         TEXT,               -- JSON: KEGG/Reactome pathway IDs
    go_terms            TEXT,               -- JSON: GO biological process terms
    transcriptomic_sig  TEXT,               -- JSON: disease signature gene expression
    prevalence          REAL,               -- patients worldwide
    unmet_need_score    REAL,               -- 0-1, higher = more unmet
    orphan_status       BOOLEAN,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trials (
    trial_id            TEXT PRIMARY KEY,   -- NCT number
    title               TEXT,
    status              TEXT,               -- 'completed', 'terminated', 'withdrawn', etc.
    phase               TEXT,               -- 'Phase 1', 'Phase 2', 'Phase 3', 'Phase 4'
    drug_id             TEXT REFERENCES drugs,
    indication_id       TEXT REFERENCES indications,
    start_date          TEXT,
    completion_date     TEXT,
    enrollment          INTEGER,
    primary_outcome     TEXT,
    result_summary      TEXT,               -- extracted from results section
    success             BOOLEAN,            -- null if no results
    termination_reason  TEXT,               -- if terminated early
    sponsor             TEXT,
    source              TEXT,               -- 'clinicaltrials_gov', 'euctr', 'isrctn'
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id             TEXT REFERENCES drugs,
    indication_id       TEXT REFERENCES indications,
    target_id           TEXT REFERENCES targets,

    -- T0 results
    t0_pass             BOOLEAN,
    t0_mechanism_overlap REAL,              -- 0-1 Jaccard overlap of pathway sets
    t0_safety_compatible BOOLEAN,
    t0_already_tried    BOOLEAN,            -- has this been in trials before?
    t0_reject_reason    TEXT,

    -- T0.25 results
    t025_pass           BOOLEAN,
    t025_network_proximity REAL,            -- drug target to disease gene shortest path
    t025_transcriptomic_score REAL,         -- LINCS L1000 reversal score
    t025_literature_cooccurrence INTEGER,   -- PubMed abstract co-occurrence count
    t025_failed_trial   BOOLEAN,            -- has this failed in a completed trial?
    t025_failed_trial_id TEXT,              -- NCT ID of failed trial if applicable

    -- T1 results
    t1_pass             BOOLEAN,
    t1_pathway_overlap  TEXT,               -- JSON: overlapping pathways with scores
    t1_polypharmacology TEXT,               -- JSON: relevant off-target effects
    t1_ae_profile       TEXT,               -- JSON: relevant adverse events from FAERS
    t1_evidence_papers  TEXT,               -- JSON: top supporting papers
    t1_evidence_score   REAL,               -- 0-1 composite evidence strength
    t1_mechanistic_score REAL,              -- 0-1 mechanistic coherence
    t1_safety_score     REAL,               -- 0-1 safety compatibility

    -- T2 results
    t2_pass             BOOLEAN,
    t2_evidence_summary TEXT,               -- narrative evidence synthesis
    t2_biomarkers       TEXT,               -- JSON: patient stratification biomarkers
    t2_dose_rationale   TEXT,               -- narrative dose selection justification
    t2_trial_design     TEXT,               -- JSON: recommended Phase II design
    t2_endpoints        TEXT,               -- JSON: primary + secondary endpoints
    t2_population       TEXT,               -- JSON: inclusion/exclusion criteria
    t2_competitive_landscape TEXT,          -- JSON: other drugs/companies in space
    t2_confidence       REAL,               -- 0-1 overall confidence in repurposing case
    t2_novelty          REAL,               -- 0-1 how novel is this (vs known repurposing)

    composite_score     REAL,               -- final ranking score
    tier_reached        INTEGER,
    run_date            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    machine_id          TEXT
);

CREATE TABLE targets (
    target_id           TEXT PRIMARY KEY,   -- e.g. 'longevity_mtor_axis'
    name                TEXT,
    description         TEXT,
    disease_context     TEXT,               -- target disease or disease family
    pathway_ids         TEXT,               -- JSON: relevant pathway IDs
    gene_set            TEXT,               -- JSON: key genes in target disease
    unmet_need          TEXT,               -- narrative description
    safety_exclusions   TEXT,               -- JSON: AE types incompatible with population
    population_context  TEXT,               -- JSON: target patient population constraints
    evidence_threshold  REAL,               -- minimum T1 evidence score to pass
    priority_mechanisms TEXT                -- JSON: highest-priority mechanisms to check
);

CREATE TABLE evidence (
    evidence_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER REFERENCES runs,
    drug_id             TEXT REFERENCES drugs,
    indication_id       TEXT REFERENCES indications,
    evidence_type       TEXT,               -- 'clinical', 'preclinical', 'epidemiological',
                                            --  'mechanistic', 'genetic', 'transcriptomic'
    source_type         TEXT,               -- 'paper', 'trial', 'case_report', 'database'
    source_id           TEXT,               -- PMID, NCT ID, etc.
    title               TEXT,
    year                INTEGER,
    strength            TEXT,               -- 'strong', 'moderate', 'weak', 'conflicting'
    direction           TEXT,               -- 'supporting', 'opposing', 'neutral'
    summary             TEXT,               -- LLM-extracted summary
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE findings (
    finding_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT,
    description         TEXT,
    drug_ids            TEXT,               -- JSON array
    indication_ids      TEXT,               -- JSON array
    statistical_support TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE receipts (
    receipt_id          TEXT PRIMARY KEY,
    machine_id          TEXT,
    batch_start         TIMESTAMP,
    batch_end           TIMESTAMP,
    n_pairs_processed   INTEGER,
    n_llm_calls         INTEGER,            -- LLM calls are cost, track separately
    llm_cost_usd        REAL,               -- track API spend
    status              TEXT,
    filepath            TEXT
);
```

---

## Config Schema

```yaml
# longevity-repurposing-pipeline/config.yaml — example

project:
  name: "longevity-repurposing-pipeline"
  application: "drug_repurposing"
  description: "Systematic scan of approved drugs for longevity/healthspan indications — mTOR, AMPK, senolysis, NAD+ pathways."
  version: "0.1.0"

target:
  id: "longevity_healthspan"
  disease_context: "aging_and_longevity"
  description: "Identify approved drugs with potential to extend healthspan via known longevity pathways"
  unmet_need: "No approved drug has a longevity/healthspan indication. Multiple pathways (mTOR, AMPK, sirtuins, senolysis) have strong mechanistic evidence."
  pathway_ids:
    - "hsa04150"       # mTOR signaling
    - "hsa04152"       # AMPK signaling
    - "hsa04210"       # Apoptosis (senolysis)
    - "hsa00760"       # Nicotinate/nicotinamide (NAD+)
    - "hsa04068"       # FoxO signaling
    - "hsa04066"       # HIF-1 signaling
    - "hsa04310"       # Wnt signaling (stem cell maintenance)
  gene_set:
    primary: ["MTOR", "AMPK", "SIRT1", "SIRT3", "FOXO3", "IGF1R", "TP53", "CDKN2A"]
    secondary: ["NAMPT", "PARP1", "NLRP3", "BCL2", "BCL-XL", "HMGB1", "IL6", "TNF"]
  population_context:
    age_range: [50, 85]
    exclude_conditions: ["active_cancer", "severe_renal_impairment"]
  safety_exclusions:
    - "severe_immunosuppression"           # mTOR inhibitors — too much for healthy aging
    - "teratogenicity"                     # not relevant but flag
    - "narrow_therapeutic_index"           # too risky for prevention indication
  evidence_threshold: 0.45                 # lower than disease treatment — prevention evidence is weaker
  priority_mechanisms:
    - "mTORC1_inhibition"
    - "AMPK_activation"
    - "senescent_cell_clearance"
    - "NAD_repletion"
    - "IGF1_pathway_reduction"

drug_universe:
  sources: ["drugbank", "chembl", "fda_approved"]
  drug_types: ["small_molecule"]           # exclude biologics for first pass
  status_filter: ["approved", "investigational_phase2+"]
  exclude_indications: []                  # don't exclude any — we want the full picture
  include_shelved: true                    # include Phase II/III failures — rich source

filters:
  t0:
    require_mechanism_pathway_overlap: true
    min_pathway_overlap_jaccard: 0.05      # at least one shared pathway term
    exclude_black_box_for_population: true
    exclude_active_trials_same_indication: true
    exclude_definitive_trial_failures: true  # Phase III failures with >1000 patients
    max_mechanism_distance: 3              # max hops in MeSH mechanism tree
  t025:
    network_proximity:
      max_shortest_path: 2                 # drug target within 2 hops of disease gene
      min_z_score: -1.5                    # network proximity z-score (negative = proximal)
    transcriptomic:
      min_reversal_score: 0.3              # LINCS L1000 signature reversal
      min_genes_matched: 10
    literature:
      min_cooccurrence: 3                  # PubMed abstract co-occurrences
    failed_trial_handling: "flag_not_exclude"  # flag failed trials, don't auto-exclude
  t1:
    min_evidence_score: 0.4
    min_mechanistic_score: 0.35
    min_safety_score: 0.5
    max_papers_to_extract: 20
    llm_model: "claude-sonnet-4-20250514"
    extract_biomarkers: true
    extract_dose_rationale: true
  t2:
    min_confidence: 0.5
    generate_trial_design: true
    trial_design_phase: "Phase_2"
    generate_competitive_landscape: true
    llm_model: "claude-opus-4-20250514"    # highest quality for final dossiers
    max_dossier_length_tokens: 4000

compute:
  workers: 8                               # T0/T0.25 are fast, high parallelism
  llm_workers: 3                           # T1/T2 LLM calls — rate limited
  batch_size: 1000
  llm_rate_limit_rpm: 50                   # Claude API rate limit
  checkpoint_interval: 100
  cache_llm_responses: true                # LLM calls are expensive — cache everything

output:
  db_path: "longevity_repurposing.db"
  receipts_dir: "receipts/"
  results_dir: "results/"
  top_n: 30
  export_dossiers: true                    # full PDF dossiers for top candidates
  export_evidence_table: true              # CSV of all evidence items
```

---

## Pipeline Scripts

```
# Core pipeline
pipeline_core.py                  — 4-tier funnel, config-driven, receipt output
db_utils.py                       — SQLite layer (RepurposingDB class)
config_schema.py                  — Pydantic config validation
receipt_system.py                 — JSON receipts, LLM cost tracking
correlation_scanner.py            — Automated cross-candidate findings

# Data ingestion
adapters/
  clinicaltrials_adapter.py       — ClinicalTrials.gov v2 API, bulk download
  openfda_adapter.py              — FDA drug label, approval, FAERS APIs
  drugbank_adapter.py             — DrugBank XML/API: targets, mechanisms, safety
  chembl_adapter.py               — ChEMBL bioactivity, target, mechanism data
  pubmed_adapter.py               — PubMed E-utilities, abstract bulk fetch
  lincs_adapter.py                — LINCS L1000 signature database (clue.io)
  disgenet_adapter.py             — DisGeNET disease-gene association scores
  string_adapter.py               — STRING PPI network (protein interaction)
  omim_adapter.py                 — OMIM genetic disease + gene associations
  faers_adapter.py                — FDA Adverse Event Reporting System
  kegg_adapter.py                 — KEGG pathway membership
  reactome_adapter.py             — Reactome pathway analysis
  opentargets_adapter.py          — Open Targets Platform (disease-target evidence)
  orphanet_adapter.py             — Orphanet rare disease database

# T0 — mechanism overlap + basic safety
compute/
  mechanism_overlap.py            — Jaccard overlap of pathway/MeSH term sets
  safety_filter.py                — Black box warnings, contraindication matching
  trial_history_checker.py        — ClinicalTrials.gov lookup for prior attempts
  mesh_distance.py                — MeSH tree distance for mechanism proximity

# T0.25 — network proximity + transcriptomics
compute/
  network_proximity.py            — Drug target → disease gene shortest path (STRING)
  lincs_scorer.py                 — Transcriptomic signature reversal (LINCS L1000)
  literature_cooccurrence.py      — PubMed abstract co-occurrence statistics
  failed_trial_classifier.py      — Classify trial failures: indication vs drug vs dose

# T1 — deep mechanistic analysis + evidence extraction
compute/
  pathway_analyzer.py             — KEGG/Reactome enrichment, pathway overlap depth
  polypharmacology_scorer.py      — Off-target effect relevance scoring
  faers_miner.py                  — Adverse event signal mining (disproportionality)
  evidence_extractor.py           — LLM-assisted evidence extraction from papers
  evidence_scorer.py              — Evidence strength + direction scoring

# T2 — full evidence synthesis + trial design
compute/
  evidence_synthesizer.py         — Systematic review synthesis via LLM
  biomarker_identifier.py         — Patient stratification biomarker extraction
  dose_analyzer.py                — Dose-response analysis from existing data
  trial_designer.py               — Phase II trial design generation
  competitive_landscape.py        — Who else is in this space?
  dossier_generator.py            — Full repurposing dossier (Markdown → PDF)

# Remote compute
merge_receipts.py                 — Ingest receipts, LLM cost accounting
batch_runner.py                   — Distributed batch launcher

# Analysis
rank_candidates.py                — Composite scoring, final ranking
mechanism_clustering.py           — Cluster candidates by mechanism class
cross_indication_analysis.py      — Find drugs with multiple repurposing signals
findings_generator.py             — Cross-candidate pattern detection
validate_pipeline.py              — Known repurposing recovery test
```

---

## Key Design Decisions

**Why network proximity at T0.25 rather than simple keyword matching?**
Drug-disease keyword co-occurrence in PubMed is noisy — papers often mention drugs and diseases in the same abstract for reasons unrelated to therapeutic activity. Network proximity (shortest path between drug primary target and disease-associated genes in the STRING PPI network) is mechanistically grounded. A drug with its primary target 1 hop from a key disease gene is a plausible repurposing candidate regardless of whether anyone has written a paper about it yet. This is the computational equivalent of the "gap finding" step in Athanor — finding connections that exist in the network but haven't been articulated in the literature.

**Why LINCS L1000 transcriptomic reversal at T0.25?**
LINCS L1000 has transcriptomic profiles for ~20,000 compounds across multiple cell lines — the gene expression signature each compound induces. The repurposing hypothesis is: a drug that reverses the transcriptomic signature of a disease (makes sick cells look more like healthy cells at the gene expression level) has therapeutic potential. This approach predicted sirolimus for progeria before any clinical evidence existed and has multiple validation examples. It's imperfect but provides orthogonal signal to network proximity — two independent computational methods agreeing strongly increases confidence.

**Why include shelved and failed compounds?**
Failed Phase II and Phase III trials are the richest source of repurposing candidates. A drug can fail for many reasons unrelated to its mechanism: wrong indication, wrong patient population, wrong dose, wrong endpoint, wrong timing. Rofecoxib (Vioxx) was withdrawn for cardiovascular risk but the COX-2 inhibition mechanism may be valuable in other contexts. Thalidomide failed catastrophically in pregnancy but became a successful multiple myeloma treatment. Systematic scanning of shelved compounds with the benefit of 20 years of subsequent disease biology knowledge is one of the highest-value applications of this pipeline.

**Why flag rather than exclude prior trial failures at T0.25?**
A prior Phase II failure at 50mg might be irrelevant if the target indication requires a different dose, a biomarker-selected population, or a combination regimen. The pipeline flags failed trials and extracts the failure reason at T1 — if the failure was "wrong dose" or "unselected population" and the current candidate design addresses those issues, the failure is informative rather than disqualifying. Hard exclusion loses valuable candidates.

**Why LLM-assisted evidence extraction at T1?**
The evidence supporting a repurposing hypothesis is scattered across mechanistic papers, case reports, epidemiological studies, and animal models — none of which are structured in a database. Automated extraction of evidence type, direction, and strength from paper abstracts is the only scalable approach. The LLM is doing structured NLP (evidence type classification, direction classification, strength assessment) not creative generation — this is a well-defined extraction task with low hallucination risk when constrained to specific structured output fields. Caching all LLM responses is essential for cost management.

**Why track LLM API cost in the receipt system?**
Unlike biochem or materials pipelines where compute cost is CPU/GPU hours, this pipeline's primary cost is LLM API calls at T1 and T2. A T1 evidence extraction pass on 20 papers costs ~$0.10-0.30 per candidate. At 450 T1 candidates, that's $45-135 per full run. T2 dossier generation at ~$0.50-1.00 per candidate × 45 candidates = $22-45. Total run cost: ~$100-200. Not negligible — tracking cost per candidate enables budget management and cost-benefit analysis (is this target worth the API spend?).

**Why separate the evidence table as a first-class database object?**
The evidence table is where the scientific value accumulates. A repurposing dossier is only as good as its evidence chain. By storing each evidence item (paper, trial result, case report, database entry) as a separate database row with type, direction, strength, and source, you get: (a) transparent evidence chains for every candidate, (b) the ability to re-rank candidates when new evidence appears without re-running the full pipeline, (c) cross-candidate evidence analysis (the same paper appears as evidence for multiple candidates — that's a finding).

---

## The Athanor Relationship — What's Real vs. Planned

**What Athanor currently does** (from the actual README): literature mapper → gap finder → hypothesis generator → critic. Domain-agnostic, workspace/domain config-driven, 69 tests, working CLI.

**Planned integration** (not yet implemented): Athanor's gap finder could identify underexplored drug-disease mechanism pairs and pass them as repurposing hypotheses directly into this pipeline for systematic evidence scanning. The hypothesis generator output format is compatible with the T0 config schema — an Athanor hypothesis becomes a drug-indication pair to screen.

**The current workflow without integration:** Run Athanor on a domain (e.g. longevity biology), identify gap hypotheses ("compound X mechanism poorly studied in aging context"), manually translate those into repurposing candidates, add to the pipeline config. Not automated yet but the conceptual pipeline is: Athanor generates candidates → this pipeline screens them → ranked dossiers returned.

This integration is worth building but is explicitly future work, not current state.

---

## The Failed Trial Database — A Special Asset

ClinicalTrials.gov contains 480,000+ trials including thousands of terminations and failures. This dataset is underused computationally. The pipeline builds a structured failed trial database as a side effect of data ingestion:

```sql
-- Derived from the trials table
SELECT t.trial_id, t.drug_id, t.indication_id, t.phase,
       t.termination_reason, t.result_summary,
       d.mechanism_of_action, d.primary_targets
FROM trials t
JOIN drugs d ON t.drug_id = d.drug_id
WHERE t.status IN ('terminated', 'withdrawn', 'completed')
AND t.success = FALSE
```

The termination reason field is narrative text — categorizing it (wrong dose, wrong population, safety signal, efficacy failure, commercial decision, enrollment failure) requires NLP. The pipeline does this classification at ingestion and stores the structured category alongside the narrative. This classified failed trial database is itself a publishable scientific asset — it doesn't exist anywhere in structured form today.

**Why failed trials are repurposing gold:**
- Wrong dose: 40% of failures — dose may be right for a different indication
- Wrong population: 25% — biomarker selection could rescue the compound
- Commercial decision: 15% — drug works but market is too small (orphan opportunity)
- Safety in specific population: 10% — safe in different population
- Efficacy: <10% of failures are clean mechanism failures

Only clean mechanism failures (compound doesn't do what the biology predicts) are truly informative negative results. Everything else is repurposing opportunity.

---

## Application-Specific Notes

### Longevity / Healthspan
The longevity repurposing space is unusual because there is no approved indication — you're screening for drugs to use in healthy or near-healthy aging populations for prevention, not treatment. This shifts several pipeline parameters:

- Evidence threshold is lower — prevention trials are rare so mechanistic + preclinical evidence gets more weight
- Safety bar is higher — a drug for a healthy 60-year-old must have an extremely clean profile
- Dose is often lower — longevity mechanisms (mTOR inhibition via rapamycin) are active at sub-immunosuppressive doses not studied in approved indications
- Endpoints are novel — biomarkers of biological age (epigenetic clocks, inflammatory markers) rather than disease incidence

Known repurposing candidates in this space (validation set for the pipeline): metformin (TAME trial), rapamycin/rapalogs, acarbose (ITP results), spermidine, NMN/NR, senolytics (dasatinib + quercetin). The pipeline should recover all of these at T1 or T2 to validate calibration.

### ALS / Neurodegenerative Disease
ALS is exceptionally drug-resistant — riluzole and edaravone are the only approved treatments and both have modest effects. The repurposing opportunity comes from the mechanistic complexity: TDP-43 aggregation, neuroinflammation, mitochondrial dysfunction, and glutamate excitotoxicity are all implicated, providing multiple independent mechanism angles.

Key consideration: CNS penetration is required. The T0 filter must check blood-brain barrier penetration (LogBB, P-gp substrate status) explicitly for CNS indications — a mechanistically perfect compound that doesn't cross the BBB is useless here.

### Rare Disease / Orphan Indications
Rare diseases have a fundamentally different evidence structure — small patient populations mean clinical trial evidence is sparse and often underpowered. The pipeline adjusts by:
- Lowering evidence threshold at T1 (mechanistic + preclinical evidence more heavily weighted)
- Including case reports as evidence (N=1-5 case series count in rare disease)
- Checking EMA compassionate use and named patient use records
- The Orphan Drug Act creates strong regulatory incentives — the competitive landscape analysis is especially important here

The FDA's Rare Diseases Repurposing Database and NCATS TRND program are primary sources for known activity data in this context.

### Antimicrobial Resistance
The AMR repurposing space has a specific structure: you're looking for approved drugs with antibiotic mechanism adjuvant activity (potentiating existing antibiotics against resistant organisms) or direct activity against resistant strains via non-standard mechanisms.

Key sources not in the general adapter list: PATRIC for bacterial target information, CARD (Comprehensive Antibiotic Resistance Database) for resistance mechanism annotation, ESKAPE pathogen databases for priority targets.

Key T0 addition: check for existing use as adjuvant in combination regimens — many repurposing opportunities in AMR are combination approaches (existing antibiotic + repurposed drug) rather than monotherapy.

---

## Validation Strategy

**Known repurposing recovery test** — the mandatory first step. Take 20-30 validated repurposing successes (drugs approved for a second indication after initial approval elsewhere), process through T0-T0.25, check that they are enriched in survivors. The repurposing success rate should be >80% at T0.25. Examples: sildenafil (hypertension → erectile dysfunction → pulmonary hypertension), thalidomide (morning sickness → multiple myeloma), methotrexate (cancer → rheumatoid arthritis), finasteride (BPH → hair loss).

**Anti-validation: known failures** — take 20-30 drug-indication pairs that have failed Phase III with clean mechanism-level failure (not dose or population issues). These should be filtered at T1 or T2. If they're passing, the mechanistic scoring is too lenient.

**Correlation with Open Targets evidence scores** — for T1 candidates, compare the pipeline's evidence score against Open Targets association scores for the same drug-disease pair. High correlation validates that the pipeline's evidence extraction is calibrated to existing gold-standard assessments.

**Prospective validation** — the hardest test. Identify 5-10 T2 candidates that have not yet entered trials, track over 2-3 years whether they enter trials or receive attention. This is the long-term validation of pipeline value but isn't possible at launch.

---

## Findings & Correlation Scanner

`correlation_scanner.py` surfaces cross-candidate patterns:

**Mechanism class enrichment** — which drug mechanisms (kinase inhibitors, HDAC inhibitors, anti-inflammatory, etc.) are disproportionately enriched in T2 survivors for a given target disease. Often the most actionable finding — tells you which drug class deserves a focused follow-up campaign.

**Polypharmacology patterns** — drugs that hit multiple targets in the target disease pathway simultaneously score better than drugs that hit one target at high specificity. The scanner identifies which off-target effects are systematically beneficial for the target indication.

**Failed trial rescue patterns** — which termination reason categories are most frequently associated with T2 survivors. If 60% of T2 candidates were terminated for "commercial decision" (market too small), that's a finding — the biology was fine, the economics were wrong.

**Dose gap analysis** — comparing approved indication doses to the dose range that achieves target mechanism activity. If 80% of longevity candidates require sub-therapeutic doses of their approved indication, that's a systematic finding about the dose-mechanism landscape.

**Evidence type distribution** — what fraction of T2 evidence is clinical vs preclinical vs mechanistic? If the pipeline is systematically relying on preclinical evidence (which translates poorly), that's a calibration flag.

**Cross-indication signals** — drugs that score well for multiple independent target indications simultaneously are prioritized. A drug that's a T2 candidate for longevity AND ALS AND metabolic syndrome is more interesting than one that scores for longevity alone.

---

## Known Pitfalls & Gotchas

| # | Issue | Impact |
|---|-------|--------|
| — | ClinicalTrials.gov data quality is inconsistent — result fields often empty even for completed trials | Missing trial outcome data |
| — | DrugBank free API has limited target data — full target/mechanism requires licensed access | Incomplete T0 mechanism overlap |
| — | LINCS L1000 covers ~20,000 compounds but many approved drugs are missing — check coverage before relying on transcriptomic score | Silent T0.25 misses |
| — | Network proximity depends strongly on STRING confidence threshold — use >700 score or proximity is noise | T0.25 false positives at low confidence |
| — | FAERS adverse event data has massive reporting bias — spontaneous reports are not incidence rates | AE frequency overestimation |
| — | LLM evidence extraction hallucinates at low rates but nonzero — always store source PMID and verify T2 dossiers | False evidence items |
| — | "Repurposing" vs "combination" is often ambiguous — a drug that's only active with another drug needs flagging | Misleading standalone candidate ranking |
| — | MeSH term coverage for rare diseases is sparse — orphan indications may have no MeSH tree overlap with mechanism terms even when relevant | False T0 failures for rare diseases |
| — | ClinicalTrials phase definitions are inconsistently applied — some "Phase 2" trials are effectively Phase 1 | Incorrect trial history classification |
| — | Open Targets evidence scores change with database updates — pin database version for reproducibility | Non-reproducible T1 scores across pipeline versions |

---

## Quick Start

```bash
git clone https://github.com/sethc5/clinical-trial-repurposing-pipeline-core.git
cd clinical-trial-repurposing-pipeline-core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set API keys
cp .env.example .env
# Add: ANTHROPIC_API_KEY, DRUGBANK_API_KEY (optional), OPENTARGETS_API_KEY

# Validate config
python config_schema.py --validate path/to/config.yaml

# Mandatory first step: known repurposing recovery test
python validate_pipeline.py \
  --config config.yaml \
  --known_repurposing reference/validated_repurposing_pairs.csv

# Run T0 + T0.25 only (fast, no LLM calls)
python pipeline_core.py --config config.yaml --tier 025 -w 8

# Run full pipeline (includes LLM calls at T1/T2)
python pipeline_core.py --config config.yaml -w 4 --llm-workers 3

# Merge receipts
python merge_receipts.py --list
python merge_receipts.py

# Generate dossiers for top candidates
python dossier_generator.py --config config.yaml --top 10

# Generate findings report
python findings_generator.py --config config.yaml
```

---

## Tool Stack

| Layer | Tool | Why |
|-------|------|-----|
| Drug data | `drugbank` (XML/API) | Most complete drug mechanism + target data |
| Bioactivity | `chembl_webresource_client` | ChEMBL target + bioactivity |
| Trial data | `pytrials` | ClinicalTrials.gov Python wrapper |
| FDA data | `openfda` | Drug labels, adverse events, approvals |
| Literature | `biopython.Entrez` | PubMed bulk access |
| Disease-gene | `disgenet2r` / REST API | DisGeNET associations |
| PPI network | `string_db` REST API | STRING protein interactions |
| Pathway analysis | `gseapy` | KEGG/Reactome enrichment |
| Pathway data | `bioservices` | KEGG, Reactome, UniProt REST wrappers |
| Transcriptomics | `cmapPy` | LINCS L1000 / clue.io access |
| Open Targets | `opentargets` Python client | Disease-target evidence platform |
| NLP / extraction | `anthropic` (Claude) | LLM evidence extraction at T1/T2 |
| Network analysis | `networkx` | PPI shortest path, centrality |
| Stats | `scipy.stats` | Disproportionality analysis (FAERS) |
| Data frames | `pandas` | Batch processing |
| Config | `pydantic` | Schema validation |
| CLI | `typer` | Clean CLI |
| Progress | `rich` | Readable output |
| Database | `sqlite3` (stdlib) | Zero infrastructure |
| PDF generation | `reportlab` or `weasyprint` | T2 dossier PDF output |

---

## Instantiation Roadmap

| Repo | Target Disease / Context | Status |
|------|-------------------------|--------|
| [longevity-repurposing-pipeline](https://github.com/sethc5/longevity-repurposing-pipeline) | Healthspan / aging pathways | 🔶 In development |
| als-repurposing-pipeline | ALS / TDP-43 neurodegeneration | 📋 Planned |
| rare-disease-repurposing-pipeline | Orphan indications (configurable) | 📋 Planned |
| amr-repurposing-pipeline | Antibiotic resistance adjuvants | 📋 Planned |
| fibrosis-repurposing-pipeline | Liver / lung / kidney fibrosis | 📋 Planned |

---

## Relationship to Other Pipelines

```
Athanor (literature gap finder + hypothesis generator)
  [planned integration: Athanor hypothesis → repurposing candidate]
    │
    └── clinical-trial-repurposing-pipeline-core
          ├── longevity-repurposing     ← directly feeds longevity research mission
          ├── als-repurposing           ← complements als-pipeline (biochem)
          └── rare-disease-repurposing

biochem-pipeline-core (novel compound screening)
    │
    └── Complements repurposing: biochem finds novel compounds,
        repurposing finds approved ones. Both feed the same
        disease indication targets. They are parallel, not sequential.
```

The repurposing pipeline and biochem-pipeline-core address the same ultimate question ("what treats this disease?") from different directions. Repurposing is faster and cheaper to act on (safety data exists); biochem is slower but opens the full chemical space. Running both on the same target disease gives the most complete picture.

---

## Evidence Ledger (Policy Justification)

This repo includes an explicit policy evidence ledger under `reference/` so gate and profile decisions are auditable:

- `reference/decisions/` — decision memos tied to config changes
- `reference/claims/` — claim IDs mapped to sources
- `reference/sources/semantic_scholar/` — fetched citation bundles

Semantic Scholar pull script:

```bash
python3 scripts/fetch_semantic_scholar_refs.py \
  --query "drug repurposing progress challenges recommendations" \
  --query "network-based drug repurposing method review" \
  --tag clinical_policy_refresh \
  --limit 8
```

---

## Suite Orchestration (MVP)

Supervised cross-repo orchestration is available via:
- `scripts/suite_orchestrator.py`
- `configs/suite_orchestrator.yaml`
- `configs/suite_backlog.example.yaml`
- `docs/SUITE_ORCHESTRATION.md`

This drives staged genomics -> biochem -> clinical flows with human review checkpoints.

Backend switching is profile-driven:
- `python3 scripts/suite_orchestrator.py --compute-profile local run-once`
- `python3 scripts/suite_orchestrator.py --compute-profile hetzner run-once --execute`

OpenRouter budget presets:
- `configs/openrouter_budget_profiles.yaml`
- `scripts/apply_openrouter_profile.py`

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Highest value contributions:

1. **New disease instantiations** — write a config YAML, run known repurposing validation, open a PR
2. **Database adapters** — particularly OpenTargets (well-maintained, comprehensive) and WHO VigiBase (global adverse event data, better than FAERS alone)
3. **Failed trial classifier** — NLP model to categorize ClinicalTrials.gov termination reasons into structured categories. This is currently the weakest part of the pipeline
4. **LINCS L1000 coverage expansion** — the LINCS database is incomplete for many approved drugs; connecting to additional transcriptomic datasets (GEO, ArrayExpress) would expand T0.25 coverage
5. **Bug documentation** — especially ClinicalTrials.gov data quality issues and DrugBank API inconsistencies
6. **Validation datasets** — curated known repurposing successes + confirmed mechanism failures with sources

---

## References

- [ClinicalTrials.gov](https://clinicaltrials.gov/) — 480,000+ registered trials, v2 API
- [OpenFDA](https://open.fda.gov/) — Drug labels, adverse events, approvals
- [DrugBank](https://www.drugbank.com/) — Drug mechanisms, targets, interactions
- [ChEMBL](https://www.ebi.ac.uk/chembl/) — Bioactivity database
- [DisGeNET](https://www.disgenet.org/) — Disease-gene associations
- [STRING](https://string-db.org/) — Protein interaction network
- [LINCS L1000](https://lincsproject.org/) — Transcriptomic drug signatures
- [Open Targets](https://www.opentargets.org/) — Disease-target evidence platform
- [FAERS](https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers) — FDA adverse event reports
- Pushpakom et al. (2019) — "Drug repurposing: progress, challenges and recommendations" — comprehensive review
- Corsello et al. (2020) — "Discovering the anticancer potential of non-oncology drugs by systematic viability profiling" — PRISM repurposing dataset
- Himmelstein et al. (2017) — "Systematic integration of biomedical knowledge prioritizes drugs for repurposing" — network proximity method validation
- [biochem-pipeline-core](https://github.com/sethc5/biochem-pipeline-core) — parallel novel compound screening
- [cytools_project](https://github.com/sethc5/cytools_project) — the pipeline architecture origin
- [athanor](https://github.com/sethc5/athanor) — literature gap finder (planned upstream integration)

## License

MIT
