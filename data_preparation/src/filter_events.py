"""Apply explicit event selection, preserving accepted row bytes and event IDs."""
import argparse
import json
import math
from pathlib import Path
from dataset_io import digest, read_rows


def filter_dataset(source, output, max_energy=110.0, remove_empty=True):
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(output)
    if not math.isfinite(max_energy) or max_energy <= 0:
        raise ValueError('max_energy must be finite and positive')
    files = sorted(source.glob('*.dat'))
    if not files:
        raise ValueError('No .dat files in source directory')
    prepared, report = {}, {}
    for path in files:
        before_hash = digest(path)
        read_rows(path)  # validate IDs, types, finite numbers and padding
        kept, rejected = [], []
        total = 0
        for line in path.read_bytes().splitlines(keepends=True):
            fields = line.split()
            if not fields:
                kept.append(line)
                continue
            total += 1
            values = list(map(float, fields))
            reason = 'energy_above_threshold' if values[4] > max_energy else (
                'no_exported_objects' if remove_empty and values[9] == 0 else None)
            if reason:
                rejected.append(dict(nEvt=int(values[0]), reason=reason))
            else:
                kept.append(line)
        prepared[path.name] = b''.join(kept)
        report[path.name] = dict(input_sha256=before_hash, input_events=total,
                                 kept=total-len(rejected), removed=rejected)
        if digest(path) != before_hash:
            raise ValueError('Input changed while filtering')
    output.mkdir(parents=True)
    for name, content in prepared.items():
        (output / name).write_bytes(content)
        report[name]['output_sha256'] = digest(output / name)
    (output / 'selection_manifest.json').write_text(json.dumps(dict(
        max_energy_GeV=max_energy, remove_empty=remove_empty, files=report), indent=2) + '\n')
    print(f'Created {output}; source rows and identifiers were preserved')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--max-energy', type=float, default=110.0)
    p.add_argument('--keep-empty', action='store_true')
    a = p.parse_args()
    filter_dataset(a.source, a.output, a.max_energy, not a.keep_empty)
