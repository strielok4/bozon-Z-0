# Reproducing the preparation workflow

This workflow generates and reconstructs DELPHI events, then exports the
27-column input files used by the channel-estimation algorithm.

Python utilities require Python 3.9 or newer, using only the standard
library. Background generation additionally requires an external PYTHIA 8
installation and C++11 compiler. Simulation, probe compilation and SDST reading
require the official DELPHI environment.

Run Python commands from `data_preparation/`. Run the external simulation and
build commands in the appropriate Linux environment. Set `WORK`, `DELPHI_DUMP`,
`DELPHI_SKELANA`, `PYTHIA_SIGNAL` and `PYTHIA8_PREFIX` to locations in your own
installation. `WORK` must be outside this repository. They are user-supplied
variables.

## 1. Record the external environment

Use the official image reference in `configs/simulation.json`. The recorded
image digest is immutable; do not silently substitute an unpinned `latest`. 
An image digest does not by itself guarantee every externally resolved
dependency is identical.

`configs/skelana_observed.json` specifies the expected SKELANA runtime
settings. `verify_probe.py` compares them with the reconstruction log. This
file does not configure detector geometry or steer the simulation. Likewise,
`configs/analysis.json` documents constants implemented in the custom hooks and
exporter; editing that JSON alone does not change the algorithms.

## 2. Generate signal inputs

The five `configs/signal/*.tit` files configure the signal samples.
Use the official DELPHI PYTHIA example to obtain/build the generator executable;
its source and Makefile are not included here.

For each sample, use a fresh working directory, copy its card to `pythia.tit`,
link `fort.11` to that card, and run the generator. For example, with `PREP`
pointing to this directory and `PYTHIA_SIGNAL` to the external executable:

```bash
mkdir "$WORK/train_e"
cd "$WORK/train_e"
cp "$PREP/configs/signal/train_e.tit" pythia.tit
ln -s pythia.tit fort.11
"$PYTHIA_SIGNAL" > generation.log 2>&1
mv fort.26 input.fadgen
```

Repeat for `train_h`, `train_m`, `train_t` and `blind_z`. Their run numbers are
in `configs/simulation.json` and in each card. Different run numbers feed the
official generator's laboratory/run seeding convention.

## 3. Generate the restricted background inputs

Build our adapter against a separately installed PYTHIA 8:

```bash
c++ -O2 -std=c++11 "$PREP/src/generate_background.cc" \
  -I"$PYTHIA8_PREFIX/include" -L"$PYTHIA8_PREFIX/lib" \
  -Wl,-rpath,"$PYTHIA8_PREFIX/lib" -lpythia8 -ldl \
  -o "$WORK/generate_background"
```

Supply explicit, distinct seeds in the supported range 1..900000000. Seeds
for the bundled background samples are unavailable, so those events cannot be
regenerated exactly. The physics settings are defined in `generate_background.cc`.

```bash
mkdir "$WORK/train_n" "$WORK/blind_n"
"$WORK/generate_background" "$WORK/train_n/input.fadgen" 10000 "$TRAIN_BG_SEED" > "$WORK/train_n/generation.log" 2>&1
"$WORK/generate_background" "$WORK/blind_n/input.fadgen" 1200 "$TEST_BG_SEED" > "$WORK/blind_n/generation.log" 2>&1
python "$PREP/src/check_background_input.py" "$WORK/train_n/input.fadgen"
python "$PREP/src/check_background_input.py" "$WORK/blind_n/input.fadgen"
```

This FADGEN writer targets the little-endian, 32-bit integer/float layout used
by the official environment. It includes the final scattered beam leptons;
the 91.25 GeV total-energy check does not require the central detector to see
that energy. Full ancestry and production vertices are not preserved by the
adapter. No claim is made that this restricted background models all sources.

## 4. Simulate and reconstruct with DELPHI

Inside each sample's working directory, use the corresponding run number and
event count from `configs/simulation.json`. For the electron reference:

```bash
runsim -VERSION v94c -LABO CERN -NRUN 4102 -EBEAM 45.625 \
  -gext input.fadgen -NEVMAX 10000 > runsim.log 2>&1
```

Retain the generator input, generation and reconstruction logs, and SDST.
`runsim` invokes the external simulation/reconstruction chain. The relevant
stages produce `simana.fadsim`, `simana.fadana` and `simana.sdst`. Requested and
successfully reconstructed event counts can differ. Compare counts, rather
than assigning synthetic rows to absent events.

## 5. Prepare the custom SDST reader without vendoring CERN source

`DELPHI_DUMP` points to an **unmodified official dump example directory** with
`dump.car`, `dump.cra` and `dump.sh`. `DELPHI_SKELANA` points to its compatible
official `skelana.car`. Neither is part of this repository.

```bash
python "$PREP/src/prepare_probe.py" \
  --template "$DELPHI_DUMP" --skelana "$DELPHI_SKELANA" \
  --sdst "$WORK/train_e/simana.sdst" \
  --output "$WORK/probe_v2" --variant v2
```

The tool checks source anchors and the normalized-text hash of the
original refit procedure. It refuses unsupported source versions. It replaces
the example's event reader, removes its event cap, inserts our conversion
routine and adds the project guard to a locally compiled copy of the
external refit procedure. It writes input hashes to `build_manifest.json`.
The generated combined files contain upstream code and must remain outside
the repository; do not commit them.

Conversion replacement and the primary-vertex refit
guard are always enabled. No environment variable is needed to activate them.

Use the official build script inside its configured environment:

```bash
cd "$WORK/probe_v2"
bash dump.sh > build.log 2>&1
mv dump.log train_e.log
```

The official dump.sh compiles and runs the reader on the SDST file specified in PDLINPUT. 
To process another sample, update PDLINPUT and reuse the executable. 
Keep a separate output log for each sample.
The project exporter uses reconstructed objects and detector identification flags. 
Generator decay labels are stored separately for evaluation.

## 6. Verify and export reconstruction

```bash
python "$PREP/src/verify_probe.py" "$WORK/probe_v2/train_e.log"
python "$PREP/src/export_events.py" "$WORK/probe_v2/train_e.log" \
  "$WORK/exports/train_e.dat" --electron-policy recover_strong --jet-overlap-policy any
```

Create `exports/` beforehand and repeat for all seven sample names listed in
`configs/simulation.json`. The output files must be named `train_h.dat`,
`train_e.dat`, `train_m.dat`, `train_t.dat`, `train_n.dat`, `blind_z.dat` and
`blind_n.dat`. Existing output files are not overwritten.

The exporter checks native object/jet associations and four-vector sums before
applying selection. Selection is intentionally preserved from the study:
regular electron isolation and recovery isolation have different eligibility
rules; strong recovery uses eligible charged neighbors only. Muon selection
uses the original `KMULS` flag. Selected leptons sharing a jet cause that entire
jet to be removed from the exported jet list. These are analysis conventions,
not an exhaustive or uniquely correct reconstruction of all event energy.
To avoid counting a selected lepton twice, we omit any jet containing
that lepton from the exported jet list. We do not retain the remaining
jet constituents as a separate jet. Event-level totals are computed independently
from all eligible reconstructed inputs and are unchanged by this overlap removal.

## 7. Assemble the mixed sample and separate evaluation key

Extract signal labels separately from generator ancestry, retaining only the
IDs of reconstructed events:

```bash
python "$PREP/src/extract_signal_truth.py" "$WORK/blind_z/input.fadgen" \
  "$WORK/signal_truth.csv" --expected-events 10000 \
  --events-file "$WORK/exports/blind_z.dat"
python "$PREP/src/build_dataset.py" --exports "$WORK/exports" \
  --signal-truth "$WORK/signal_truth.csv" --output "$WORK/dataset" --seed 540101
```

Assembly requires 10000 reconstructed visible-Z events and 1200 background
events. It fixes feature rows and shuffle order before loading signal labels.
Background labels follow the separately generated background source. Files are
written into `assets/` and `evaluation/`; the latter contains both truth and the
source-event mapping. A manifest records input/output hashes. No classifier
code is copied or changed.

## 8. Apply event selection

The repository-root `main.py` applies this selection in memory when reading
unfiltered `assets/delphi/` files when `DATASET = "delphi"` in
`dataset_config.py`. For the ready-to-run workflow, skip this standalone
export step. The command below is for producing separately filtered files; it
does not overwrite the original dataset.

```bash
python "$PREP/src/filter_events.py" "$WORK/dataset/assets" \
  "$WORK/dataset/assets_selected" --max-energy 110
```

The default also removes events with `ID1 == 0`.
Use `--keep-empty` only for an explicitly different selection variant. The
filter never silently reuses an existing output directory. Accepted row bytes
and event IDs are preserved; the selection
manifest records removed IDs, reasons and hashes of the actual selected files.

Do not renumber after selection. Evaluate with the original key to make missing
events and class-dependent acceptance visible. A selection-adjusted sample is
not automatically an unbiased sample of Z branching fractions.

## 9. Evaluate predictions

After running the main algorithm, evaluate its saved results separately:

```bash
python "$PREP/src/evaluate_results.py" "$WORK/final_res.csv" \
  "$WORK/dataset/evaluation/truth.csv" "$WORK/evaluation"
```

Evaluation only reads `sample=s` rows, joins by `nEvt`, and reports accuracy,
per-channel precision/recall/F1, macro-F1, balanced accuracy, confusion counts
and missing-event retention. Unknown IDs or duplicate IDs cause a failure.
Missing predictions are errors; events absent from the results are reported
separately rather than silently added to the accuracy denominator.
