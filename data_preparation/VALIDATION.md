# Data checks

The preparation scripts check the inputs and exported event structure:

- `check_background_input.py`: FADGEN record boundaries, beam entries,
  final-particle values and total energy.
- `verify_probe.py`: SKELANA settings against `configs/skelana_observed.json`,
  native jet membership and four-vector sums.
- `dataset_io.py`: 27-column format, finite values, unique event IDs,
  object types, multiplicities, padding and ordering by transverse momentum.
- `build_dataset.py`: correspondence between reconstructed signal IDs and
  the separate truth key.

These checks concern data consistency, not the physical accuracy of the
detector model.

Python versions can differ in floating-point summation and serialized digits.
Record the Python version alongside exported data when comparing file hashes.
