# Reproducing the Delphes/ILD samples

Run these commands from this directory. Keep generated files outside the
package and preserve the resulting ROOT files, cards, manifests and logs.
The commands do not run or modify the classification algorithm.

## 1. External software

The Docker environment uses Delphes 3.5.1, PYTHIA 8.313 and ROOT 6.34.00 on
Ubuntu 24.04, Linux x86-64 (`linux/amd64`). Docker Desktop must use Linux
containers. `Dockerfile` pins the ROOT base-image digest, downloads the named
upstream source releases, verifies their SHA-256 hashes and builds the PYTHIA
interface. It contains no local source-directory dependencies. Network access
to the image registry, Ubuntu repositories, pythia.org and GitHub is required.
APT packages are not frozen to a repository snapshot, so this is not a
guarantee of byte-identical build artifacts. On an ARM host, explicitly request
`--platform linux/amd64` for build/run commands. The image targets x86-64;
ARM hosts require emulation.

```sh
docker build -t delphes-ild-reproduction:3.5.1 .
```

This image tag is created locally by the command; it is not a public image to
pull. A compatible existing build can also be used. The package needs Python
3.9+ and ROOT in that environment. Its Python scripts use only the standard
library.

Allow several GB for the software image/build cache plus space for ROOT data.
Reserve space for ROOT data, text exports, logs and working files in addition
to the image. Actual size depends on the generated events. Start with the
small check before generating all 160,000 requested events.
`run.py` checks a 5 GiB free-space floor before each sample. On Docker Desktop,
also monitor the host drive: container filesystem free space does not always
reflect the remaining capacity of the host drive holding Docker's virtual disk.

## 2. Set mount locations

Use absolute paths for a package mount (read-only) and a separate work mount.
Create an empty work directory. The fixed paths `/prep`, `/work`, `/opt/Delphes`
below are container locations, not paths tied to the author's computer.

POSIX shell:

```sh
PACKAGE_DIR="$PWD"
mkdir ../delphes-work
WORK_DIR="$(cd ../delphes-work && pwd)"
```

PowerShell:

```powershell
$PACKAGE_DIR = (Get-Location).Path
New-Item -ItemType Directory ../delphes-work
$WORK_DIR = (Resolve-Path ../delphes-work).Path
```

The following Docker commands are deliberately single-line and work with those
variables in either shell. The preparation destination (`/work/smoke` or
`/work/production`) must not already exist.

## 3. Small end-to-end check

```sh
docker run --rm --network none --mount "type=bind,source=$PACKAGE_DIR,target=/prep,readonly" --mount "type=bind,source=$WORK_DIR,target=/work" delphes-ild-reproduction:3.5.1 python3 /prep/src/prepare.py /work/smoke --delphes /opt/Delphes --events 10 --detector-seed 410001
docker run --rm --network none --mount "type=bind,source=$PACKAGE_DIR,target=/prep,readonly" --mount "type=bind,source=$WORK_DIR,target=/work" delphes-ild-reproduction:3.5.1 python3 /prep/src/run.py /work/smoke --delphes /opt/Delphes
```

This requests 10 events in each of seven samples, including both background
cards and the visible-Z mixture. Expect seven `events OK` messages. A nonzero
command exit or missing success messages require investigation in the logs.
Exit status of Delphes alone is insufficient: the runner also checks the
exported row count, finite values, identifiers and 27-column structure.

## 4. Production samples

```sh
docker run --rm --network none --mount "type=bind,source=$PACKAGE_DIR,target=/prep,readonly" --mount "type=bind,source=$WORK_DIR,target=/work" delphes-ild-reproduction:3.5.1 python3 /prep/src/prepare.py /work/production --delphes /opt/Delphes --detector-seed 410001
docker run --rm --network none --mount "type=bind,source=$PACKAGE_DIR,target=/prep,readonly" --mount "type=bind,source=$WORK_DIR,target=/work" delphes-ild-reproduction:3.5.1 python3 /prep/src/run.py /work/production --delphes /opt/Delphes
```

Omitting `--events` preserves the card counts: 10,000 per separate sample,
100,000 for `visible_z`. To use automatic detector seeding exactly as specified
for the bundled samples, use `--detector-seed 0`; results will not be identical
between runs. The small and production examples deliberately reuse streams
for workflow checking: do not treat the small check as independent evaluation
data or combine it with production.

To generate only a subset, append repeated selections such as
`--sample train/e --sample train/h` to the runner command. It refuses to
overwrite existing outputs/logs. After an interruption, retain the failed job
for diagnosis and use a fresh work directory, or select only untouched jobs.
Do not silently reuse partial ROOT files as successful samples.

The output layout is:

```text
production/
  manifest.json       requested counts, PYTHIA/detector seeds, card hashes
  cards/              exact PYTHIA and generated detector cards per sample
  root/               preserved Delphes ROOT files (train/, calibration/, visible_z.root)
  export/             .dat features and .json count/hash receipts
  logs/               generator, detector and exporter output
```

`visible_z` is directly under each corresponding directory. The full ROOT
files contain both generator records and reconstructed branches, allowing
re-export without rerunning generation and simulation. They are not part of
the repository package.

## 5. Extract truth and assemble sample S

The bundled S uses 10,000 events selected from `visible_z` and 1,200 events from
`calibration/n`. It does not use equal channel quotas. Keep the `train/n`
reference separate from the `calibration/n` background used here.

Create a truth output directory on the host (PowerShell: `New-Item -ItemType
Directory "$WORK_DIR/truth"`; POSIX: `mkdir "$WORK_DIR/truth"`). With the package
and work variables from section 2, these commands read existing ROOT files and
exports, without regenerating any events:

```sh
docker run --rm --network none --mount "type=bind,source=$PACKAGE_DIR,target=/prep,readonly" --mount "type=bind,source=$WORK_DIR/production,target=/production,readonly" --mount "type=bind,source=$WORK_DIR/truth,target=/truth" --entrypoint root delphes-ild-reproduction:3.5.1 -l -b -q '/prep/src/extract_truth.C("/production/root/visible_z.root","/production/export/visible_z.dat","/truth/visible_z_truth.csv")'
docker run --rm --network none --mount "type=bind,source=$PACKAGE_DIR,target=/prep,readonly" --mount "type=bind,source=$WORK_DIR/production,target=/production,readonly" --mount "type=bind,source=$WORK_DIR/truth,target=/truth" --entrypoint root delphes-ild-reproduction:3.5.1 -l -b -q '/prep/src/extract_truth.C("/production/root/calibration/n.root","/production/export/calibration/n.dat","/truth/background_truth.csv",true)'
```

Truth extraction requires ROOT only; the pinned base image in `Dockerfile` can
also be used instead of the built Delphes image. It reads split numeric leaves
and does not need the Delphes class library. Without that library ROOT may print
missing-class-dictionary warnings; entry counts, ancestry and feature-alignment
checks still run. Any failed check gives a nonzero exit status.

Run each extraction in a separate ROOT process. Outputs must not already exist.
The macro supports the particle-flow branches used by this package's ILD setup;
it rejects missing branches and unexpected truth records. The signal key uses
the terminal Z's direct decay pair, preserving tau labels through subsequent
tau decays. Feature IDs and ROOT entry indices must agree for every row, with
matching reconstructed multiplicities and total particle-flow energy within
1e-5 GeV.

Assemble S on the host using only the Python standard library:

```sh
python src/build_sample_s.py --signal "$WORK_DIR/production/export/visible_z.dat" --signal-truth "$WORK_DIR/truth/visible_z_truth.csv" --background "$WORK_DIR/production/export/calibration/n.dat" --background-truth "$WORK_DIR/truth/background_truth.csv" --output "$WORK_DIR/sample_s"
```

Defaults select 10,000 signal and 1,200 background rows without replacement,
using seeds 540201 and 540202, then shuffle with seed 540203. Selection and
feature-row order are fixed before truth files are loaded. Record the Python
version for exact reproduction of `random.Random.sample`/`shuffle` behavior.
The original feature fields are preserved; only event IDs are rewritten.

The new output directory contains `sample_for_analysis.dat`, `truth.csv`,
`event_sources.csv` and `sample_manifest.json`. These map to the repository's
`assets/delphes/` (features) and `evaluation/delphes/` (evaluation files).
No energy or empty-object filter is applied during assembly. With
`DATASET = "delphes"`, the classifier also bypasses its event filter and
processes all 11,200 mixed events. DELPHI retains its separate selection.

The shipped full source truth keys and source/output hashes are recorded in
`evaluation/delphes/` at the repository root. New detector simulations can
produce different events because the detector random states of the bundled
samples are unavailable.

## 6. Classifier input

The `.dat` format matches the main algorithm's input contract. Point its file
mapping at the exported files, or copy into a new dataset directory using:

| Export | Existing classifier filename |
|---|---|
| `train/h.dat` | `sm_lep90_pythia6_test_qq.dat` |
| `train/e.dat` | `sm_lep90_pythia6_test_ee.dat` |
| `train/m.dat` | `sm_lep90_pythia6_test_mumu.dat` |
| `train/t.dat` | `sm_lep90_pythia6_test_tata.dat` |
| `train/n.dat` | `sm_lep90_pythia6_test_bg.dat` |
| `sample_s/sample_for_analysis.dat` from section 5 | `sample_for_analysis.dat` |

The filename token `pythia6` is an interface convention, not the generator
version. Use the assembled `sample_s/truth.csv` as the separate evaluation key.
`calibration/n` supplies the independent S background and must not also be
reused as a reference sample for that analysis. This preparation package does
not execute matrix estimation, apply DELPHI energy filters, or replace files
in `assets`.

## 7. Optional Event Display

On a graphical ROOT/Delphes installation (with its libraries configured), use
the generated card and the matching ROOT file. From the Delphes source/build
directory, a POSIX-shell example is:

```sh
root -l 'examples/EventDisplay.C("/absolute/work/production/cards/train/e.tcl","/absolute/work/production/root/train/e.root","ParticlePropagator","ChargedHadronTrackingEfficiency","MuonEfficiency","ECal,HCal")'
```

Replace the two example absolute paths with your own. The ECal/HCal names and
propagator match this ILD card. A headless container does not automatically
provide a graphical display; the batch data workflow above does not require
one. See the [upstream display instructions](https://delphes.github.io/workbook/event-display/).
