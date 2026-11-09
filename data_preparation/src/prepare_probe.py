"""Apply project hooks to user-supplied DELPHI sources outside this repository.

This file distributes no complete upstream procedure. The official example,
cradle, build script and PSHCTRECPBS body are read from an external installation.
No compilation or simulation is performed here.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Unsupported source: expected exactly one anchor {old!r}')
    return text.replace(old, new, 1)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(template, skelana, sdst, output, variant='v2'):
    if variant != 'v2':
        raise ValueError('Only the v2 configuration is supported')
    template, skelana, sdst, output = map(Path, (template, skelana, sdst, output))
    # Generated files contain upstream code: do not place them in the repo.
    repository = next((p for p in PACKAGE.parents if (p / '.git').exists()), PACKAGE)
    if output.resolve().is_relative_to(repository.resolve()):
        raise ValueError('Choose a build directory outside the repository (generated files contain upstream code).')
    if output.exists():
        raise FileExistsError(output)
    for path in (template / 'dump.car', template / 'dump.cra', template / 'dump.sh', skelana, sdst):
        if not path.is_file():
            raise FileNotFoundError(path)
    if any(c in str(sdst.resolve()) for c in ('\n', '\r')):
        raise ValueError('Invalid SDST path')
    car = (template / 'dump.car').read_text()
    # Remove only the example event cap. Refuse an unfamiliar template.
    cap = re.compile(r'(?m)^      IF \( NEVENT \.GT\. (?:10|10000) \) THEN\n'
                     r'         NEED = -3\n         GO TO 99\n      ENDIF')
    car, count = cap.subn('*-- Read the complete input; EOF controls the event count.', car)
    if count != 1:
        raise ValueError('Expected exactly one event cap in the original dump example')
    start = car.index('+DECK,USER02.')
    end = car.index('+DECK, USER99.', start)
    hook = (PACKAGE / 'custom/user02.car.in').read_text()
    hook += (PACKAGE / 'custom/conversion_repair.f.in').read_text()
    car = car[:start] + hook + car[end:]
    inputs = {name: sha(template / name) for name in ('dump.car', 'dump.cra', 'dump.sh')}
    library = skelana.read_text()
    start = library.index('      SUBROUTINE PSHCTRECPBS(')
    end = library.index('+DECK,', start)
    routine = library[start:end]
    expected = json.loads((PACKAGE / 'configs/simulation.json').read_text())['original_refit_normalized_text_sha256']
    if hashlib.sha256(routine.encode()).hexdigest() != expected:
        raise ValueError('PSHCTRECPBS differs from the validated version; review before porting the guard.')
    routine = once(routine, '      INTEGER IERROR,LMAIN,LTRAC',
                   '      INTEGER IERROR,LMAIN,LTRAC\n'
                   '      INTEGER LPVA,JBIT,REASON\n'
                   '      REAL IPXY,IPZ,STH,VCOVG(6),DCAG(4)')
    guard = (PACKAGE / 'custom/vertex_guard.f.inc').read_text().rstrip('\n')
    routine = once(routine, '      IREJ = 1', '      IREJ = 1\n' + guard)
    car = once(car, '+DECK, USER99.', routine + '\n+DECK, USER99.')
    inputs['skelana.car'] = sha(skelana)
    output.mkdir(parents=True)
    (output / 'dump.car').write_text(car)
    for name in ('dump.cra', 'dump.sh'):
        shutil.copyfile(template / name, output / name)
    (output / 'PDLINPUT').write_text(f'FILE = {sdst.resolve()}\n')
    manifest = dict(variant=variant, external_source_sha256=inputs,
                    sdst_sha256=sha(sdst),
                    custom_sha256={p.name: sha(p) for p in (PACKAGE / 'custom').iterdir()},
                    generated_dump_sha256=sha(output / 'dump.car'))
    (output / 'build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Prepared {output}. Build using the official DELPHI environment and dump.sh.')
    print('Conversion replacement and the primary-vertex refit guard are always enabled.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', required=True, type=Path, help='External original DELPHI dump example directory')
    parser.add_argument('--skelana', required=True, type=Path, help='External official skelana.car')
    parser.add_argument('--sdst', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--variant', choices=('v2',), default='v2')
    args = parser.parse_args()
    prepare(args.template, args.skelana, args.sdst, args.output, args.variant)
