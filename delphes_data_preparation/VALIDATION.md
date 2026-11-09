# Data checks

The preparation scripts check configuration and exported data:

- `prepare.py` checks the upstream ILD card hash and the two jet-threshold edits.
- `run.py` checks card hashes, output row counts, sequential event IDs,
  finite values and the 27-column format.
- `extract_truth.C` checks the terminal Z decay, particle ancestry and alignment
  between ROOT entries and feature rows. Multiplicities must agree, and the
  total-energy difference must not exceed `1e-5` GeV.
- `build_sample_s.py` checks feature/truth IDs and sample sizes. Selection and
  shuffle order are fixed before the truth labels are read.

For a small simulation and export run, follow
[the end-to-end check](REPRODUCING.md#3-small-end-to-end-check).
These checks address software behavior and data consistency.
