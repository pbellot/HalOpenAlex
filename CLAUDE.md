# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This project analyses HAL (Hyper Articles en Ligne) and OpenAlex publication data for CNRS laboratories. It cross-references publications from the HAL open archive API with the OpenAlex bibliographic database to measure coverage and enrich records with ORCID identifiers.

## Environment

**Conda environment:** `EtudePublicationsHALOA`  
**Jupyter kernel:** `EtudePublicationsHALOA` (registered as `python3` in that env)

Activate before working:
```bash
conda activate EtudePublicationsHALOA
```

Launch Jupyter:
```bash
jupyter lab
# or
jupyter notebook
```

Key packages: `requests`, `pandas` (3.x), `tqdm`, `pickle`.

## Notebooks

### `hal_publications.ipynb` — Main analysis pipeline

Sequential workflow — cells must be run in order:

1. **Data loading** (cells 2–3): loads from CSV cache (`hal_publications_par_labo.csv`) or pickle checkpoint (`notebook_state.pkl`) to avoid re-fetching
2. **Lab list** (cell 5): `LABS` dict maps lab acronym → set of HAL `structId` values (multiple IDs per lab handle aliases)
3. **HAL API fetch** (cells 8–10): queries `https://api.archives-ouvertes.fr/search/` by `structId_i`, years 2015–2025
4. **ORCID enrichment** (cells 14–16): two-pass enrichment via HAL `ref/author` endpoint — first by `idHal`, then by name
5. **Deduplication** (cells 21–23): drops duplicate `hal_id` rows to produce `df_unique`
6. **OpenAlex crossmatch** (cells 25–28): two-pass matching — DOI batch lookup then title fuzzy match — against `https://api.openalex.org/works`
7. **Coverage stats** (cells 29–43): per-lab, per-year, per-doctype, per-language coverage tables, exported to CSV
8. **Lab/year author comparison** (cells 47–61): compares HAL vs OpenAlex author lists for a specific lab/year (`LABO_CIBLE`, `ANNEE_CIBLE`)
9. **Checkpoint save/load** (cells 3 and 65): `notebook_state.pkl` stores intermediate Python dicts between sessions

### `ROROrcidsLabos.ipynb` — Lab identifiers & ORCID stats

1. **Lab list** (cell 1): `ABS` dict, same structure as `LABS` above
2. **Lab identifier lookup** (cells 4–5): queries `https://api.hal.science/ref/structure/` to collect ROR, RNSR, ISNI, IdRef per lab → `labo_identifiants.csv`
3. **Author/ORCID collection** (cells 6–8): resolves struct aliases, fetches all authors for a given `YEAR` (default 2024), enriches with `ref/author` to get ORCID
4. **ORCID employment verification** (cells 9–10): calls `https://pub.orcid.org/v3.0` to get current employer from each ORCID profile
5. **Stats export** (cells 11–13): per-lab ORCID coverage, by employer, by role → `labo_stats_orcid_2024.csv`, `labo_stats_orcid_par_employeur_2024.csv`, `labo_stats_orcid_par_fonction_2024.csv`

## Key data files

| File | Description |
|------|-------------|
| `hal_publications_par_labo.csv` | Raw HAL records per lab (with ORCID, not deduplicated) |
| `hal_publications_uniques.csv` | HAL records deduplicated by `hal_id` |
| `hal_openalex_uniques.csv` | Above + OpenAlex match results (`in_openalex`, `match_method`, `openalex_id`) |
| `notebook_state.pkl` | Python checkpoint: intermediate dicts for resuming without re-fetching |
| `labo_identifiants.csv` | Lab → ROR / RNSR / ISNI identifiers |
| `couverture_openalex_par_labo.csv` | Summary OpenAlex coverage rates per lab |

## APIs used

- **HAL search:** `https://api.archives-ouvertes.fr/search/` (also `https://api.hal.science/search/`)
- **HAL ref/author:** `https://api.archives-ouvertes.fr/ref/author/` — ORCID enrichment by `idHal`
- **HAL ref/structure:** `https://api.hal.science/ref/structure/` — lab identifiers
- **OpenAlex works:** `https://api.openalex.org/works` — DOI batch + title fuzzy match
- **ORCID public API:** `https://pub.orcid.org/v3.0` — employment verification

All API calls include polite sleep delays (`time.sleep`) to respect rate limits. OpenAlex requests include a `mailto` parameter (set in `OPENALEX_URL` params).

## Lab identifiers

Each lab in `LABS`/`ABS` maps to one or more HAL `structId` integers. Multiple IDs are needed because HAL uses numeric `docid` for structures and labs may have aliases (old/new IDs). The `resolve_valid_struct_ids()` function in `ROROrcidsLabos.ipynb` handles alias resolution by checking `numFound` and filtering suspect IDs.
