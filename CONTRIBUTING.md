# Contributing to clinical-trial-repurposing-pipeline-core

Thank you for your interest in contributing! This document describes the highest-value
contributions and the standards expected for each.

---

## High-Value Contribution Areas

### 1. New Disease Instantiations
The most immediately useful contributions are new instantiation repositories that use this
core to screen drugs for specific disease verticals.

To create one:
1. Fork or copy the `_template_instantiation/` folder (if provided).
2. Create a new GitHub repo named `{disease}-repurposing-pipeline`.
3. Add a `config.yaml` pointing to this core.
4. Run `validate_pipeline.py` first to confirm ≥80% recovery of known pairs.
5. Document your target disease gene list and data sources in the repo README.

---

### 2. New Database Adapters (`adapters/`)

Priority targets:
- **WHO VigiBase** — pharmacovigilance AE signal database (requires WHO licence)
- **TTD (Therapeutic Target Database)** — alternative target source
- **ClinVar** — genetic variant → disease associations
- **OpenCravat** — multi-database variant annotation

Adapter requirements:
- Subclass nothing; plain class with `__init__(self, config)` and typed methods.
- Return plain Python dicts/lists (no framework objects).
- Cache API responses in `.cache/{adapter_name}/` with SHA256-keyed filenames.
- Respect rate limits with `time.sleep()` and exponential backoff.
- Implement a `ping()` method that returns `True` if the data source is reachable.
- Add full docstrings including example return shapes.
- Write at least one unit test in `tests/test_{adapter_name}.py` using `responses` mocking.

---

### 3. Failed Trial Classifier NLP (`compute/failed_trial_classifier.py`)

Current implementation uses regex keyword rules. Priority improvements:
- **Fine-tuned classifier** on labeled ClinicalTrials.gov termination reason text.
- **LLM classification** with structured output for ambiguous cases.
- Expand the `is_rescuable` logic: distinguish "wrong dose" from "wrong patient population"
  as these have different repurposing implications.
- Add a feedback loop: fetch actual trial publications via PubMed to verify the
  classifier's termination reason labels.

---

### 4. LINCS Coverage Expansion (`adapters/lincs_adapter.py`)

Current LINCS adapter covers L1000 via clue.io API. Improvements:
- Add support for loading `.gctx` compound signature files locally via `cmapPy`.
- Implement compound signature similarity (CMap score) in addition to reversal scoring.
- Add signatures from JUMP-CP (cell painting morphological profiles).
- Extend to PRISM drug sensitivity profiles.

---

### 5. Pathway Enrichment Enhancements (`compute/pathway_analyzer.py`)

- Add WikiPathways as a third source (open, frequently updated).
- Implement gene set enrichment analysis (GSEA pre-rank) via `gseapy`.
- Cache gene set libraries locally to avoid repeated API calls.

---

## Code Standards

- **Python ≥ 3.10** required (use `match`, `X | Y` union types freely).
- **Type hints** on all public function signatures.
- **Docstrings** in Google style for all public classes and functions.
- **Pydantic v2** for any new config or data schema classes.
- **No global state** — pass `config` explicitly; adapters may hold an internal cache dict.
- All new files must pass `ruff check` with default settings.
- Do not introduce new mandatory dependencies without discussion; optional deps are fine
  if guarded with `try/except ImportError`.

---

## Running Tests

```bash
pip install -r requirements.txt pytest responses
pytest tests/ -v
```

The test suite includes:
- `tests/test_validate_pipeline.py` — known pair recovery (integration)
- `tests/test_config_schema.py` — config validation edge cases
- Per-adapter mock tests

---

## Commit Message Format

```
<type>(<scope>): <short description>

<body if needed>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
Scopes: `adapter`, `compute`, `pipeline`, `config`, `docs`

Example:
```
feat(adapter): add WHO VigiBase pharmacovigilance adapter

Implements VigiBaseAdapter with get_ae_signal() and compute_ic() methods.
Requires WHO API licence key in VIGIBASE_API_KEY env var.
```

---

## Pull Request Checklist

- [ ] New tests added and passing
- [ ] `validate_pipeline.py` still passes (≥80% recovery)
- [ ] Type hints on all new public functions
- [ ] Docstrings updated
- [ ] `.env.example` updated if new API keys introduced
- [ ] `requirements.txt` updated if new dependencies added (optional deps commented out)
- [ ] CONTRIBUTING.md updated if new contribution area introduced
