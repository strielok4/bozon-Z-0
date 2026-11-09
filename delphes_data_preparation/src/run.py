"""Run prepared Pythia/Delphes jobs and the project exporter; no classifier changes."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess


def validate(path, expected):
    count = 0
    with path.open(encoding="utf-8") as stream:
        for count, line in enumerate(stream, 1):
            fields = line.split()
            if len(fields) != 27 or not all(math.isfinite(float(x)) for x in fields):
                raise ValueError("Invalid 27-column row in " + str(path))
            if int(fields[0]) != count - 1:
                raise ValueError("Non-sequential event ID")
            for start in (9, 15, 21):
                if int(fields[start]) not in (0, 1, 2, 3):
                    raise ValueError("Invalid object type")
    if count != expected:
        raise ValueError("Expected {} events, exported {} in {}".format(expected, count, path))
    return count


def run(work, delphes, selected, minimum_free_gib):
    manifest = json.loads((work / "manifest.json").read_text())
    jobs = manifest["jobs"]
    if selected:
        names = set(selected)
        if names - {job["sample"] for job in jobs}:
            raise ValueError("Unknown sample name")
        jobs = [job for job in jobs if job["sample"] in names]
    env = os.environ.copy()
    env["ROOT_INCLUDE_PATH"] = str(delphes) + os.pathsep + env.get("ROOT_INCLUDE_PATH", "")
    env["LD_LIBRARY_PATH"] = str(delphes) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    macro = Path(__file__).with_name("export_delphes.C").resolve()
    for job in jobs:
        sample = Path(job["sample"])
        root = work / "root" / sample.with_suffix(".root")
        data = work / "export" / sample.with_suffix(".dat")
        log = work / "logs" / sample.with_suffix(".log")
        for path in (root, data, log):
            if path.exists() or path.with_name(path.name + ".partial").exists():
                raise FileExistsError("Refusing to overwrite " + str(path))
            path.parent.mkdir(parents=True, exist_ok=True)
        for suffix, key in ((".cmnd", "pythia_sha256"), (".tcl", "detector_sha256")):
            path = work / "cards" / sample.with_suffix(suffix)
            if hashlib.sha256(path.read_bytes()).hexdigest() != job[key]:
                raise ValueError("Card changed after preparation: " + str(path))
        if shutil.disk_usage(work).free < minimum_free_gib * 1024**3:
            raise RuntimeError("Free space is below the configured floor")
        with log.open("x", encoding="utf-8") as stream:
            subprocess.run([str(delphes / "DelphesPythia8"),
                            str(work / "cards" / sample.with_suffix(".tcl")),
                            str(work / "cards" / sample.with_suffix(".cmnd")), str(root)],
                           env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
            args = ",".join(json.dumps(str(x)) for x in (root.parent, data.parent, sample.name))
            subprocess.run(["root", "-l", "-b", "-q", str(macro) + "(" + args + ")"],
                           env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        count = validate(data, job["events"])
        result = {**job, "exported_events": count, "dat_sha256": hashlib.sha256(data.read_bytes()).hexdigest()}
        data.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(job["sample"], count, "events OK", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--delphes", type=Path, required=True)
    parser.add_argument("--sample", action="append", help="e.g. train/e; repeat to select several")
    parser.add_argument("--minimum-free-gib", type=float, default=5)
    args = parser.parse_args()
    if args.minimum_free_gib < 0:
        parser.error("Minimum free space must be nonnegative")
    run(args.work.resolve(), args.delphes.resolve(), args.sample, args.minimum_free_gib)
