# NeurIPS 2026 Venue Configuration

**Venue:** Conference on Neural Information Processing Systems (NeurIPS)
**Year:** 2026
**Submission deadline:** TBD -- monitor https://neurips.cc for 2026 dates (typically late May)

> **BLOCKER:** NeurIPS 2026 template/style files not yet released as of March 2026. Using NeurIPS 2025 style (`neurips_2025.sty`) as placeholder. Update when 2026 template is available.

---

## Format Requirements

| Property | Value |
|----------|-------|
| Page limit | 9 pages (main content) + unlimited appendix/references |
| Paper size | US Letter (8.5" x 11") |
| Columns | Single column |
| Font | 10pt, Times New Roman or similar serif |
| Template | LaTeX (`neurips_2025.sty` placeholder until 2026 release) |
| Template source | https://neurips.cc/Conferences/2026/CallForPapers |
| Compilation | `tectonic main.tex` (auto-downloads style file) |
| Line numbers | Required for submission (remove for camera-ready) |
| Margins | Set by style file |

---

## LaTeX Template

| Property | Value |
|----------|-------|
| Package name | `neurips_2025.sty` (placeholder -- 2026 not yet released) |
| Download URL | https://neurips.cc/Conferences/2026/CallForPapers |
| Compilation command | `tectonic main.tex` |
| Document class | `\usepackage{neurips_2025}` |
| Submission mode | `\usepackage[preprint]{neurips_2025}` for preprint, no options for blind submission |

> **NOTE:** LaTeX class files are NOT stored in this repository. Tectonic downloads them automatically, or they can be obtained from the URL above. When NeurIPS 2026 template is released, update the package name and URL.

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

NeurIPS uses a 1-10 scale on four dimensions. The peer-reviewer agent should calibrate to these levels.

### Quality (1-10)

| Score | Level | Description |
|-------|-------|-------------|
| 1-2 | Poor | Fundamental methodological flaws, incorrect proofs, invalid experimental setup |
| 3-4 | Below average | Significant issues with correctness or evaluation, missing important baselines |
| 5-6 | Average | Sound methodology with some gaps, adequate but not thorough evaluation |
| 7-8 | Good | Technically sound, well-evaluated, minor issues only |
| 9-10 | Excellent | Impeccable methodology, comprehensive evaluation, all claims well-supported |

### Clarity (1-10)

| Score | Level | Description |
|-------|-------|-------------|
| 1-2 | Poor | Incomprehensible, missing key details, no logical structure |
| 3-4 | Below average | Confusing organization, unclear notation, hard to follow arguments |
| 5-6 | Average | Understandable but could be improved, some notation issues |
| 7-8 | Good | Well-written, clear notation, easy to follow |
| 9-10 | Excellent | Exceptionally well-written, elegant presentation, perfect notation |

### Originality (1-10)

| Score | Level | Description |
|-------|-------|-------------|
| 1-2 | Poor | No novel contribution, straightforward application of existing methods |
| 3-4 | Below average | Minor variations on known approaches, incremental at best |
| 5-6 | Average | Some novel elements but builds heavily on prior work |
| 7-8 | Good | Clear novelty in approach, method, or insight; meaningful advance |
| 9-10 | Excellent | Highly original, opens new research direction, paradigm-shifting |

### Significance (1-10)

| Score | Level | Description |
|-------|-------|-------------|
| 1-2 | Poor | No practical or theoretical impact, solves a non-problem |
| 3-4 | Below average | Limited impact, niche interest only |
| 5-6 | Average | Moderate interest to a subcommunity, useful but not essential |
| 7-8 | Good | Broad interest, clear practical or theoretical contributions |
| 9-10 | Excellent | Transformative impact, will be widely cited and adopted |

### Reviewer Confidence (1-5)

| Score | Description |
|-------|-------------|
| 1 | Not confident -- reviewed outside area of expertise |
| 2 | Somewhat confident -- familiar with the area but not an expert |
| 3 | Fairly confident -- knowledgeable in the area |
| 4 | Confident -- have published in this area |
| 5 | Very confident -- expert in this specific topic |

---

## Submission Checklist

Before running `/paper:submit-check`, verify:

- [ ] Paper is within 9-page limit (main content only)
- [ ] All author information removed (double-blind)
- [ ] No identifying URLs or institution names
- [ ] Line numbers included
- [ ] All figures are readable in black-and-white
- [ ] References are complete (no "TODO" or placeholder citations)
- [ ] Abstract is within 250-word limit
- [ ] All claims are supported by evidence (citations or experiments)
- [ ] Supplementary materials are anonymous
- [ ] LaTeX compiles without errors using venue style file
- [ ] No acknowledgments section in submission
- [ ] Ethics statement included (if applicable)
- [ ] Reproducibility checklist completed (NeurIPS requirement)
- [ ] All citations verified against real papers (zero fabrication)

---

## NeurIPS-Specific Considerations

### What Reviewers Look For
- **Novel contribution** clearly stated in introduction
- **Strong baselines** -- not just strawman comparisons
- **Ablation studies** showing which components matter
- **Statistical significance** reported for experimental results
- **Limitations section** showing intellectual honesty
- **Broader impact statement** addressing societal implications

### Common Rejection Reasons
1. Insufficient novelty (incremental improvement over existing work)
2. Missing or weak baselines
3. Claims not supported by evidence
4. Poor experimental methodology (no error bars, no significance tests)
5. Paper too long or poorly organized
6. Writing quality issues (unclear, verbose, AI-pattern heavy)

### Accept Rate
- Typical NeurIPS accept rate: ~25-28% of submissions
- Spotlight: ~3-5%
- Oral: ~1-2%

---

*Venue config version: 1.0*
*Last updated: 2026-03-14*
*Status: Using 2025 template as placeholder -- monitor for 2026 release*
