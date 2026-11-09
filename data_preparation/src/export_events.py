"""Export native DELPHI Durham jets and reconstructed leptons to 27 columns.

Input: diagnostic log from the reader built by prepare_probe.py, with PROBE LINK lines.
This is a DELPHI-only adapter; it does not read Delphes samples or generator
truth. Lepton selection uses DELPHI PID flags plus kinematic/isolation cuts.
Jet/lepton overlap is resolved only from DELPHI's IVECP(10,I) association.
"""

import argparse
import math
from pathlib import Path
from typing import Optional
from dataset_io import write_rows


def pt(p4: tuple[float, ...]) -> float:
    return math.hypot(p4[0], p4[1])


def eta(p4: tuple[float, ...]) -> float:
    transverse = pt(p4)
    return math.asinh(p4[2] / transverse) if transverse else math.copysign(math.inf, p4[2])


def phi(p4: tuple[float, ...]) -> float:
    return math.atan2(p4[1], p4[0])


def isolated(index: int, objects: list[tuple], limit: float,
             *, charged_only: bool = False, eligible_only: bool = False,
             excluded: Optional[set[int]] = None) -> bool:
    candidate = objects[index][0]
    nearby = 0.0
    for j, item in enumerate(objects):
        other = item[0]
        if (j == index or (excluded and j in excluded) or pt(other) <= 0.5
                or (charged_only and item[1] == 0)
                or (eligible_only and item[-1] & (1 | (1 << 31)))):
            continue
        dphi = math.atan2(math.sin(phi(candidate) - phi(other)),
                          math.cos(phi(candidate) - phi(other)))
        if math.hypot(eta(candidate) - eta(other), dphi) < 0.5:
            nearby += pt(other)
    return nearby / pt(candidate) <= limit


def read_events(path: Path) -> list[dict]:
    events = []
    current = None
    seen = set()
    run_number = None
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if fields[:2] == ["PROBE", "EVENT"]:
            if len(fields) != 6:
                raise ValueError(f"Invalid event header: {line}")
            run, number, count = map(int, fields[2:5])
            energy = float(fields[5])
            if (number < 0 or number in seen or count < 0 or
                    not math.isfinite(energy) or energy <= 0 or
                    (run_number is not None and run != run_number)):
                raise ValueError(f"Invalid or duplicate event, or mixed runs: {line}")
            seen.add(number)
            run_number = run
            current = {"number": int(fields[3]), "expected_objects": int(fields[4]),
                       "expected_jets": None, "ierr": None, "objects": [],
                       "jets": [], "links": {}, "conversions": []}
            events.append(current)
        elif fields[:2] == ["PROBE", "CONV"]:
            if current is None or len(fields) != 9:
                raise ValueError(f"Invalid conversion audit: {line}")
            current['conversions'].append(dict(
                parent=int(fields[2]), status=int(fields[3]),
                children=(int(fields[4]), int(fields[5])), code=int(fields[6]),
                old_energy=float(fields[7]), replacement_energy=float(fields[8])))
            if not all(math.isfinite(float(x)) for x in fields[7:9]):
                raise ValueError(f"Non-finite conversion audit: {line}")
        elif fields[:2] == ["PROBE", "OBJ"]:
            if current is None or len(fields) != 15 or "*" in fields[-1]:
                raise ValueError(f"Invalid object line: {line}")
            p4 = tuple(map(float, fields[3:8]))
            charge = float(fields[8])
            if int(fields[2]) != len(current['objects']) + 1:
                raise ValueError(f"Nonsequential or repeated object index: {line}")
            if not all(math.isfinite(x) for x in (*p4, charge)):
                raise ValueError(f"Non-finite object: {line}")
            pid = tuple(map(int, fields[9:14]))
            lock = int(fields[14], 16)
            current["objects"].append((p4, charge, *pid, lock))
        elif fields[:2] == ["PROBE", "LINK"]:
            if current is None or len(fields) != 4:
                raise ValueError(f"Invalid association line: {line}")
            index, code = map(int, fields[2:])
            if index in current["links"]:
                raise ValueError(f"Repeated object association: {index}")
            current["links"][index] = code // 1000
        elif fields[:2] == ["PROBE", "JETS"]:
            if current is None or len(fields) != 4 or current["expected_jets"] is not None:
                raise ValueError(f"Invalid jet header: {line}")
            current["expected_jets"] = int(fields[2])
            current["ierr"] = int(fields[3])
            if current['expected_jets'] < 0 or current['ierr'] < 0:
                raise ValueError(f"Invalid jet header: {line}")
        elif fields[:2] == ["PROBE", "JET"]:
            if current is None or len(fields) != 8:
                raise ValueError(f"Invalid jet line: {line}")
            if int(fields[2]) != len(current['jets']) + 1:
                raise ValueError(f"Nonsequential or repeated jet index: {line}")
            jet = tuple(map(float, fields[3:8]))
            if not all(math.isfinite(x) for x in jet):
                raise ValueError(f"Non-finite jet: {line}")
            current["jets"].append(jet)
    if not events:
        raise ValueError(f"No events in {path}")
    for event in events:
        replaced, used = set(), set()
        for repair in event['conversions']:
            if repair['status'] not in (0, 1):
                raise ValueError('Unknown conversion repair status')
            if not repair['status']:
                continue
            parent, children = repair['parent'], set(repair['children'])
            valid = set(range(1, len(event['objects']) + 1))
            if (parent not in valid or not children <= valid or len(children) != 2
                    or parent in children or parent in replaced or children & used
                    or parent in used or children & replaced):
                raise ValueError('Ambiguous conversion replacement')
            if not event['objects'][parent-1][-1] & 1:
                raise ValueError('Replaced parent remains active')
            if any(event['objects'][i-1][-1] & 0x80000001 for i in children):
                raise ValueError('Conversion replacement contains inactive daughter')
            if abs(sum(event['objects'][i-1][0][3] for i in children)
                   - repair['replacement_energy']) > 1e-3:
                raise ValueError('Conversion replacement energy mismatch')
            replaced.add(parent)
            used.update(children)
        event['replaced_indices'] = replaced
        if (len(event["objects"]) != event["expected_objects"] or
                event["expected_jets"] is None or
                len(event["jets"]) != event["expected_jets"] or
                set(event["links"]) != set(range(1, len(event["objects"]) + 1)) or
                event["ierr"] & 1):
            raise ValueError(f"Incomplete native reconstruction: event {event['number']}")
        eligible = [item[0] for item in event["objects"]
                    if item[-1] & (1 | (1 << 31)) == 0 and pt(item[0]) > 0]
        event["eligible"] = eligible
        event["eligible_indices"] = [i + 1 for i, item in enumerate(event["objects"])
                                      if item[-1] & (1 | (1 << 31)) == 0 and pt(item[0]) > 0]
        if any(not 1 <= event['links'][i] <= event['expected_jets']
               for i in event['eligible_indices']):
            raise ValueError(f"Eligible object has no valid jet association: event {event['number']}")
        for component in range(4):
            difference = sum(p[component] for p in eligible) - sum(
                p[component] for p in event["jets"])
            if abs(difference) > 1e-3:
                raise ValueError(f"Jet/input four-vector mismatch in event {event['number']}: "
                                 f"component {component} differs by {difference}")
        for jet_index, jet in enumerate(event["jets"], 1):
            members = [event["objects"][i - 1][0] for i in event["eligible_indices"]
                       if event["links"][i] == jet_index]
            if not members:
                raise ValueError(f"Jet {jet_index} has no constituents in event {event['number']}")
            for component in range(4):
                difference = sum(p[component] for p in members) - jet[component]
                if abs(difference) > 1e-3:
                    raise ValueError(f"Native jet membership mismatch: event {event['number']} "
                                     f"jet {jet_index}, component {component}")
    return events


def event_row(event: dict, overlap_policy: str = "any",
              electron_policy: str = "recover_strong") -> list[float]:
    if overlap_policy not in ('any', 'single', 'none'):
        raise ValueError(f'Unknown jet overlap policy: {overlap_policy}')
    if electron_policy != "recover_strong":
        raise ValueError('Only the recover_strong electron policy is supported')
    objects = event["objects"]
    eligible = event["eligible"]
    total = tuple(sum(p[i] for p in eligible) for i in range(4))
    total_mass = math.sqrt(max(0.0, total[3]**2 - sum(v * v for v in total[:3])))
    electron_indices = []
    eligible_set = set(event["eligible_indices"])
    excluded = {i-1 for i in event.get('replaced_indices', ())}
    for i, item in enumerate(objects):
        if (i in excluded or item[2] <= 1 or item[3] != 0 or item[4] != 0
                or pt(item[0]) <= 10 or abs(eta(item[0])) > 2.5):
            continue
        regular = isolated(i, objects, 0.12, excluded=excluded)
        recovered = (i + 1 in eligible_set
                     and item[2] >= 4
                     and isolated(i, objects, 0.12, charged_only=True,
                                  eligible_only=True, excluded=excluded))
        if regular or recovered:
            electron_indices.append(i)
    muon_indices = [i for i, item in enumerate(objects)
             if i not in excluded and item[5] != 0 and pt(item[0]) > 10
             and abs(eta(item[0])) <= 2.4
             and isolated(i, objects, 0.25, excluded=excluded)]
    electrons = [objects[i][0] for i in electron_indices]
    muons = [objects[i][0] for i in muon_indices]
    selected_leptons = {i + 1 for i in electron_indices + muon_indices}
    kept_jets = []
    for jet_index, jet in enumerate(event["jets"], 1):
        members = {i for i in event["eligible_indices"]
                   if event["links"][i] == jet_index}
        overlap = bool(members & selected_leptons)
        if overlap_policy == "any" and overlap:
            continue
        if overlap_policy == "single" and overlap and len(members) == 1:
            continue
        kept_jets.append(jet)
    # The original classifier sees the three highest-pT objects, unchanged.
    reco = [(1, p) for p in electrons] + [(2, p) for p in muons]
    reco += [(3, p) for p in kept_jets]
    reco.sort(key=lambda item: pt(item[1]), reverse=True)
    row = [event["number"], *total, total_mass,
           len(electrons), len(muons), len(kept_jets)]
    for obj_id, p4 in reco[:3]:
        row.extend([obj_id, *p4])
    for _ in range(3 - min(3, len(reco))):
        row.extend([0] * 6)
    if len(row) != 27 or not all(math.isfinite(v) for v in row):
        raise ValueError(f"Invalid event {event['number']}: {row}")
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jet-overlap-policy", choices=("any", "single", "none"),
                        default="any", help="Which native jets sharing a selected lepton to omit")
    parser.add_argument("--electron-policy", choices=("recover_strong",),
                        default="recover_strong",
                        help="Recovery of strong DELPHI electrons obscured by nearby neutral objects")
    args = parser.parse_args()
    events = read_events(args.input)
    rows = [event_row(event, args.jet_overlap_policy, args.electron_policy)
            for event in events]
    write_rows(args.output, rows)
    print(f"events={len(rows)} overlap_policy={args.jet_overlap_policy} "
          f"electron_policy={args.electron_policy} "
          f"jets={sum(row[8] for row in rows)} "
          f"electrons={sum(row[6] for row in rows)} "
          f"muons={sum(row[7] for row in rows)} output={args.output}")


if __name__ == "__main__":
    main()
