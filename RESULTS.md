# Results on the bundled datasets

The primary output is the channel distribution after response-matrix correction.
Both samples S contain 10,000 visible-Z events and 1,200 background events.
DELPHI retains 11,062 S events after selection; Delphes uses all 11,200.

The tables use Python 3.13.14, NumPy 2.5.2 and pandas 3.0.5. S is not an
independent holdout sample; see [METHOD.md](METHOD.md) for evaluation scope.

## Corrected channel fractions

### DELPHI

| Channel | Visible fraction | Full fraction assuming 20% invisible |
|---|---:|---:|
| Hadronic | 87.796% | 70.237% +/- 0.306 percentage points |
| Electron | 3.788% | 3.030% +/- 0.177 percentage points |
| Muon | 3.952% | 3.162% +/- 0.170 percentage points |
| Tau | 4.464% | 3.571% +/- 0.249 percentage points |

### Delphes/ILD

| Channel | Visible fraction | Full fraction assuming 20% invisible |
|---|---:|---:|
| Hadronic | 87.612% | 70.089% +/- 0.334 percentage points |
| Electron | 3.969% | 3.175% +/- 0.161 percentage points |
| Muon | 4.035% | 3.228% +/- 0.169 percentage points |
| Tau | 4.384% | 3.507% +/- 0.264 percentage points |

The errors propagate observed-count uncertainty with a fixed reference matrix.
They do not include reference-sample, tuning, selection or simulation-model
uncertainties. The invisible fraction is assumed, not measured.

## Classification diagnostics

Classification is an intermediate step in estimating channel fractions.
These metrics describe individual assignments, not the accuracy of the corrected fractions.

### DELPHI

| Metric | Value |
|---|---:|
| Original S events | 11,200 |
| Retained and evaluated | 11,062 |
| Absent after selection | 138 |
| Correct predictions | 10,535 |
| Accuracy on retained events | 95.24% |
| Balanced accuracy | 87.26% |
| Macro-F1 | 86.03% |
| Majority-class accuracy baseline | 78.68% |

| Channel | Evaluated events | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| h | 8,704 | 99.54% | 97.66% | 98.59% |
| e | 371 | 93.25% | 81.94% | 87.23% |
| m | 397 | 95.89% | 88.16% | 91.86% |
| t | 405 | 56.54% | 79.01% | 65.91% |
| n | 1,185 | 83.81% | 89.54% | 86.58% |

Overall accuracy is dominated by the hadronic population. The tau category
remains substantially harder, especially in precision.

### Delphes/ILD

| Metric | Value |
|---|---:|
| Evaluated S events | 11,200 |
| Correct predictions | 10,148 |
| Accuracy | 90.61% |
| Balanced accuracy | 91.29% |
| Macro-F1 | 84.05% |

The sample composition and generator labels are described in
[Delphes sample S](evaluation/delphes/SAMPLE_S.md).

## Output files

`debug/<dataset>/res_after_matrix.csv` contains corrected channel fractions and
their uncertainties. `debug/<dataset>/evaluation_s/` contains classification
diagnostics produced by `evaluate_sample_s.py`.

Compact outputs are included separately for each dataset:

| Dataset | Corrected channel fractions | Classification metrics | Confusion matrix |
|---|---|---|---|
| DELPHI | [CSV](results/delphi/corrected_fractions.csv) | [JSON](results/delphi/summary.json) | [CSV](results/delphi/confusion_matrix.csv) |
| Delphes/ILD | [CSV](results/delphes/corrected_fractions.csv) | [JSON](results/delphes/summary.json) | [CSV](results/delphes/confusion_matrix.csv) |

`corrected_fractions.csv` contains the final estimates and their propagated
uncertainties. `summary.json` and `confusion_matrix.csv` describe the intermediate
event assignments before matrix correction. Summary paths are relative to the
repository root; source hashes use UTF-8 text with LF line endings.

These files are saved results. Running the analysis writes to `debug/<dataset>/`
and does not update `results/<dataset>/` automatically.
