# ICML 2026 Venue Configuration

**Venue:** International Conference on Machine Learning (ICML)
**Year:** 2026
**Submission deadline:** TBD -- monitor https://icml.cc for 2026 dates (typically late January/early February)

---

## Format Requirements

| Property | Value |
|----------|-------|
| Page limit | 8 pages (main content) + unlimited appendix/references |
| Paper size | US Letter (8.5" x 11") |
| Columns | Two-column |
| Font | 10pt, as specified by style file |
| Template | LaTeX (`icml2026.sty`) |
| Template source | https://icml.cc/Downloads/2026 |
| Compilation command | `tectonic main.tex` |
| Margins | Set by style file |

---

## LaTeX Template

| Property | Value |
|----------|-------|
| Package name | `icml2026.sty` |
| Download URL | https://icml.cc/Downloads/2026 |
| Compilation command | `tectonic main.tex` |
| Document class | `\usepackage{icml2026}` |
| Submission mode | `\usepackage[accepted]{icml2026}` for camera-ready, no options for blind submission |

> **NOTE:** LaTeX class files are NOT stored in this repository. Tectonic downloads them automatically, or they can be obtained from the URL above.

---

## Anonymization Rules (Double-Blind)

- **No author names** in the paper
- **No identifying URLs** (e.g., no personal GitHub repos, no institution-specific links)
- **No acknowledgments** section in submission version
- **Self-citations** must be written in third person ("Prior work [N] showed..." not "Our prior work showed...")
- **Anonymous supplementary** materials only
- **No institution names** in text, figures, or headers
- **Code repositories** must be anonymized if shared (use anonymous repo services)

---

## Review Criteria

ICML uses a different scoring system than NeurIPS. The peer-reviewer agent must adapt when target venue is ICML.

### Dimension Scores (1-4 scale)

ICML scores four dimensions on a 1-4 scale (not 1-10 like NeurIPS).

#### Soundness (1-4)

| Score | Level | Description |
|-------|-------|-------------|
| 1 | Poor | Major flaws in methodology, proofs, or experiments |
| 2 | Fair | Some issues with correctness or evaluation gaps |
| 3 | Good | Technically sound with minor issues only |
| 4 | Excellent | Impeccable methodology, all claims rigorously supported |

#### Presentation (1-4)

| Score | Level | Description |
|-------|-------|-------------|
| 1 | Poor | Incomprehensible, missing key details |
| 2 | Fair | Understandable but needs significant improvement |
| 3 | Good | Well-written, clear, easy to follow |
| 4 | Excellent | Exceptionally well-written, elegant presentation |

#### Significance (1-4)

| Score | Level | Description |
|-------|-------|-------------|
| 1 | Poor | No practical or theoretical impact |
| 2 | Fair | Limited impact, niche interest |
| 3 | Good | Broad interest, clear contributions |
| 4 | Excellent | Transformative impact, will be widely adopted |

#### Originality (1-4)

| Score | Level | Description |
|-------|-------|-------------|
| 1 | Poor | No novel contribution |
| 2 | Fair | Minor variations on known approaches |
| 3 | Good | Clear novelty, meaningful advance |
| 4 | Excellent | Highly original, opens new directions |

### Overall Rating (1-6 scale)

| Score | Rating | Description |
|-------|--------|-------------|
| 1 | Strong Reject | Fundamentally flawed or trivial |
| 2 | Reject | Below acceptance threshold, significant issues |
| 3 | Weak Reject | Borderline, some merit but notable weaknesses |
| 4 | Weak Accept | Above average, minor concerns |
| 5 | Accept | Clear accept, solid contribution |
| 6 | Strong Accept | Top paper, exceptional contribution |

### Reviewer Confidence (1-5)

| Score | Description |
|-------|-------------|
| 1 | Not confident -- reviewed outside area of expertise |
| 2 | Somewhat confident -- familiar with the area but not an expert |
| 3 | Fairly confident -- knowledgeable in the area |
| 4 | Confident -- have published in this area |
| 5 | Very confident -- expert in this specific topic |

### Score Normalization for Quality Ratchet

For quality ratchet compatibility, ICML 1-4 dimension scores are mapped to the NeurIPS 1-10 equivalent scale used internally by quality_history.jsonl:

| ICML Score | NeurIPS Equivalent | Description |
|------------|-------------------|-------------|
| 1 | 1-2 | Poor |
| 2 | 4-5 | Fair |
| 3 | 7-8 | Good |
| 4 | 9-10 | Excellent |

The peer-reviewer agent performs this mapping when target_venue is ICML, so the quality ratchet always operates on a consistent 1-10 scale regardless of venue.

---

## Submission Checklist

Before running `/paper:submit-check`, verify:

- [ ] Paper is within 8-page limit (main content only, two-column format)
- [ ] All author information removed (double-blind)
- [ ] No identifying URLs or institution names
- [ ] All figures are readable at two-column width
- [ ] References are complete (no "TODO" or placeholder citations)
- [ ] Abstract is concise and self-contained
- [ ] All claims are supported by evidence (citations or experiments)
- [ ] Supplementary materials are anonymous
- [ ] LaTeX compiles without errors using `icml2026.sty`
- [ ] No acknowledgments section in submission
- [ ] Ethics statement included (if applicable)
- [ ] All citations verified against real papers (zero fabrication)
- [ ] Code availability statement included (can reference anonymous repo)
- [ ] Reproducibility information provided (hyperparameters, compute, seeds)

---

## ICML-Specific Considerations

### What Reviewers Look For
- **Clear problem motivation** with real-world relevance
- **Strong empirical evaluation** with proper baselines and ablations
- **Theoretical grounding** where applicable (convergence, bounds)
- **Reproducibility** -- enough detail to reimplement
- **Honest limitations** section
- **Societal impact** discussion

### Common Rejection Reasons
1. Insufficient novelty (incremental improvement, too similar to existing work)
2. Missing or inappropriate baselines (not comparing against state-of-the-art)
3. Experimental methodology issues (no variance reporting, cherry-picked results)
4. Claims not supported by the evidence presented
5. Poor writing quality or unclear presentation
6. Exceeding page limit (strict enforcement at ICML)
7. Anonymization violations

### Accept Rate
- Typical ICML accept rate: ~25-28% of submissions
- Spotlight: ~3-4%
- Oral: ~1-2%

---

*Venue config version: 1.0*
*Last updated: 2026-03-14*
*Source: ICML 2026 Author Instructions (https://icml.cc/Conferences/2026/AuthorInstructions)*
