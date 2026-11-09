# Delphes/ILD data preparation

This directory documents the locally generated Delphes dataset used to study
Z-decay channel classification and channel-fraction estimation. Data preparation
supports the main algorithm; it is not a new detector simulator. These are
simulated events, not recorded collision data.

```text
PYTHIA 8.313: electron-positron collisions at 91.1876 GeV
                       |
Delphes 3.5.1: parameterized detector response, ILD card
                       |
ROOT trees: reconstructed particle flow, electrons, muons, jets
                       |
project exporter: totals, multiplicities, three leading objects
                       |
27-column text files -> classification and channel-fraction analysis
```

Delphes Event Display is an optional viewer of the ROOT events, not a step in
generation or export. This package describes our local Delphes/ILD samples.
The ready-to-run Delphes exports are in `assets/delphes/` at the repository root:
five reference samples and S assembled from 10,000 visible-Z events plus 1,200
events from the separately generated `calibration/n` background. Select
`DATASET = "delphes"` in `dataset_config.py` to use them. Their truth key is
`evaluation/delphes/truth.csv`; raw ROOT files are not bundled. Full source truth
keys, the selected source-event mapping and hash/seed receipts are stored under
`evaluation/delphes/`. Signal selection has no channel quotas or truth-based cuts.
The background events used in S are not also used to fit the response matrix.
The separate `assets/delphi/` dataset uses DELPHI, documented in
[../data_preparation/README.md](../data_preparation/README.md).

## Generator and samples

All cards use electron/positron beams at a total centre-of-mass energy of
91.1876 GeV. Signal uses `WeakSingleBoson:ffbar2gmZ = on` and
`WeakZ0:gmZmode = 2`. Only the requested Z decay channels are enabled; other
generator settings retain the defaults of PYTHIA 8.313. Tau decays and their
secondary neutrinos are handled by that generator configuration.

| Sample group | Contents | Requested events | PYTHIA seeds |
|---|---|---:|---|
| `train` | Separate h, e, m, t, n references | 10,000 per channel | h=310101, e=310102, m=310103, t=310104, n=310105 |
| `calibration/n` | Independent background source for S | 10,000 | 330105 |
| `visible_z` | Generator-selected mixture of h, e, m, t | 100,000 | 340101 |

Here h means Z to quarks (u, d, s, c, b); e, m and t mean electron, muon and
tau pairs. The mixed signal enables those channels together, without quotas or
post-generation reweighting. Direct Z decays to neutrinos are disabled, so its
fractions are conditional on the enabled visible Z channels. It contains no
added two-photon background.

The n channel is a restricted two-photon background proxy:
`PDF:lepton2gamma = on`, `Photon:ProcessType = 4`, `Photon:Wmin = 10.0`,
`PhotonCollision:all = on`. Its beam energy remains 91.1876 GeV; the interacting
photons carry fractions of the beam energy. This is not a model of all collision
backgrounds or electronic noise. All complete cards are in `configs/`.

## Detector configuration

The basis is the **ILD card distributed with Delphes 3.5.1**, used as a fast
detector model at the Z pole. It is not a model of the DELPHI detector.
The full external card specifies tracking, calorimeter response, efficiencies,
isolation and object overlap handling. Key settings include:

- Propagator field: 3.5 T; field radius: 1.8 m; half-length: 2.4 m.
- Reconstructed jets: anti-kt, R=0.5, from `EFlowMerger/eflow`.
- Project jet threshold: 10 GeV in both `FastJetFinder` and `GenJetFinder`.
  These are the only two changes to the external ILD card before optional
  explicit detector seeding. The upstream threshold is 20 GeV.
- Electron efficiency selection: pT > 10 GeV, |eta| <= 2.5; muon selection:
  pT > 10 GeV, |eta| <= 2.4, with the card's efficiency formulas.
- Electron/muon isolation: cone radius 0.5, isolation-input pT threshold
  0.5 GeV, relative limits 0.12 and 0.25 respectively.
- `UniqueObjectFinder` gives precedence to photons, electrons, muons, then jets.

`src/prepare.py` checks a normalized SHA-256 of the external card and applies
the two threshold changes. It also checks that the resulting card matches our
configured detector-card hash. The full upstream card and Delphes implementation are not
redistributed here; generated cards remain in the external work directory.

## Export contract

Each headerless row contains 27 whitespace-separated values:

```text
nEvt Total.Px Total.Py Total.Pz Total.E Total.M nElectron nMuon nJet
ID1 Px1 Py1 Pz1 E1 M1 ID2 Px2 Py2 Pz2 E2 M2 ID3 Px3 Py3 Pz3 E3 M3
```

Momentum and energy use GeV with c=1. Event IDs are zero-based within each
file. Types are 1=electron, 2=muon, 3=jet, 0=empty. Empty slots contain zeros.
Floating-point values are written to six decimal places.

The exporter sums **all** reconstructed `EFlowTrack`, `EFlowPhoton` and
`EFlowNeutralHadron` four-vectors for event totals. It also supports a combined
`ParticleFlowCandidate` branch if provided by a different input file, but the
documented ILD card uses the three separate branches. Total.M is the invariant
mass of that sum, not the sum of individual masses.

Electron, Muon and Jet branch objects are pooled and sorted by decreasing pT;
only the first three are stored. Multiplicities count the complete branch
collections before truncation. Four-vectors and masses come from Delphes `P4()`
methods. The exporter does not recompute PID or jets, add a mass hypothesis,
or impose an energy cut. Events with zero objects remain in the file.

Generator Particle, GenJet, flavour tags and truth links are not read by the
feature exporter. Delphes itself uses generator particles to simulate detector
response and includes truth information in ROOT files. The labels for separate
reference samples come from the selected generator channels. Sample S assembly
stores generator labels in a separate truth key, never in feature rows.

## Randomness and reproduction

PYTHIA seeds are recorded in all cards. The bundled samples use automatic
detector seeding (`RandomSeed = 0`); their detector random states are unavailable.
The configuration therefore defines the simulation setup and sample distribution,
but cannot regenerate the bundled events exactly.

For new reproducible runs, `prepare.py --detector-seed 410001` assigns explicit
positive detector seeds using fixed per-sample offsets in `prepare.py` and
records each seed and card hash in a manifest. The offsets are 7 for
`calibration/n`, 9/10/11/12/13 for `train/e`, `train/h`, `train/m`, `train/n`,
`train/t`, and 14 for `visible_z`. A seed of zero enables automatic seeding.
Use the same software build, cards and both random streams when comparing repeat runs. ROOT file bytes can still
differ through metadata; compare exported rows and their hashes.

## Files and reproduction

- [REPRODUCING.md](REPRODUCING.md): build, generation, export and optional display.
- [VALIDATION.md](VALIDATION.md): checks performed by the preparation scripts.
- `configs/`: the seven complete project PYTHIA cards.
- `src/prepare.py`: validate/patch the external detector card and record a run.
- `src/run.py`: generate, export, validate counts, preserve logs and hashes.
- `src/export_delphes.C`: project ROOT-to-text exporter.
- `src/extract_truth.C`: read the terminal Z decay from stored generator ancestry
  and verify feature-row IDs, reconstructed multiplicities and total energy.
- `src/build_sample_s.py`: select 10,000 visible-Z and 1,200 independent background
  rows, shuffle before loading truth, and write S plus its separate evaluation key.
- `Dockerfile`: external software build recipe; `.dockerignore` excludes data.

No upstream implementation, binary, ROOT dataset or machine-specific launcher
is included. Obtain external software under its authors' terms. This package
does not relicense it.

## External references

- [Delphes quick tour](https://delphes.github.io/workbook/quick-tour/)
- [Delphes with PYTHIA 8](https://delphes.github.io/workbook/pythia8/)
- [Delphes Event Display](https://delphes.github.io/workbook/event-display/)
- [PYTHIA releases](https://pythia.org/releases/)
- [Delphes 3.5.1 source](https://github.com/delphes/delphes/tree/3.5.1)
