"""Shared validation of the project's 27-column, headerless exchange format."""
import hashlib
import math
from pathlib import Path

FILES = {
    'h': 'sm_lep90_pythia6_test_qq.dat',
    'e': 'sm_lep90_pythia6_test_ee.dat',
    'm': 'sm_lep90_pythia6_test_mumu.dat',
    't': 'sm_lep90_pythia6_test_tata.dat',
    'n': 'sm_lep90_pythia6_test_bg.dat',
}
INTEGER_COLUMNS = (0, 6, 7, 8, 9, 15, 21)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(rows):
    seen = set()
    for row in rows:
        if len(row) != 27 or not all(math.isfinite(x) for x in row):
            raise ValueError('Expected 27 finite numeric columns')
        if any(row[i] != int(row[i]) for i in INTEGER_COLUMNS):
            raise ValueError('Non-integral identifier or object count')
        if row[0] < 0 or row[0] in seen:
            raise ValueError(f'Invalid or repeated event ID: {row[0]}')
        seen.add(row[0])
        if min(row[6:9]) < 0:
            raise ValueError('Negative object multiplicity')
        ids = [int(row[i]) for i in (9, 15, 21)]
        if any(i not in (0, 1, 2, 3) for i in ids):
            raise ValueError('Unknown object type')
        if sum(i != 0 for i in ids) != min(3, sum(row[6:9])):
            raise ValueError('Object count/padding mismatch')
        if any(a == 0 and b != 0 for a, b in zip(ids, ids[1:])):
            raise ValueError('Empty slots must follow all occupied slots')
        for kind in (1, 2, 3):
            if ids.count(kind) > row[5 + kind]:
                raise ValueError('Stored objects exceed declared multiplicity')
        transverse = [math.hypot(row[i + 1], row[i + 2]) for i in (9, 15, 21)]
        if any(b > a + 1e-6 for a, b in zip(transverse, transverse[1:])):
            raise ValueError('Objects are not sorted by decreasing pT')
        for i in (9, 15, 21):
            if row[i] == 0 and any(row[i:i + 6]):
                raise ValueError('Nonzero padding')
    return rows


def read_rows(path):
    rows = [[float(x) for x in line.split()] for line in Path(path).read_text().splitlines() if line.strip()]
    return validate(rows)


def write_rows(path, rows):
    validate(rows)
    with Path(path).open('x', encoding='ascii', newline='\n') as stream:
        for row in rows:
            stream.write(' '.join(str(int(x)) if i in INTEGER_COLUMNS else f'{x:.8g}'
                                  for i, x in enumerate(row)) + '\n')
