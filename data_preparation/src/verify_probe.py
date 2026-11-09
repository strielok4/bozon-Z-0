"""Verify observed SKELANA settings and reconstruction consistency before export."""
import argparse
import json
import re
from pathlib import Path
from export_events import read_events


def verify(log, expected, expected_guard_mode=None):
    if expected_guard_mode not in (None, 1):
        raise ValueError('Only the enabled refit guard is supported')
    text = Path(log).read_text(errors='replace')
    header = text.split('PROBE EVENT', 1)[0]
    values = dict(re.findall(r'^\s+(\w+)\s*=\s*([\d.E+-]+)\s*$', header, re.M))
    config = json.loads(Path(expected).read_text())
    for name, value in {**config['flags'], **config['selection']}.items():
        if name not in values or float(values[name]) != value:
            raise ValueError(f'Runtime setting mismatch: {name}: expected {value}, found {values.get(name)}')
    if expected_guard_mode is not None:
        modes = {int(line.split()[5]) for line in text.splitlines()
                 if line.split()[:2] == ['AUD', 'PVREFIT']}
        if modes != {expected_guard_mode}:
            raise ValueError(f'Cannot confirm refit guard mode {expected_guard_mode}; observed audit modes: {sorted(modes)}')
    events = read_events(Path(log))
    if len({e['number'] for e in events}) != len(events):
        raise ValueError('Duplicate event ID; export one run at a time')
    print(f'Verified runtime settings and native object/jet sums for {len(events)} events')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    p.add_argument('--expected', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/skelana_observed.json')
    p.add_argument('--expected-guard-mode', type=int, choices=(1,),
                   help='Require refit audit records in this mode; fails if no such records exist')
    a = p.parse_args()
    verify(a.log, a.expected, a.expected_guard_mode)
