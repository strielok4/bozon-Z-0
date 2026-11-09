# Delphes sample S

S contains **10,000 visible-Z events and 1,200 separately generated background
events**, before the analysis selection. No channel quotas, truth-based cuts,
or event duplication are used.

## Sources and identity

- Signal: 10,000 rows selected without replacement from the 100,000-event
  `visible_z.dat` export; generator seed 340101.
- Background: 1,200 rows selected without replacement from the 10,000-event
  `calibration/n.dat` export; generator seed 330105. The background reference
  used by the classifier comes from `train/n`, with seed 310105, so selected
  background events are not reused as reference events.
- Signal selection seed: 540201; background selection seed: 540202;
  final shuffle seed: 540203, using Python 3.13.14 `random.Random`.

The builder fixes selected IDs, order and reconstructed feature rows before
loading truth labels. Only the first field (`nEvt`) is changed in feature rows.
The remaining 26 field strings are preserved from the original export.

`event_sources.csv` maps each new `nEvt` to its source and original ROOT-entry
index. `truth.csv` contains the evaluation label for that new ID.
`sample_manifest.json` records selection seeds, source/output hashes and counts.

## Generator truth

Truth comes from the preserved ROOT files, not from reconstructed particle IDs.
The extractor follows Z copies to the terminal Z decay and reads its direct
fermion pair, checking daughter/mother links. Thus a tau that subsequently
decays to an electron or muon still belongs to the tau channel. Missing,
unsupported or ambiguous decay records cause an error instead of an inferred
label. Background labels use the separately configured background source; the
extractor also rejects an unexpected Z in that source.

Complete source keys are preserved in `source_truth/`. `truth_provenance.json`
records their hashes, ROOT-file hashes, extraction-code hash and ROOT image.
Source signal labels are h=87,558, e=4,180, m=4,127, t=4,135. All 10,000 source
background rows have label n.

## Composition and analysis selection

| True channel | In S before selection | Retained by current classifier |
|---|---:|---:|
| h | 8,777 | 8,777 |
| e | 401 | 401 |
| m | 391 | 391 |
| t | 431 | 431 |
| n | 1,200 | 1,200 |
| Total | 11,200 | 11,200 |

Selecting `DATASET = "delphes"` bypasses the entire event filter for references
and S. All rows are passed to classification, including `ID1 == 0`; no
`Total.E` threshold is applied. Input-format and finite-value validation remain
enabled. Empty exported object slots do not necessarily mean a physically empty
event. Unavailable templates are excluded from scoring; a sole valid candidate
is assigned directly, as described in [METHOD.md](../../METHOD.md).

The MC labels are stored separately from the classifier's feature input.

For extraction and assembly commands, see
[the Delphes reproduction instructions](../../delphes_data_preparation/REPRODUCING.md).
