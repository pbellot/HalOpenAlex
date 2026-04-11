# HalOpenAlex

Analyse croisée des publications HAL et OpenAlex pour les laboratoires du CNRS.

Ce projet interroge l'API HAL (Hyper Articles en Ligne) pour collecter les publications de laboratoires CNRS, les enrichit avec les identifiants ORCID des auteurs, puis mesure leur couverture dans la base bibliographique [OpenAlex](https://openalex.org).

## Objectifs

- **Couverture OpenAlex** : quelle proportion des publications déposées dans HAL se retrouve dans OpenAlex ? Par laboratoire, par année, par type de document, par langue.
- **Enrichissement ORCID** : associer un ORCID à chaque auteur à partir du référentiel HAL.
- **Comparaison des auteurs** : confronter les listes d'auteurs HAL et OpenAlex pour un laboratoire et une année donnés.
- **Identifiants des laboratoires** : collecter ROR, RNSR, ISNI et IdRef pour chaque laboratoire via l'API HAL.

## Notebooks

### [`hal_publications.ipynb`](hal_publications.ipynb) — Pipeline principal

| Étape | Description |
|-------|-------------|
| Chargement | Depuis le cache CSV ou le checkpoint pickle pour éviter de re-télécharger |
| Collecte HAL | Interrogation par `structId_i`, années 2015–2025 |
| Enrichissement ORCID | Deux passes via `ref/author` : par `idHal` puis par nom |
| Dédoublonnage | Suppression des doublons sur `hal_id` → `df_unique` |
| Croisement OpenAlex | Deux passes : par DOI (batch) puis par titre (fuzzy match) |
| Statistiques | Taux de couverture par labo / année / type / langue, exportés en CSV |
| Comparaison auteurs | HAL vs OpenAlex pour un labo/année cible (`LABO_CIBLE`, `ANNEE_CIBLE`) |

### [`ROROrcidsLabos.ipynb`](ROROrcidsLabos.ipynb) — Identifiants & statistiques ORCID

| Étape | Description |
|-------|-------------|
| Identifiants des labos | ROR, RNSR, ISNI, IdRef via `api.hal.science/ref/structure/` |
| Collecte auteurs | Résolution des alias de `structId`, fetch des auteurs pour une année |
| Vérification ORCID | Appel à `pub.orcid.org/v3.0` pour récupérer l'employeur actuel |
| Export stats | Couverture ORCID par labo, par employeur, par rôle |

## Installation

```bash
conda activate EtudePublicationsHALOA
jupyter lab
```

Dépendances principales : `requests`, `pandas` (3.x), `tqdm`.

## Fichiers de données

| Fichier | Contenu |
|---------|---------|
| `hal_publications_par_labo.csv` | Publications HAL brutes par labo (avec ORCID, non dédoublonnées) |
| `hal_publications_uniques.csv` | Publications dédoublonnées sur `hal_id` |
| `hal_openalex_uniques.csv` | Idem + résultats du croisement OpenAlex (`in_openalex`, `match_method`, `openalex_id`) |
| `couverture_openalex_par_labo.csv` | Taux de couverture OpenAlex par laboratoire |
| `labo_identifiants.csv` | Identifiants ROR / RNSR / ISNI par laboratoire |
| `labo_stats_orcid_2024.csv` | Statistiques ORCID par labo (2024) |
| `notebook_state.pkl` | Checkpoint Python pour reprendre sans re-télécharger |

## APIs utilisées

| API | Usage |
|-----|-------|
| `api.archives-ouvertes.fr/search/` | Collecte des publications par `structId_i` |
| `api.archives-ouvertes.fr/ref/author/` | Enrichissement ORCID par `idHal` |
| `api.hal.science/ref/structure/` | Identifiants ROR/RNSR des laboratoires |
| `api.openalex.org/works` | Croisement par DOI et par titre |
| `pub.orcid.org/v3.0` | Vérification de l'employeur actuel |

Toutes les requêtes incluent des pauses (`time.sleep`) pour respecter les limites de taux des APIs. Les requêtes OpenAlex incluent un paramètre `mailto`.

## Laboratoires

Chaque laboratoire est identifié par un ou plusieurs `structId` HAL (entiers). Les alias (ancien/nouveau identifiant) sont détectés automatiquement via `resolve_valid_struct_ids()` qui filtre les IDs retournant peu de résultats.

## Licence

[MIT](LICENSE)
