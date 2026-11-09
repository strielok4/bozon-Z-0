# Method and interpretation

## Inputs and event selection

Each headerless input row contains 27 whitespace-separated values:

```text
nEvt Total.Px Total.Py Total.Pz Total.E Total.M nElectron nMuon nJet
ID1 P1.Px P1.Py P1.Pz P1.E P1.M
ID2 P2.Px P2.Py P2.Pz P2.E P2.M
ID3 P3.Px P3.Py P3.Pz P3.E P3.M
```

Energy, momentum and mass use GeV with c=1. Object types are electron (1), muon
(2), jet (3), or empty slot (0). Event totals include more reconstructed inputs
than the three stored objects. Multiplicities describe the full selected
collections before the top-three truncation. The exporter documentation in
[data_preparation](data_preparation/README.md) defines these conventions.

For DELPHI, `main.py` retains rows with `Total.E <= 110` and `ID1 != 0`. For
Delphes, it bypasses `filter_events` entirely, applying neither condition to
the references or S. Input-format and finite-value validation still apply.
It preserves event
IDs and leaves input files unchanged. IDs are unique within a sample, not across
all six input files. The nominal energy used by classifier rules is 91.1876 GeV;
the DELPHI generator configuration uses 91.25 GeV. Both values are recorded
explicitly rather than treated as interchangeable.

## Classification

1. Compute event momentum/transverse momentum, object angles and the pair
   summaries used by the configured templates.
2. Apply explicit energy, angular and multiplicity rules to clear cases.
   Conflicting or unmatched rule results remain ambiguous.
3. For each configured `(nElectron, nMuon, nJet)` topology, estimate feature
   medians and scales from ambiguous events in its selected reference channels.
   Empty references or nonfinite feature medians/MADs make a template unavailable.
   For valid templates, the scale is `1.4826 * max(MAD, 1e-6)`; constant features
   retain this finite floor.
4. Sum squared standardized feature deviations for each candidate channel.
   Unavailable templates and nonfinite scores cannot win. With one valid score,
   assign its channel directly. With two or more, choose the smallest score if
   its gap to the second-smallest is at least 1; otherwise leave the event
   ambiguous. With no valid scores, leave it ambiguous. The explicit zero-object
   background rule takes precedence over scoring.
5. Assign remaining ambiguous events to background (`n`). The report records
   how many S events entered background through this fallback.

The score uses marginal feature scales, not a fitted covariance matrix.
It is a ranking score, not a calibrated class probability or a chi-square
significance. Correlated features can receive overlapping weight. Candidate
channels and feature lists are explicitly defined in `apply_topology_templates`.

Channel codes are `h` (hadrons), `e` (electron pair), `m` (muon pair), `t` (tau
pair), and `n` (background). `s` identifies the mixed sample; it is never a
candidate decay channel. No per-event S truth label is used by classification.

## Correction and fractions

The reference predictions give a matrix
`A[predicted, true] = P(predicted class | reference channel)`, normalized by
column. The observed S counts form `y`; the code solves `A x = y` for corrected
channel populations. It uses a least-squares/pseudoinverse fallback when the
absolute determinant is below `1e-12`. Negative solutions are not clipped.

Uncertainties propagate a Poisson count covariance `diag(y)` through the inverse
matrix and then through normalization. They treat A as fixed.

Visible fractions normalize corrected h/e/m/t counts after background
correction. The full-distribution table scales them by 0.8 and inserts an
assumed 20% invisible fraction.

## Evaluation scope

`evaluate_sample_s.py` evaluates individual S event assignments before
response-matrix correction. It joins those assignments with
`evaluation/<dataset>/truth.csv` using `nEvt` and reports accuracy, balanced
accuracy, macro-F1, per-channel precision/recall/F1, confusion counts and events
absent after selection. Accuracy is computed on retained events; retention is
reported separately.

These metrics describe the intermediate classification step, not the accuracy
of the final corrected channel fractions. The response matrix corrects aggregate
channel counts, not individual event labels. Higher classification accuracy does
not necessarily imply more accurate channel-fraction estimates.

