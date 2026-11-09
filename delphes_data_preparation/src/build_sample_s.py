"""Select/shuffle reconstructed rows before joining separate generator labels."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import random


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_features(path):
    rows = {}
    with Path(path).open(encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.split()
            if len(fields) != 27 or not all(math.isfinite(float(x)) for x in fields):
                raise ValueError(f'Invalid feature row at line {line_number}')
            event_id = int(fields[0])
            if event_id < 0 or event_id in rows:
                raise ValueError('Negative or duplicate feature ID')
            rows[event_id] = fields
    return rows


def read_truth(path, expected_ids, allowed):
    labels = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['nEvt', 'true_channel']:
            raise ValueError('Expected truth columns nEvt,true_channel')
        for row in reader:
            event_id = int(row['nEvt'])
            label = row['true_channel']
            if event_id in labels or label not in allowed:
                raise ValueError('Duplicate truth ID or unsupported channel')
            labels[event_id] = label
    if set(labels) != set(expected_ids):
        raise ValueError('Truth IDs do not match feature IDs')
    return labels


def build(signal, signal_truth, background, background_truth, output,
          signal_count=10000, background_count=1200,
          signal_seed=540201, background_seed=540202, shuffle_seed=540203):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Choose a new output directory')
    if signal_count <= 0 or background_count <= 0:
        raise ValueError('Sample sizes must be positive')
    sources = {'visible_z': Path(signal), 'background': Path(background)}
    rows = {source: read_features(path) for source, path in sources.items()}
    if signal_count > len(rows['visible_z']) or background_count > len(rows['background']):
        raise ValueError('Requested more events than available')

    # Selection depends only on feature IDs and seeds, never on channel labels.
    selected = [
        ('visible_z', event_id)
        for event_id in random.Random(signal_seed).sample(sorted(rows['visible_z']), signal_count)
    ]
    selected += [
        ('background', event_id)
        for event_id in random.Random(background_seed).sample(sorted(rows['background']), background_count)
    ]
    random.Random(shuffle_seed).shuffle(selected)
    feature_lines = [
        ' '.join([str(new_id), *rows[source][event_id][1:]])
        for new_id, (source, event_id) in enumerate(selected)
    ]
    # Only now read the evaluation labels. No quotas or truth-based selection.
    labels = {
        'visible_z': read_truth(signal_truth, rows['visible_z'], set('hemt')),
        'background': read_truth(background_truth, rows['background'], {'n'}),
    }
    output.mkdir(parents=True)
    feature_path = output / 'sample_for_analysis.dat'
    with feature_path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(feature_lines) + '\n')
    with (output / 'truth.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['nEvt', 'true_channel'])
        writer.writerows((i, labels[source][event_id]) for i, (source, event_id) in enumerate(selected))
    with (output / 'event_sources.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['nEvt', 'source', 'source_nEvt'])
        writer.writerows((i, source, event_id) for i, (source, event_id) in enumerate(selected))
    paths = {'signal_features': signal, 'signal_truth': signal_truth,
             'background_features': background, 'background_truth': background_truth}
    manifest = {
        'sample': 'Delphes/ILD S: visible-Z mixture plus separately generated background',
        'signal_events': signal_count, 'background_events': background_count,
        'selection': 'random.Random.sample without replacement, then Random.shuffle; labels loaded afterwards',
        'signal_seed': signal_seed, 'background_seed': background_seed, 'shuffle_seed': shuffle_seed,
        'python': platform.python_version(),
        'event_id': 'Sequential mixed ID; event_sources.csv preserves original ROOT-entry IDs',
        'filtering': 'None during assembly; classifier selection is separate',
        'truth_counts': dict(sorted(Counter(labels[source][event_id] for source, event_id in selected).items())),
        'inputs': {key: {'name': Path(path).name, 'sha256': sha(path)} for key, path in paths.items()},
        'outputs': {name: {'sha256': sha(output/name), 'events': len(selected)}
                    for name in ('sample_for_analysis.dat', 'truth.csv', 'event_sources.csv')},
        'builder_sha256': sha(__file__),
    }
    (output / 'sample_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'events': len(selected), 'truth_counts': manifest['truth_counts']}, indent=2))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('signal', 'signal-truth', 'background', 'background-truth', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--signal-count', type=int, default=10000)
    parser.add_argument('--background-count', type=int, default=1200)
    parser.add_argument('--signal-seed', type=int, default=540201)
    parser.add_argument('--background-seed', type=int, default=540202)
    parser.add_argument('--shuffle-seed', type=int, default=540203)
    build(**vars(parser.parse_args()))
