"""Check the Fortran sequential LUJETS records of a DELPHI FADGEN file."""
import argparse
import math
import struct
from pathlib import Path


def check(path: Path) -> None:
    events = 0
    with path.open("rb") as source:
        while True:
            prefix = source.read(4)
            if not prefix:
                break
            if len(prefix) != 4:
                raise ValueError("Truncated Fortran record marker")
            (size,) = struct.unpack("<i", prefix)
            if size < 4 or size > 4 + 4000 * 60 or (size - 4) % 60:
                raise ValueError(f"Event {events + 1}: invalid record length {size}")
            record = source.read(size)
            suffix = source.read(4)
            if len(record) != size or len(suffix) != 4:
                raise ValueError(f"Event {events + 1}: truncated record")
            if struct.unpack("<i", suffix)[0] != size:
                raise ValueError(f"Event {events + 1}: marker mismatch")
            (count,) = struct.unpack_from("<i", record)
            if count != (size - 4) // 60 or not 2 < count < 4000:
                raise ValueError(f"Event {events + 1}: invalid particle count {count}")
            energy = 0.0
            for index in range(count):
                offset = 4 + 60 * index
                status, pid, *_ = struct.unpack_from("<5i", record, offset)
                px, py, pz, e, mass = struct.unpack_from("<5f", record, offset + 20)
                if not all(map(math.isfinite, (px, py, pz, e, mass))):
                    raise ValueError(f"Event {events + 1}: non-finite particle")
                if index == 0 and (status, pid) != (21, 11):
                    raise ValueError(f"Event {events + 1}: invalid electron beam")
                if index == 1 and (status, pid) != (21, -11):
                    raise ValueError(f"Event {events + 1}: invalid positron beam")
                if index >= 2:
                    if status != 1:
                        raise ValueError(f"Event {events + 1}: unexpected final status")
                    energy += e
            if abs(energy - 91.25) > 0.1:
                raise ValueError(f"Event {events + 1}: final energy {energy:.3f} GeV")
            events += 1
    if not events:
        raise ValueError("Empty FADGEN file")
    print(f"FADGEN OK: events={events} file={path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    check(parser.parse_args().input)
