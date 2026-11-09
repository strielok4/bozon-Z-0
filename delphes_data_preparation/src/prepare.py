"""Prepare project cards from the external Delphes 3.5.1 ILD card. Python >=3.9."""
import argparse
import hashlib
import json
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
UPSTREAM_HASH = "067f31d5b49dce9be10e97286d1246a976391db11ad42489d8232ebea1cf7065"
PROJECT_HASH = "591b10e37ddcf4b3f93be060073ec6d519155c59ec8a73838267369681bedc59"


# Stable sample identifiers for explicit detector random streams.
DETECTOR_SEED_OFFSETS = {
    "calibration/n": 7,
    "train/e": 9,
    "train/h": 10,
    "train/m": 11,
    "train/n": 12,
    "train/t": 13,
    "visible_z": 14,
}


def patch_card(source):
    text = source.read_text(encoding="utf-8")
    if hashlib.sha256(text.encode()).hexdigest() != UPSTREAM_HASH:
        raise ValueError("Unexpected upstream ILD card; use the Delphes 3.5.1 release")
    for module in ("GenJetFinder", "FastJetFinder"):
        pattern = r"(module FastJetFinder " + module + r" \{[^}]*?set JetPTMin )20\.0"
        text, count = re.subn(pattern, r"\g<1>10.0", text)
        if count != 1:
            raise ValueError("Cannot locate jet threshold for " + module)
    if hashlib.sha256(text.encode()).hexdigest() != PROJECT_HASH:
        raise ValueError("Patched card differs from the recorded project card")
    return text


def write_text(path, text):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def prepare(work, delphes, events=None, detector_seed=0):
    if events is not None and events <= 0:
        raise ValueError("Event count must be positive")
    if not 0 <= detector_seed <= 4294967200:
        raise ValueError("Detector seed must be in [0, 4294967200]")
    card = patch_card(delphes / "cards/delphes_card_ILD.tcl")
    # Refuse reuse, including partial previous preparations.
    work.mkdir(parents=True, exist_ok=False)
    jobs = []
    for source in sorted((PACKAGE / "configs").rglob("*.cmnd")):
        relative = source.relative_to(PACKAGE / "configs")
        text = source.read_text(encoding="utf-8")
        if events is not None:
            text, count = re.subn(r"(?m)^Main:numberOfEvents = \d+$",
                                 "Main:numberOfEvents = " + str(events), text)
            if count != 1:
                raise ValueError("Missing event count in " + str(relative))
        output = work / "cards" / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        write_text(output, text)
        sample = relative.with_suffix("").as_posix()
        seed = detector_seed + DETECTOR_SEED_OFFSETS[sample] if detector_seed else 0
        detector_relative = relative.with_suffix(".tcl")
        detector = card + ("\nset RandomSeed " + str(seed) + "\n" if seed else "")
        write_text(work / "cards" / detector_relative, detector)
        jobs.append({"sample": sample,
                     "events": int(re.search(r"Main:numberOfEvents = (\d+)", text)[1]),
                     "pythia_seed": int(re.search(r"Random:seed = (\d+)", text)[1]),
                     "detector_seed": seed,
                     "pythia_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "detector_sha256": hashlib.sha256(detector.encode()).hexdigest()})
    (work / "manifest.json").write_text(json.dumps({"jobs": jobs}, indent=2) + "\n", encoding="utf-8")
    return jobs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--delphes", type=Path, required=True)
    parser.add_argument("--events", type=int, help="Override all sample sizes for a small check")
    parser.add_argument("--detector-seed", type=int, default=0,
                        help="0 preserves the recorded automatic seeding; positive sets per-job seeds")
    args = parser.parse_args()
    jobs = prepare(args.work, args.delphes, args.events, args.detector_seed)
    print("Prepared", len(jobs), "jobs in", args.work)
