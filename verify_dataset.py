"""Verify packaged input bytes, event counts and row structure; no dependencies."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify_dataset():
    manifest = json.loads((ROOT / 'data_manifest.json').read_text(encoding='utf-8'))
    feature_ids = {}
    truth_ids = {}
    for name, expected in manifest['files'].items():
        path = ROOT / name
        contents = path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != expected['sha256']:
            raise ValueError(f'Dataset hash mismatch: {name}')
        if len(contents) != expected['bytes']:
            raise ValueError(f'Dataset size mismatch: {name}')
        rows = contents.decode('utf-8-sig').splitlines()
        events = len(rows) - (1 if path.suffix == '.csv' else 0)
        if events != expected['events']:
            raise ValueError(f'Event count mismatch: {name}')
        if path.suffix == '.dat':
            ids = []
            for line_number, row in enumerate(rows, 1):
                values = row.split()
                if len(values) != 27 or not all(math.isfinite(float(v)) for v in values):
                    raise ValueError(f'Invalid feature row: {name}:{line_number}')
                event_id = float(values[0])
                if event_id < 0 or not event_id.is_integer():
                    raise ValueError(f'Invalid event ID: {name}:{line_number}')
                ids.append(int(event_id))
            if len(ids) != len(set(ids)):
                raise ValueError(f'Duplicate event IDs: {name}')
            if path.name == 'sample_for_analysis.dat':
                feature_ids[path.parent.name] = set(ids)
        else:
            labels = list(csv.DictReader(rows))
            ids = [int(row['nEvt']) for row in labels]
            if len(ids) != len(set(ids)) or any(row['true_channel'] not in ('h', 'e', 'm', 't', 'n') for row in labels):
                raise ValueError(f'Invalid truth key: {name}')
            truth_ids[path.parent.name] = set(ids)
        print(f'OK {name}: {events} events')
    if feature_ids != truth_ids:
        raise ValueError('Mixed-sample event IDs do not match their dataset evaluation keys')
    for dataset, description in manifest.get('datasets', {}).items():
        if 'sample_manifest' not in description:
            continue
        receipt_path = ROOT / description['sample_manifest']
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        for name, expected in receipt['outputs'].items():
            path = (ROOT/'assets'/dataset/name if name.endswith('.dat') else receipt_path.parent/name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']:
                raise ValueError(f'Assembly output hash mismatch: {name}')
        provenance = json.loads((ROOT/description['truth_provenance']).read_text(encoding='utf-8'))
        source_labels = {}
        for source, record in provenance['sources'].items():
            path = receipt_path.parent/record['truth_file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != record['truth_sha256']:
                raise ValueError(f'Source truth hash mismatch: {source}')
            with path.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.DictReader(stream))
            labels = {int(row['nEvt']): row['true_channel'] for row in rows}
            if len(rows) != record['events'] or len(labels) != len(rows):
                raise ValueError(f'Source truth count or ID mismatch: {source}')
            source_labels[source] = labels
        with (receipt_path.parent/'truth.csv').open(encoding='utf-8', newline='') as stream:
            mixed_truth = {int(row['nEvt']): row['true_channel'] for row in csv.DictReader(stream)}
        with (receipt_path.parent/'event_sources.csv').open(encoding='utf-8', newline='') as stream:
            mapping = list(csv.DictReader(stream))
        origins = [(row['source'], int(row['source_nEvt'])) for row in mapping]
        if len(set(origins)) != len(origins) or {int(row['nEvt']) for row in mapping} != set(mixed_truth):
            raise ValueError('Duplicate source events or inconsistent mixed IDs')
        counts = Counter(source for source, event_id in origins)
        if counts != {'visible_z': receipt['signal_events'], 'background': receipt['background_events']}:
            raise ValueError('Wrong signal/background mixture')
        for row in mapping:
            if mixed_truth[int(row['nEvt'])] != source_labels[row['source']][int(row['source_nEvt'])]:
                raise ValueError('Mixed truth differs from generator source truth')
        if Counter(mixed_truth.values()) != receipt['truth_counts']:
            raise ValueError('Channel count mismatch')
        print(f'OK {dataset}: source truth, shuffle mapping and mixture verified')


if __name__ == '__main__':
    verify_dataset()
