# OpenAlex Abstract Integrity — Project Guide

This folder contains all data, code, and drafts for our study on the integrity of abstracts in OpenAlex. The goal is to quantify how many OpenAlex abstracts marked as available (`has_abstract=True`) are actually usable, classify failures into a taxonomy, and release annotated data for the community.

---

## Quick start for Seorin

Your two tasks:
1. **Improve the ICSSI submission** in [`icssi_submission/`](#icssi-submission)
2. **Design nicer figures** in [`figures_for_submission.ipynb`](#figures-notebook)

The key files you need are listed below, grouped by purpose.

---

## 1. Data files

### 1a. Human-curated ground truth (1,000 entries)

| File | Description |
|------|-------------|
| `output/integrity_final_1000.json` | Final labels for 1,000 abstracts. Each entry has `entry_id`, `paper_id`, `final_verdict` (bool), individual annotator votes (`vince`, `seorin`, `claude`, `codex`), `comment` (from discussion), `abstract`, and `failure_mode` (for rejected entries). |
| `output/integrity_final_1000.csv` | Same data in CSV format (1.2 MB). |

### 1b. Full 10,000-entry dataset (LLM-annotated)

| File | Description |
|------|-------------|
| `output/integrity_all_10000.json` | All 10,000 abstracts annotated by Claude Opus 4.6 using the calibrated prompt. Each entry has `entry_id`, `paper_id`, `claude_label` (one of 8 labels), `failure_mode`, `abstract`, and `final_verdict_1k` (human ground truth for first 1,000; `null` for entries 1,000--9,999). |
| `output/integrity_all_10000.csv` | Same data in CSV format (12.2 MB). |

### 1c. Individual annotator files

| File | Description |
|------|-------------|
| `output/integrity_Vince.json` | Vince's binary Yes/No annotations (932 valid, 68 rejected) |
| `output/integrity_Seorin.json` | Seorin's binary Yes/No annotations (769 valid, 231 rejected) |
| `output/integrity_claude.json` | Claude Opus 4.6 binary annotations (876 valid, 124 rejected) |
| `output/integrity_Codex_GPT54_first1000.json` | Codex GPT-5.4 binary annotations (939 valid, 61 rejected) |
| `output/integrity_discussion.json` | Discussion annotations resolving the 196 disagreements |

### 1d. Codex multi-label chunks (10k, partial)

| File | Description |
|------|-------------|
| `output/tmp_integrity_codex_chunks/chunk_*.json` | 12 chunk files covering entries 0--5,999. Each entry has `codex_label` (one of 8 labels). Used for Codex multi-label comparison against ground truth. |

---

## 2. Failure mode taxonomy

| File | Description |
|------|-------------|
| `output/failure_mode_update_hierarchy.md` | Definitions of the 7 failure mode categories (the canonical reference). |
| `output/failure_mode_analysis.md` | Detailed analysis of all 128 rejected entries and 120 overruled entries, with representative examples, annotator patterns, and key findings. |

The seven failure modes (non-overlapping):

1. **Insufficient abstract content** — conclusion-only snippets, bare questions, title repetitions
2. **Bibliographic / repository metadata** — citation strings, DOI-only, tables of contents
3. **Wrong document section** — introduction or body text instead of the abstract
4. **Web-scrape artefacts** — navigation, paywall, HTML/XML residue
5. **Truncated abstract** — cut off mid-sentence (some at exactly 200 chars)
6. **No abstract / placeholder** — stubs, "n/a", "[in Japanese]"
7. **Wrong scholarly genre** — editorials, errata, letters to the editor

---

## 3. Classification prompt

| File | Description |
|------|-------------|
| `prompt_for_abstract_integrity.md` | The calibrated 8-label classification prompt used for the 10k annotation. Includes task description, label definitions, and borderline-case guidance derived from the annotator discussion. This is what we release alongside the dataset. |

Key calibration rules (from annotator discussion on 196 borderline cases):
- Short abstracts are **Valid** if they convey both methods and results
- Case reports are **Valid** regardless of non-standard structure
- HTML markup around valid content is **not** a failure
- Non-English text is classified by its underlying defect, not language

---

## 4. ICSSI submission

| File | Description |
|------|-------------|
| `icssi_submission/template_latex_icssi_2026.tex` | Original submitted version (v0). |
| `icssi_submission/template_latex_icssi_2026_revision_v1.tex` | **Current revision (v1)**, addressing reviewer comments. Start here. |
| `icssi_submission/bibliography.bib` | BibTeX file with 6 references (shared by both versions). |
| `icssi_submission/fig1_failure_modes.pdf` | Figure 1, copied from `output/figures/fig1_failure_modes.pdf`. |
| `icssi_submission/icssi_review_report_v1.md` | Reviewer 1 (external): Weak Accept |
| `icssi_submission/icssi_review_report_v2.md` | Reviewer 2 (internal/co-author comments from Vince) |
| `icssi_submission/icssi_review_report_v3.md` | Reviewer 3 (external): Accept |

### Compilation

```bash
cd icssi_submission
pdflatex template_latex_icssi_2026_revision_v1.tex
bibtex template_latex_icssi_2026_revision_v1
pdflatex template_latex_icssi_2026_revision_v1.tex
pdflatex template_latex_icssi_2026_revision_v1.tex
```

### Constraints
- **2-page limit** (including references, figures, and tables)
- Single-spaced, 12pt, 1-inch margins, A4
- Template preamble must not be altered

---

## 5. Figures notebook

| File | Description |
|------|-------------|
| `figures_for_submission.ipynb` | Generates all publication figures from the data. Currently produces 6 figures (see below). |

### Current figures in `output/figures/`

| Figure | Content | Used in paper? |
|--------|---------|----------------|
| `fig1_failure_modes.pdf` | Horizontal bar chart of 7 failure modes (10k data) with inset pie chart (valid/rejected split) | Yes (Figure 1) |
| `fig2_agreement_before.pdf` | Panel (a): individual rejection rates; Panel (b): pairwise Cohen's kappa heatmap | No |
| `fig3_agreement_after.pdf` | Stacked bar chart of annotator votes vs. final verdict after consultation | No |
| `fig4_voting_patterns.pdf` | Four-way voting patterns (V S C X) with counts | No |
| `fig5a_disagreements_by_category.pdf` | Disagreements by failure mode category (Claude vs. human) | No |
| `fig5b_confusion_matrix.pdf` | Binary confusion matrix (Claude vs. human, first 1k) | No |

Only `fig1_failure_modes.pdf` is used in the paper. The 2-page limit allows for one figure. The notebook uses `output/integrity_final_1000.json` and `output/integrity_all_10000.json` as input data.

---

## 6. Key numbers

| Metric | Value |
|--------|-------|
| Sample size | 10,000 English-language articles from OpenAlex |
| Sampling filters | article type, English, 1900--2025, `has_abstract=True`, not retracted, cited at least once |
| Annotators | 2 human (Vince, Seorin) + 2 LLM (Claude Opus 4.6, Codex GPT-5.4) |
| Unanimous agreement (1k) | 804 / 1,000 |
| Fleiss' kappa (4 annotators, 1k) | 0.50 (moderate) |
| Final verdict (1k) | 872 valid, 128 rejected (12.8% rejection) |
| Calibrated prompt agreement (1k) | 96.0% (842 TP, 118 TN, 30 FP, 10 FN) |
| Claude binary agreement (1k) | 97.0% |
| Codex binary agreement (1k) | 94.3% |
| Full dataset verdict (10k) | 8,795 valid, 1,205 rejected (12.0%) |

### 10k failure mode distribution

| Failure mode | Count | % of rejected |
|-------------|-------|---------------|
| Insufficient abstract content | 353 | 29.3% |
| Bibliographic / repository metadata | 185 | 15.4% |
| Wrong document section | 167 | 13.9% |
| Web-scrape artefacts | 150 | 12.4% |
| Truncated abstract | 139 | 11.5% |
| No abstract / placeholder | 109 | 9.0% |
| Wrong scholarly genre | 102 | 8.5% |

### Per-annotator rejection rates (1k)

| Annotator | Valid | Rejected | Rejection rate |
|-----------|-------|----------|----------------|
| Vince | 932 | 68 | 6.8% |
| Seorin | 769 | 231 | 23.1% |
| Claude | 876 | 124 | 12.4% |
| Codex | 939 | 61 | 6.1% |

---

## 7. Protocol: how we reached the current revision

### Phase 1: Sampling and annotation setup
- Sampled 10,000 English-language articles from OpenAlex using `src/OpenAlex_random_sample_v2.py` (filters: article type, English, 1900--2025, `has_abstract=True`, not retracted, `cited_by_count >= 1`).
- Built an annotation GUI (`cleaning_gui.py`) for binary Yes/No judgments on abstract validity.
- Four annotators independently rated the first 1,000 abstracts: Vince and Seorin (human), Claude Opus 4.6 and Codex GPT-5.4 (LLM).

### Phase 2: Disagreement resolution and failure mode discovery
- 804/1,000 entries had unanimous agreement. The remaining 196 were resolved through structured discussion between Vince and Seorin (`annotator_discussion.py`, saved in `output/integrity_discussion.json`).
- Final verdict: 872 valid, 128 rejected (12.8%).
- Key annotator patterns discovered: Seorin was the strictest (231 rejections), Codex the most lenient (61 rejections). Disagreements did not split along the human--machine divide.
- From the 128 rejected entries, 7 non-overlapping failure modes were inductively derived through qualitative analysis of annotator comments and discussion records. Definitions codified in `output/failure_mode_update_hierarchy.md`.

### Phase 3: Prompt calibration
- Insights from annotator discussion (especially the 196 borderline cases) were used to write a calibrated classification prompt (`prompt_for_abstract_integrity.md`).
- Key calibration decisions: short abstracts valid if method+result present; case reports valid; HTML markup not a failure; non-English classified by underlying defect.

### Phase 4: Scaled annotation (10k)
- Applied the calibrated prompt to all 10,000 abstracts using Claude Opus 4.6 as an in-context classifier.
- On the first 1,000 entries, the prompt achieved 96.0% agreement with human ground truth.
- Full results: 8,795 valid (88.0%), 1,205 rejected (12.0%). Saved in `output/integrity_all_10000.json`.

### Phase 5: Writing and figures
- Generated publication figures in `figures_for_submission.ipynb` (6 figures, only `fig1_failure_modes.pdf` used in the paper).
- Wrote the ICSSI extended abstract in `icssi_submission/template_latex_icssi_2026.tex` (v0). Compiles to exactly 2 pages.

### Phase 6: Reviews and revision (current stage)
- Received 3 reviews (see `icssi_submission/icssi_review_report_v*.md`).
- Main reviewer concerns and how v1 addresses them:

| Concern | Raised by | How addressed in v1 |
|---------|-----------|---------------------|
| 96% agreement is in-sample (same data used for calibration) | R1, R3 | Added explicit caveat; argued overfitting risk is minimal because calibration was qualitative boundary rules, not supervised label fitting |
| No formal inter-annotator agreement metric | R1, R3 | Added Fleiss' kappa = 0.50; noted human--machine disagreement patterns |
| Sampling limitations not explicit enough | R1, R3 | Added caveat: English-only, cited-only, non-English/uncited/recent may differ |
| Weak connection to downstream SoS research | R1, R2 | Named concrete vulnerable analyses: novelty scores for research evaluation, topic models ingesting artefacts |
| Title should include finding | R2 | Changed to "One in Eight OpenAlex Abstracts Has Integrity Issues" |
| Opening too dry | R2 | Shortened application list, foregrounded consequence ("corrupted text compromises downstream results") |
| Missing concrete annotator insights | R2 | Added PubMed conclusion-only scraping pattern and 200-char truncation pattern |
| Emphasize community use of dataset | R2 | Strengthened closing: train own classifiers, extend coverage through community efforts |
| Keywords too generic | R3 | Changed "data integrity" to "bibliometric data quality" |

### Still open / not addressed in v1
- Temporal/disciplinary breakdown of failure rates (R1, R3) — would require new analysis
- Remediation guidance: which failures can be auto-corrected vs. need re-scraping (R3) — could add if space permits
- Held-out validation split (R1, R3) — decided against; argued qualitative calibration has minimal overfitting risk

---

## 8. Other files (for reference)

| File | Description |
|------|-------------|
| `experimental_setup.md` | Original experimental design document (sampling, annotation, GUI, analysis plan) |
| `plan_for_submission.md` | Planning notes for the ICSSI/STI submission angle |
| `instructions.md` | How to launch the annotation GUI |
| `cleaning_gui.py` | Tkinter annotation GUI (binary Yes/No) |
| `annotator_discussion.py` | Tool for structured annotator discussion |
| `prepare_cleaning_tasks.py` | Samples 10,000 entries from the OpenAlex set |
| `src/OpenAlex_random_sample_v2.py` | Script that queries the OpenAlex API for the random sample |
| `inter_annotator_agreement.ipynb` | Notebook for inter-annotator agreement analysis |
| `reports/claude_report_abstracts.md` | Claude's initial analysis of abstract quality issues |
| `reports/claude_report_abstracts_cleaning.md` | Claude's literature review on abstract cleaning |
| `reports/gpt_report_abstracts_fixed_citations.md` | GPT literature review (source for Culbert and Alonso-Alvarez citations) |
| `output/integrity_claude_model_spec.json` | Model spec log for Claude binary annotation |
| `output/integrity_all_10000_model_spec.json` | Model spec log for 10k annotation run |
| `output/failure_mode_claude_model_spec.json` | Model spec log for failure mode classification |
| `output/integrity_Codex_GPT54_first1000_specs.json` | Model spec log for Codex annotation |
| `sti_submission/STI-ENID2026_Template-Paper-and-Poster.docx` | Template for STI conference (separate submission) |
