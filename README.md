# OpenAlex Abstract Integrity

Code and analysis for a study on the integrity of abstracts in OpenAlex. We quantify how many records flagged `has_abstract=True` are actually usable scientific abstracts, classify the failures into a seven-category taxonomy, and compare human vs. LLM annotations on a 1,000-paper ground truth set before scaling to 10,000 with a calibrated LLM prompt.

## Study at a glance

- **Sample**: 10,000 English-language articles from OpenAlex (`has_abstract=True`, cited ≥ 1, 1900–2025, not retracted).
- **Ground truth**: 1,000 of those abstracts labelled independently by four annotators — two humans (`A1`, `A2`) and two LLMs (Claude Opus 4.6, Codex GPT-5.4). Disagreements (196/1000) resolved by structured discussion between the human annotators.
- **Taxonomy**: 7 non-overlapping failure modes inductively derived from the 128 rejected entries.
- **Scaled run**: a calibrated prompt applied to all 10,000 entries with Claude Opus 4.6 (96.0 % agreement with human ground truth on the first 1k).
- **Headline finding**: ~12 % of OpenAlex abstracts with `has_abstract=True` are not usable scientific abstracts.

### Failure modes

1. Insufficient abstract content (conclusion-only snippets, bare questions, title repetitions)
2. Bibliographic / repository metadata (citation strings, DOI-only, tables of contents)
3. Wrong document section (introduction or body text instead of the abstract)
4. Web-scrape artefacts (navigation, paywall, HTML/XML residue)
5. Truncated abstract (cut off mid-sentence; some at exactly 200 chars)
6. No abstract / placeholder (stubs, "n/a", "[in Japanese]")
7. Wrong scholarly genre (editorials, errata, letters)

## Repository layout

```
.
├── .env.example              Template for the Semantic Scholar API key
├── .gitignore
├── README.md                 (this file)
├── src/                      Python scripts: sampling, annotation, matching, analysis
└── notebooks/                Figures and inter-annotator-agreement analysis
```

Data, figures, papers, and per-LLM model-spec logs live in `output/`, `docs/`, `submissions/`, and `references/`, which are **not tracked in this repository**. See [Data](#data) below.

## Setup

```bash
# Python 3.10+ recommended
pip install numpy pandas polars pyarrow scikit-learn requests plotly
# For the Tkinter GUIs (cleaning_gui.py, annotator_discussion.py): Tk usually ships with Python on macOS/Windows
# On Linux: sudo apt-get install python3-tk
```

Copy `.env.example` to `.env` and fill in your Semantic Scholar API key (only required for `src/semantic_scholar_matching.py`):

```bash
cp .env.example .env
# then edit .env
```

## Code

### `src/`

| Script | Purpose |
|---|---|
| `OpenAlex_random_sample_v2.py` | Draws the random 10k sample from the OpenAlex parquet (filters: article, English, 1900–2025, `has_abstract=True`, not retracted, cited ≥ 1). Reads from HPC-mounted parquets — paths at the top of the file must be adjusted for your environment. |
| `prepare_cleaning_tasks.py` | Builds the per-task annotation files (10k integrity + 10k language) for human labelling. Reads the cleaned background parquet (HPC path). |
| `cleaning_gui.py` | Tkinter GUI for binary Yes/No labelling of abstract integrity and language. Used by the human annotators. |
| `annotator_discussion.py` | Tkinter GUI for structured resolution of inter-annotator disagreements between A1 and A2 (also displays the Claude / Codex verdicts side-by-side). |
| `semantic_scholar_matching.py` | Matches the 10k OpenAlex papers to Semantic Scholar via DOI and fetches S2 abstracts. Requires `SS_API_KEY` in `.env`. |
| `compare_abstract_lengths.py` | Compares normalised abstract lengths between OpenAlex and Semantic Scholar for papers present in both sources. |
| `failure_mode_cross_platform.py` | Analyses (a) whether specific OpenAlex failure modes correlate with S2 abstract absence, and (b) what failure modes appear in length-mismatched pairs. |

### `notebooks/`

| Notebook | Purpose |
|---|---|
| `fig1_plotly_executed.ipynb` | Generates publication figures from the labelled data (executed; Plotly outputs embedded). |
| `inter_annotator_agreement.ipynb` | Computes pairwise / Fleiss' kappa, prints the contingency tables, and walks through representative disagreements. |
| `extract_dois_hpc.ipynb` | One-off HPC notebook that extracts the DOI mapping for the 10k sample from the OpenAlex metadata parquet. |

## Data

The repository contains **only the code**. The data files referenced by the scripts and notebooks are expected under `output/` but are not committed (see [`.gitignore`](.gitignore)). To run the notebooks end-to-end you will need:

### Annotator label files (1k subset)

| Expected path | Contents |
|---|---|
| `output/integrity_A1.json` | Human annotator A1's binary Yes/No labels (first 1k) |
| `output/integrity_A2.json` | Human annotator A2's binary Yes/No labels (first 1k) |
| `output/integrity_claude.json` | Claude Opus 4.6 binary labels (first 1k) |
| `output/integrity_Codex_GPT54_first1000.json` | Codex GPT-5.4 binary labels (first 1k) |
| `output/integrity_discussion.json` | Joint A1+A2 adjudication of the 196 disagreements |

### Consolidated / scaled outputs

| Expected path | Contents |
|---|---|
| `output/integrity_tasks.json` | The 10k task definitions (entry_id, title, abstract, paper_id) |
| `output/integrity_final_1000.json` | Per-entry merge of human ground truth, all four annotator votes, `final_verdict`, and `failure_mode` |
| `output/integrity_all_10000.json` | Calibrated-prompt labels on the full 10k set (one of 8 labels per entry) |

### Run / model provenance

| Expected path | Contents |
|---|---|
| `output/integrity_claude_model_spec.json` | Model, temperature, prompt template for the 1k Claude run |
| `output/integrity_all_10000_model_spec.json` | Same, for the scaled 10k run |
| `output/integrity_Codex_GPT54_first1000_specs.json` | Run metadata and decision policy for the Codex run |
| `output/failure_mode_claude_model_spec.json` | Spec for the failure-mode classification run |

The published dataset (label files + provenance) is intended for separate release alongside the paper. If you have a copy, place it under `output/` and the notebooks will run unchanged.

## Annotator labels

Throughout this codebase the two human annotators are referred to as **`A1`** and **`A2`** (lowercase `a1`/`a2` when used as dict keys or pandas columns). LLM annotators are referred to by their model names (`claude`, `codex`).

## Key numbers (reference)

| Metric | Value |
|---|---|
| Sample | 10,000 English articles, OpenAlex, 1900–2025 |
| Ground-truth size | 1,000 abstracts |
| Unanimous agreement (4 annotators, 1k) | 804 / 1,000 |
| Fleiss' κ (4 annotators, 1k) | 0.50 (moderate) |
| Final verdict (1k) | 872 valid · 128 rejected (12.8 %) |
| Calibrated-prompt agreement (1k) | 96.0 % (842 TP, 118 TN, 30 FP, 10 FN) |
| Full-dataset verdict (10k) | 8,795 valid · 1,205 rejected (12.0 %) |

### Per-annotator rejection rates (1k)

| Annotator | Valid | Rejected | Rejection rate |
|---|---|---|---|
| A1 | 932 | 68 | 6.8 % |
| A2 | 769 | 231 | 23.1 % |
| Claude (Opus 4.6) | 876 | 124 | 12.4 % |
| Codex (GPT-5.4) | 939 | 61 | 6.1 % |

### 10k failure-mode distribution

| Failure mode | Count | % of rejected |
|---|---|---|
| Insufficient abstract content | 353 | 29.3 % |
| Bibliographic / repository metadata | 185 | 15.4 % |
| Wrong document section | 167 | 13.9 % |
| Web-scrape artefacts | 150 | 12.4 % |
| Truncated abstract | 139 | 11.5 % |
| No abstract / placeholder | 109 | 9.0 % |
| Wrong scholarly genre | 102 | 8.5 % |

## Reproducing the pipeline

1. **Sample**: run `src/OpenAlex_random_sample_v2.py` against your local OpenAlex mirror to produce the 10k sample (or skip this if you already have `output/integrity_tasks.json`).
2. **Human labelling**: launch `src/cleaning_gui.py` for the binary Yes/No task; outputs `output/integrity_<NAME>.json` per annotator.
3. **LLM labelling**: produce `output/integrity_claude.json` and `output/integrity_Codex_GPT54_first1000.json` by running the LLM annotators (model + prompt documented in the corresponding `*_model_spec.json`).
4. **Disagreement resolution**: launch `src/annotator_discussion.py` to resolve the cases where annotators disagree.
5. **Inter-annotator agreement**: run `notebooks/inter_annotator_agreement.ipynb`.
6. **Scale**: apply the calibrated prompt to the full 10k set with Claude Opus 4.6 → `output/integrity_all_10000.json`.
7. **Figures**: run `notebooks/fig1_plotly_executed.ipynb`.

## License

TBD.
