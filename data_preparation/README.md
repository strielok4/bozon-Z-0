# Data provenance for Z-decay channel estimation

The main project estimates the relative populations of Z-boson decay channels
from reconstructed events. Its focus is the classification method and the
correction of observed channel counts for misclassification. This directory
documents and implements the supporting data preparation, rather than a new
detector simulator.

The inputs are **simulated events**, not recorded LEP collision data. They were
processed with the publicly available DELPHI simulation and reconstruction
software. DELPHI and the unrelated Delphes framework are not interchangeable;
the dataset described here uses DELPHI.

## Where the data come from

```text
Signal: PYTHIA 5.722 + JETSET 7.409     Background: PYTHIA 8 two-photon processes
                    \                 /
                    generator events (FADGEN)
                              |
               DELSIM detector simulation, v94c
                              |
               DELANA / PXDST reconstruction
                              |
                     Short DST (SDST)
                              |
          SKELANA preparation + project reconstruction corrections
                              |
                  native Durham jet clustering
                              |
             project object selection and 27-column export
                              |
                  event selection -> main algorithm
```

The signal was generated at a collision energy of **91.25 GeV**, using separate
runs for hadronic, electron, muon and tau reference samples. The mixed signal
sample enables those visible Z-decay channels together; direct Z decays to
neutrinos are disabled. Neutrinos from subsequent decays can still occur.
ISR, FSR and fragmentation are enabled, with the TAUOLA option selected.

Background is a **restricted two-photon sample**, generated with PYTHIA 8 and
converted by our adapter into DELPHI's external-input format. It is not a model
of every LEP background or electronics noise. The incoming electron/positron
beams have a combined energy of 91.25 GeV; the photons carry fractions of
that energy. Low visible energy therefore does not require lowering the beam
energy. The configuration selects direct-direct photon interactions and sets
`Photon:Wmin = 10.0`. The adapter preserves final-state particles but does not
retain the generator's complete ancestry or production vertices.

The detector setup is **v94c**, with a beam energy of **45.625 GeV**. Geometry,
calibration data, detector simulation and the standard reconstruction programs
come from the external DELPHI distribution. The pinned image and recorded
settings are in [configs/simulation.json](configs/simulation.json).

## What is project-specific

| Component | Responsibility |
|---|---|
| Signal generation | Existing generator; project-selected cards and samples |
| Background | Existing PYTHIA 8 physics; project driver and FADGEN adapter |
| Detector simulation and initial reconstruction | Existing DELPHI tools |
| Conversion handling | Project-authored selective replacement of pathological reconstructed conversion objects |
| Primary-vertex refit guard | Project-authored conditional guard added to an externally supplied DELPHI routine |
| Jets | Existing Durham implementation, with project-selected inputs and resolution |
| Export | Project lepton selection, isolation, overlap policy, ordering and serialization |
| Dataset assembly and filtering | Project code, with event identifiers and evaluation labels kept separate |

The two interventions act **after detector simulation**, while preparing stored
SDST events for analysis. They do not regenerate detector hits or modify the
installed DELPHI libraries. The conversion intervention replaces an eligible
neutral conversion object with energy above the collision energy only when two
unambiguous, oppositely charged reconstructed daughters meet the implemented
checks. Unresolved cases remain unchanged. The refit guard prevents selected
primary-vertex refits for secondary-associated tracks or tracks failing the
existing impact-parameter criteria before the refit.

## What the algorithm receives

Each headerless row contains 27 values: an event identifier, the total
four-momentum and invariant mass, electron/muon/jet multiplicities, and three
object slots ordered by decreasing transverse momentum. Each slot contains a
type and `(px, py, pz, E, M)`. Types are `1=electron`, `2=muon`, `3=jet`, and
`0=empty`; empty slots are zero-filled.

Totals use all eligible reconstructed inputs, **not just the three stored
objects**. Multiplicities are recorded before the top-three truncation.
Individual masses are copied from the reconstruction; a PID label does not
replace a stored mass hypothesis. The default overlap policy removes an entire
jet if it contains a selected lepton. These choices affect topology and are part
of the method, not detector measurements by themselves.

| Sample | Exported before event selection | After current selection |
|---|---:|---:|
| Hadronic reference | 9,999 | 9,894 |
| Electron reference | 9,990 | 9,269 |
| Muon reference | 10,000 | 9,733 |
| Tau reference | 9,997 | 9,943 |
| Background reference | 10,000 | 9,918 |
| Mixed `s`: 10,000 visible-Z + 1,200 background | 11,200 | 11,062 |

The current selection keeps `Total.E <= 110 GeV` and requires at least one
exported object (`ID1 != 0`). It removes 114 mixed events by energy and another
24 with no exported objects. The latter need not be unphysical events.
Class-dependent retention must be considered when interpreting channel ratios.
The filter exposes both conditions as configurable options.

Filenames containing `pythia6` are part of the classifier's input interface;
they do not identify the generators used here.

## Generator truth

Generator truth is not an input to object selection, repair or jet building.
The reference channels provide labeled calibration samples for the classifier.
For the mixed sample, a separate event-to-channel key is joined only after the
reconstructed feature rows and shuffle order are fixed. Evaluation uses this
key to check already computed predictions.


## Contents and reproduction

- [REPRODUCING.md](REPRODUCING.md): external prerequisites and portable commands.
- [VALIDATION.md](VALIDATION.md): checks performed by the preparation scripts.
- `configs/`: signal cards, detector/run settings, observed SKELANA settings,
  and analysis constants.
- `custom/`: only project-authored analysis hooks and additions.
- `src/`: background adapter, probe preparation, export, assembly, filtering
  and evaluation utilities.

No DELPHI implementation, detector database, generated combined source,
binary, event dataset or machine-specific launcher is distributed here. 

## Upstream tools and documentation

- [DELPHI simulation guide, CERN Open Data](https://opendata.cern/docs/delphi-guide-simulation)
- [About DELPHI and its preserved software](https://opendata.cern.ch/docs/about-delphi)
- [PYTHIA photoproduction documentation](https://pythia.org/latest-manual/Photoproduction.html)

These tools remain the work of their respective authors.
Obtain upstream software under its own terms;
this directory does not relicense or redistribute it.
