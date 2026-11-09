"""Assemble exported reconstruction; consult truth only after features are fixed."""
import argparse
import csv
import json
import random
from pathlib import Path
from dataset_io import FILES, digest, read_rows, write_rows


def build(exports, signal_truth, output, seed=540101, *, expected_signal=None, expected_background=None):
    exports, signal_truth, output = map(Path, (exports, signal_truth, output))
    if output.exists():
        raise FileExistsError(output)
    names = [f'train_{c}' for c in FILES] + ['blind_z', 'blind_n']
    paths = {name: exports / f'{name}.dat' for name in names}
    hashes = {name: digest(path) for name, path in paths.items()}
    samples = {name: read_rows(path) for name, path in paths.items()}
    if any(not samples[name] for name in names):
        raise ValueError('Empty input sample')
    for name, expected in (('blind_z', expected_signal), ('blind_n', expected_background)):
        if expected is not None and (expected < 1 or len(samples[name]) != expected):
            raise ValueError(f'{name}: expected {expected} reconstructed events; found {len(samples[name])}')
    order = [(name, i) for name in ('blind_z', 'blind_n') for i in range(len(samples[name]))]
    random.Random(seed).shuffle(order)
    combined, provenance = [], []
    for new_id, (source, i) in enumerate(order):
        row = samples[source][i].copy()
        provenance.append((new_id, source, int(row[0])))
        row[0] = new_id
        combined.append(row)
    # Labels cannot affect features, ordering, or object/event selection above.
    truth = {}
    truth_hash = digest(signal_truth)
    with signal_truth.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            key, label = int(row['nEvt']), row['true_channel']
            if key in truth or label not in 'hemt' or len(label) != 1:
                raise ValueError('Invalid or duplicate signal truth label')
            truth[key] = label
    if set(truth) != {int(r[0]) for r in samples['blind_z']}:
        raise ValueError('Signal truth IDs do not match reconstructed signal IDs')
    if hashes != {name: digest(path) for name, path in paths.items()} or truth_hash != digest(signal_truth):
        raise ValueError('Inputs changed while assembling the dataset')
    # Reserve the output directory exclusively; never reuse a partial dataset.
    output.mkdir(parents=True)
    (output / 'assets').mkdir()
    (output / 'evaluation').mkdir()
    for channel, filename in FILES.items():
        write_rows(output / 'assets' / filename, samples[f'train_{channel}'])
    write_rows(output / 'assets/sample_for_analysis.dat', combined)
    for filename, header, rows in (
        ('event_sources.csv', ['nEvt', 'source', 'source_nEvt'], provenance),
        ('truth.csv', ['nEvt', 'true_channel'],
         [(n, truth[old] if source == 'blind_z' else 'n') for n, source, old in provenance]),
    ):
        with (output / 'evaluation' / filename).open('x', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
    metadata = dict(shuffle_seed=seed, source_sha256=hashes, signal_truth_sha256=truth_hash,
                    source_counts={n: len(r) for n, r in samples.items()},
                    assets_sha256={p.name: digest(p) for p in (output / 'assets').glob('*.dat')},
                    truth_usage='Evaluation only; signal truth read after reconstructed features and shuffle were fixed.')
    (output / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Created {output}: {len(combined)} mixed events')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exports', required=True, type=Path)
    p.add_argument('--signal-truth', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seed', type=int, default=540101)
    p.add_argument('--expected-signal', type=int, help='Optional strict reconstructed signal count')
    p.add_argument('--expected-background', type=int, help='Optional strict reconstructed background count')
    args = p.parse_args()
    build(args.exports, args.signal_truth, args.output, args.seed,
          expected_signal=args.expected_signal, expected_background=args.expected_background)
