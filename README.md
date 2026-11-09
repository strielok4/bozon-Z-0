# Z-decay channel estimation

The goal of this project is to estimate the fractions of Z-boson decays into
the hadronic, electron, muon and tau channels using reconstructed simulated
events. Its main output is a set of channel fractions corrected for background
and misclassification between channels.

Individual event assignments are an intermediate step: physics-based rules
identify clear cases, topology-specific median/MAD templates classify the
remaining events, and a response matrix built from reference samples corrects
the observed channel counts. The repository includes the data needed to run
the analysis.

## DELPHI and Delphes datasets

The project includes two simulated datasets produced with different detector
models and reconstruction workflows:

- **DELPHI** was an experiment and detector at CERN's LEP collider. The data in
  `assets/delphi/` use its preserved DELSIM detector simulation and
  DELANA/PXDST reconstruction software, with the v94c detector configuration.
  The project then prepares the reconstructed events and exports the features
  used by the algorithm. See [DELPHI data preparation](data_preparation/README.md).
- **Delphes** is a separate fast detector-simulation framework. It models
  detector response through parameterized resolutions and efficiencies. The
  data in `assets/delphes/` use Delphes 3.5.1 with the ILD (International Large
  Detector) card, which describes a different detector model from DELPHI.
  See [Delphes/ILD data preparation](delphes_data_preparation/README.md).

Both datasets contain simulated events, not recorded collision data. Each has
its own reference samples and mixed sample S, exported in the same 27-column
format. They allow the channel-estimation method to be studied under different
detector responses. Their generation, object reconstruction and event selection
also differ, so differences in results cannot be attributed to detector response
alone. Detector simulation is provided by external software; this project's
main contribution is the channel-estimation algorithm.

## Select the dataset

Set `DATASET = "delphi"` or `DATASET = "delphes"` in `dataset_config.py`.
Inputs are read from `assets/<dataset>/`; truth keys are in
`evaluation/<dataset>/truth.csv` and outputs in `debug/<dataset>/`.
Both S files contain 10,000 visible-Z events plus 1,200 background events before
the classifier's selection. Delphes S is sampled from the natural visible-Z
mixture without channel quotas. Its assembly, exact composition and selection
losses are documented in [Delphes sample documentation](evaluation/delphes/SAMPLE_S.md).

## Run the analysis

Analysis environment: Python 3.13, NumPy 2.5.2 and pandas 3.0.5. Docker and detector
software are not needed to analyze the bundled data.

From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe verify_dataset.py
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe evaluate_sample_s.py
```

On Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python verify_dataset.py
.venv/bin/python main.py
.venv/bin/python evaluate_sample_s.py
```

The scripts create their output directories. `main.py` reads the original
selected `assets/<dataset>/` files; it does not modify those files. For DELPHI it
filters a copy in memory. For Delphes it bypasses the entire event filter,
retaining empty exported object slots and applying no total-energy cut.
The evaluation scripts read the separate truth key only after predictions have
been computed. Repeating these commands replaces the reports in `debug/<dataset>/`.


## Results and outputs

Each mixed sample S contains 10,000 visible-Z events and 1,200 background events.
The DELPHI selection retains 11,062 events. Delphes uses all 11,200 S events,
including all 1,200 background events, because its event filter is disabled.
See [RESULTS.md](RESULTS.md) for measurements from the packaged code and data,
and [METHOD.md](METHOD.md) for their interpretation.
Compact outputs for each dataset are included in [results/delphi/](results/delphi/)
and [results/delphes/](results/delphes/). These are saved results; normal analysis
runs write to `debug/<dataset>/` and do not overwrite them.

| Output | Contents |
|---|---|
| `debug/test.csv` | Assignments after the initial rules |
| `debug/final_res.csv` | Final event assignments, features and reasons |
| `debug/res_after_matrix.csv` | Corrected channel fractions and propagated uncertainties |
| `debug/missing_ET.csv` | Counts and feature summaries, including means and medians, by sample/topology |
| `debug/topology_counts.csv` | Topology frequencies within each sample |
| `debug/evaluation_s/` | Accuracy, per-channel metrics, confusion matrix and missing-event accounting |

The paths in this table are relative to the selected dataset's output directory:
replace `debug/` with `debug/delphi/` or `debug/delphes/`.

`missing_ET.csv` contains energy, momentum and mass summaries by topology.
Its `mean_missing_E` column is the mean of `91.1876 - Total.E`, in GeV.

## Repository layout

```text
main.py                         Classification, count correction and reporting
dataset_config.py               Shared dataset selection flag
evaluate_sample_s.py             Evaluation against the separate S truth key
assets/delphi/                   Six unfiltered DELPHI feature samples
assets/delphes/                  Six unfiltered Delphes/ILD feature samples
results/delphi/                  Saved DELPHI fractions and classification diagnostics
results/delphes/                 Saved Delphes/ILD fractions and classification diagnostics
evaluation/<dataset>/truth.csv   Separate S event-to-channel key
evaluation/delphes/source_truth/ Complete keys for the source signal/background
data_manifest.json              Dataset sizes, event counts and SHA-256 hashes
verify_dataset.py               Check the bundled data against the manifest
data_preparation/               DELPHI generation, extraction and reproduction
delphes_data_preparation/        Separate Delphes/ILD preparation workflow
```

The Delphes package describes the second simulation workflow. Reconstructed
feature samples and separate truth keys are bundled; raw ROOT files are not.
`RESULTS.md` reports channel fractions and classification diagnostics for both datasets.

## Checks

```sh
python verify_dataset.py
```

This command checks the integrity and structure of the bundled data. For the scope of
the statistical evaluation, see [METHOD.md](METHOD.md#evaluation-scope).

## Regenerate the data

To rerun the analysis, use the bundled feature files. To regenerate simulated
events, follow the separate [DELPHI instructions](data_preparation/REPRODUCING.md)
or [Delphes/ILD instructions](delphes_data_preparation/REPRODUCING.md).
These require external software and substantially more resources.

The preparation packages contain configurations, available seeds and custom
code. Exact regeneration requires the random states and software environment
used for the dataset; see each package's randomness notes. Raw SDST/ROOT files,
upstream implementations, detector databases and compiled libraries are not included.

External tools remain the work of their respective authors and are obtained
under their own terms.
