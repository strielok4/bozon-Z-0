"""Evaluate existing sample S predictions without rerunning the classifier.

Run this file in an IDE, or add the following at the end of main.py:
    from evaluate_sample_s import evaluate_sample_s
    evaluate_sample_s(data=work.data)

Without arguments, use debug/<dataset>/final_res.csv or the latest completed
archived run for DATASET in dataset_config.py. Write evaluation_s beside that CSV.
The results_path, truth_path and output_dir options are Python arguments, not CLI flags.
Join only by nEvt; preserve original event IDs after filtering.
MC truth is used only for evaluation. Importing this module runs no analysis.
Missing/ambiguous labels count as errors; absent events are reported separately.
Do not assume that filtering caused those events to be absent.
This report does not establish independence from earlier tuning.
JSON/CSV metrics are fractions in 0..1; the text report uses percentages.
"""

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from dataset_config import DATASET, DEBUG_DIR, TRUTH_PATH

BASE_DIR = Path(__file__).resolve().parent
LABELS = ('h', 'e', 'm', 't', 'n')
UNRESOLVED = 'unresolved'


def _event_id(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (InvalidOperation, ValueError):
        raise ValueError(f'Invalid nEvt: {value!r}') from None


def _read_csv(path, required):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        missing = set(required) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path}: missing columns {sorted(missing)}')
        return list(reader)


def _find_results():
    current = DEBUG_DIR / 'final_res.csv'
    if current.is_file():
        return current
    for manifest in sorted((BASE_DIR / 'runs').glob('*/manifest.json'), reverse=True):
        metadata = json.loads(manifest.read_text(encoding='utf-8-sig'))
        candidate = manifest.parent / 'debug' / 'final_res.csv'
        if (metadata.get('status') == 'complete'
                and metadata.get('dataset') == DATASET and candidate.is_file()):
            return candidate
    raise FileNotFoundError(f'No final_res.csv found for {DATASET}. Run main.py with that DATASET.')


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def calculate_metrics(records, truth_records):
    """Compute metrics without modifying input data or writing files."""
    truth = {}
    for row in truth_records:
        key = _event_id(row['nEvt'])
        label = str(row['true_channel']).strip()
        if key in truth or label not in LABELS:
            raise ValueError(f'Duplicate or invalid truth label: {key}, {label}')
        truth[key] = label
    if not truth:
        raise ValueError('The truth file is empty.')

    seen = set()
    counts = Counter()
    details = []
    for row in records:
        if str(row['sample']).strip() != 's':
            continue
        key = _event_id(row['nEvt'])
        if key in seen:
            raise ValueError(f'Duplicate nEvt in sample S: {key}')
        if key not in truth:
            raise ValueError(f'Missing truth label for nEvt={key}; check dataset compatibility.')
        seen.add(key)
        raw = str(row['class_auto']).strip()
        if raw in LABELS:
            predicted = raw
        elif raw.lower() in ('', 'nan', 'none', '<na>', 'ambiguous', 'brak', 'unresolved'):
            predicted = UNRESOLVED
        else:
            raise ValueError(f'Unknown class_auto={raw!r} for nEvt={key}')
        actual = truth[key]
        counts[actual, predicted] += 1
        details.append(dict(nEvt=key, true_channel=actual, predicted=predicted,
                            original_prediction=raw, correct=int(actual == predicted),
                            status='evaluated',
                            topology=','.join(str(row.get(c, '')) for c in
                                              ('nElectron', 'nMuon', 'nJet')),
                            class_reason=str(row.get('class_reason', ''))))
    if not seen:
        raise ValueError('No sample=s events found; the report was not saved.')

    total_truth = Counter(truth.values())
    predicted_counts = Counter()
    support = Counter()
    for (actual, predicted), count in counts.items():
        support[actual] += count
        predicted_counts[predicted] += count
    per_class = []
    for label in LABELS:
        tp = counts[label, label]
        size = support[label]
        predictions = predicted_counts[label]
        per_class.append(dict(channel=label, truth_total=total_truth[label], support=size,
                              missing=total_truth[label] - size,
                              retention=_ratio(size, total_truth[label]),
                              predicted=predictions, correct=tp,
                              precision=_ratio(tp, predictions), recall=_ratio(tp, size),
                              f1=_ratio(2 * tp, size + predictions)))
    for key in sorted(truth.keys() - seen):
        details.append(dict(nEvt=key, true_channel=truth[key], predicted='',
                            original_prediction='', correct='', status='missing_from_results',
                            topology='', class_reason=''))

    correct = sum(counts[label, label] for label in LABELS)
    n = len(seen)
    accuracy = correct / n
    # Wilson 95% interval: statistical uncertainty only; excludes tuning and systematic effects.
    z = 1.959963984540054
    denominator = 1 + z * z / n
    center = (accuracy + z * z / (2 * n)) / denominator
    half = z * math.sqrt(accuracy * (1 - accuracy) / n + z * z / (4 * n * n)) / denominator
    supported = [row for row in per_class if row['support']]
    summary = dict(truth_total=len(truth), evaluated=n, missing=len(truth) - n,
                   retention=n / len(truth), correct=correct, incorrect=n - correct,
                   unresolved=predicted_counts[UNRESOLVED], accuracy=accuracy,
                   accuracy_wilson95=[center - half, center + half],
                   balanced_accuracy=sum(row['recall'] for row in supported) / len(supported),
                   macro_f1=sum(row['f1'] for row in supported) / len(supported),
                   macro_classes=[row['channel'] for row in supported],
                   majority_baseline=max(support.values()) / n,
                   correct_over_original_truth=correct / len(truth),
                   per_class=per_class,
                   confusion={a: {p: counts[a, p] for p in (*LABELS, UNRESOLVED)} for a in LABELS})
    return summary, sorted(details, key=lambda row: row['nEvt'])


def evaluate_sample_s(data=None, *, results_path=None, truth_path=None, output_dir=None):
    """Evaluate a CSV or work.data DataFrame; return a summary and write reports."""
    truth_path = Path(truth_path) if truth_path is not None else TRUTH_PATH
    if data is not None and results_path is not None:
        raise ValueError('Provide either data or results_path, not both.')
    results = None if data is not None else (Path(results_path) if results_path is not None else _find_results())
    records = data.to_dict(orient='records') if data is not None else _read_csv(results, ('sample', 'nEvt', 'class_auto'))
    truth_records = _read_csv(truth_path, ('nEvt', 'true_channel'))
    summary, details = calculate_metrics(records, truth_records)
    output = Path(output_dir) if output_dir is not None else (results.parent if results else DEBUG_DIR) / 'evaluation_s'
    sources = {truth_path.resolve()}
    if results:
        sources.add(results.resolve())
    names = ('summary.json', 'report.txt', 'per_class.csv', 'confusion_matrix.csv', 'events.csv')
    if any((output / name).resolve() in sources for name in names):
        raise ValueError('The report must not overwrite input data.')
    summary.update(created_at=datetime.now(timezone.utc).isoformat(),
                   results_source=str(results.resolve()) if results else 'DataFrame supplied by the caller',
                   truth_source=str(truth_path.resolve()),
                   truth_sha256=hashlib.sha256(truth_path.read_bytes()).hexdigest(),
                   output_dir=str(output.resolve()))
    pct = lambda value: 'n/a' if value is None else f'{100 * value:.2f}%'
    lines = [f"Sample S: {summary['results_source']}",
             f"Evaluated {summary['evaluated']} / {summary['truth_total']}; absent: {summary['missing']}",
             f"Accuracy: {pct(summary['accuracy'])} ({correct_text(summary)})",
             f"Wilson 95% interval: {pct(summary['accuracy_wilson95'][0])} - {pct(summary['accuracy_wilson95'][1])}",
             f"Balanced accuracy: {pct(summary['balanced_accuracy'])}; macro-F1: {pct(summary['macro_f1'])}",
             f"Baseline (always predict the most frequent class): {pct(summary['majority_baseline'])}",
             f"Unresolved predictions (counted as errors): {summary['unresolved']}",
             f"Correct / entire original sample: {pct(summary['correct_over_original_truth'])}",
             '', 'Channel N      Precision  Recall     F1         Retained / truth']
    for row in summary['per_class']:
        lines.append(f"{row['channel']:5}  {row['support']:<7} {pct(row['precision']):10} {pct(row['recall']):10} {pct(row['f1']):10} {row['support']}/{row['truth_total']}")
    lines += ['', 'Matrix: rows=true labels, columns=predictions',
              'true,' + ','.join((*LABELS, UNRESOLVED))]
    lines += [a + ',' + ','.join(str(v) for v in summary['confusion'][a].values()) for a in LABELS]
    lines += ['', 'MC truth was used only to evaluate existing predictions.',
              'Evaluation of the existing sample S; independence from earlier tuning is not established.',
              'Absent events are excluded from accuracy; the reason for their absence is not determined.',
              'Macro-F1 and balanced accuracy cover classes present in the evaluated sample.',
              'Precision with no predictions: n/a; recall with no true events in the class: n/a.',
              'The Wilson interval excludes systematic uncertainties and tuning effects.']
    output.mkdir(parents=True, exist_ok=True)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    (output / 'report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    tables = [('per_class.csv', list(summary['per_class'][0]), summary['per_class']),
              ('events.csv', list(details[0]), details),
              ('confusion_matrix.csv', ['true_channel', *LABELS, UNRESOLVED],
               [dict(true_channel=a, **summary['confusion'][a]) for a in LABELS])]
    for name, fields, rows in tables:
        with (output / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print('\n'.join(lines))
    print(f'Reports: {output.resolve()}')
    return summary


def correct_text(summary):
    return f"{summary['correct']} / {summary['evaluated']}"


if __name__ == '__main__':
    evaluate_sample_s()
