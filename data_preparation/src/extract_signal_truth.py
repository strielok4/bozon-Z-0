"""Extract visible Z decay labels from PYTHIA 5.7 LUJETS FADGEN records."""
import argparse
import csv
import struct
from pathlib import Path


def labels(path: Path):
    with path.open("rb") as stream:
        event = 0
        while (prefix := stream.read(4)):
            if len(prefix) != 4:
                raise ValueError("Truncated record marker")
            (size,) = struct.unpack("<i", prefix)
            if size < 4 or size > 4 + 4000 * 60 or (size - 4) % 60:
                raise ValueError(f"Event {event + 1}: invalid record length")
            data = stream.read(size)
            suffix = stream.read(4)
            if len(data) != size or len(suffix) != 4 or struct.unpack("<i", suffix)[0] != size:
                raise ValueError(f"Event {event + 1}: incomplete record")
            (count,) = struct.unpack_from("<i", data)
            if count != (size - 4) // 60:
                raise ValueError(f"Event {event + 1}: particle count mismatch")
            particles = [struct.unpack_from("<5i", data, 4 + 60 * i)
                         for i in range(count)]
            roots = [i + 1 for i, k in enumerate(particles) if k[1] == 23 and k[2] == 0]
            if len(roots) != 1:
                raise ValueError(f"Event {event + 1}: expected one primary Z, got {roots}")
            daughter_ids = [abs(k[1]) for k in particles
                            if k[2] == roots[0] and abs(k[1]) in (1, 2, 3, 4, 5, 11, 13, 15)]
            if len(daughter_ids) != 2 or daughter_ids[0] != daughter_ids[1]:
                raise ValueError(f"Event {event + 1}: unexpected Z daughters {daughter_ids}")
            pid = daughter_ids[0]
            channel = "h" if pid in (1, 2, 3, 4, 5) else {11: "e", 13: "m", 15: "t"}.get(pid)
            if channel is None:
                raise ValueError(f"Event {event + 1}: unsupported Z decay {pid}")
            event += 1
            yield event, channel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-events", type=int)
    parser.add_argument("--events-file", type=Path,
                        help="Exported DELPHI .dat; keep truth only for reconstructed event IDs")
    args = parser.parse_args()
    rows = list(labels(args.input))
    if not rows:
        raise ValueError('Empty generator input')
    if args.expected_events is not None and len(rows) != args.expected_events:
        raise ValueError(f"Expected {args.expected_events} events, got {len(rows)}")
    if args.events_file is not None:
        selected = []
        for line in args.events_file.read_text().splitlines():
            fields = line.split()
            if len(fields) != 27:
                raise ValueError("Expected 27 fields in exported event")
            selected.append(int(fields[0]))
        if len(selected) != len(set(selected)):
            raise ValueError("Duplicate reconstructed event IDs")
        lookup = dict(rows)
        if not set(selected) <= lookup.keys():
            raise ValueError("Reconstructed event ID absent from generator truth")
        rows = [(number, lookup[number]) for number in selected]
    with args.output.open("x", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("nEvt", "true_channel"))
        writer.writerows(rows)
    counts = {channel: sum(label == channel for _, label in rows) for channel in "hemt"}
    print(f"events={len(rows)} channel_counts={counts} output={args.output}")


if __name__ == "__main__":
    main()
