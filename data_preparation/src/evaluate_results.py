"""Evaluate already saved sample=s predictions against a separate truth key."""
import argparse
import csv
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from dataset_io import digest

LABELS = ('h', 'e', 'm', 't', 'n')


def event_id(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (ValueError, InvalidOperation):
        raise ValueError(f'Invalid event ID: {value!r}') from None


def calculate(records, truth_records):
    truth = {}
    for row in truth_records:
        key, label = event_id(row['nEvt']), row['true_channel']
        if key in truth or label not in LABELS:
            raise ValueError('Invalid or duplicate truth label')
        truth[key] = label
    if not truth:
        raise ValueError('Empty truth key')
    matrix, seen = Counter(), set()
    for row in records:
        if row['sample'] != 's':
            continue
        key = event_id(row['nEvt'])
        if key not in truth or key in seen:
            raise ValueError(f'Unknown or duplicate sample=s event ID: {key}')
        seen.add(key)
        predicted = str(row['class_auto']).strip()
        if predicted.lower() in ('', 'none', 'nan', '<na>', 'ambiguous', 'brak', 'unresolved'):
            predicted = 'unresolved'
        if predicted not in (*LABELS, 'unresolved'):
            raise ValueError(f'Unknown prediction: {predicted}')
        matrix[truth[key], predicted] += 1
    if not seen:
        raise ValueError('No sample=s predictions')
    per_class = []
    all_true = Counter(truth.values())
    for label in LABELS:
        tp = matrix[label, label]
        support = sum(v for (a, p), v in matrix.items() if a == label)
        predicted = sum(v for (a, p), v in matrix.items() if p == label)
        per_class.append(dict(channel=label, support=support, predicted=predicted, correct=tp,
                              truth_total=all_true[label], missing=all_true[label]-support,
                              retention=support/all_true[label] if all_true[label] else None,
                              precision=tp/predicted if predicted else None,
                              recall=tp/support if support else None,
                              f1=2*tp/(support+predicted) if support+predicted else None))
    n = len(seen)
    correct = sum(matrix[c, c] for c in LABELS)
    acc, z = correct/n, 1.959963984540054
    den = 1+z*z/n
    center = (acc+z*z/(2*n))/den
    half = z*math.sqrt(acc*(1-acc)/n+z*z/(4*n*n))/den
    supported = [r for r in per_class if r['support']]
    return dict(evaluated=n, truth_total=len(truth), missing=len(truth)-n,
                missing_ids=sorted(set(truth)-seen), retention=n/len(truth), correct=correct,
                accuracy=acc, accuracy_wilson95=[center-half, center+half],
                balanced_accuracy=sum(r['recall'] for r in supported)/len(supported),
                macro_f1=sum(r['f1'] for r in supported)/len(supported),
                macro_classes=[r['channel'] for r in supported],
                majority_baseline=max(r['support'] for r in per_class)/n,
                correct_over_original_truth=correct/len(truth),
                unresolved=sum(v for (a, p), v in matrix.items() if p == 'unresolved'),
                per_class=per_class,
                confusion={a: {p: matrix[a, p] for p in (*LABELS, 'unresolved')} for a in LABELS},
                note='Existing sample; independence from development is not established. Wilson intervals are statistical only. Macro metrics use true classes present in evaluated rows.')


def evaluate(results, truth, output):
    results, truth, output = map(Path, (results, truth, output))
    if output.exists():
        raise FileExistsError(output)
    hashes = dict(results_sha256=digest(results), truth_sha256=digest(truth))
    with results.open(encoding='utf-8-sig', newline='') as r, truth.open(encoding='utf-8-sig', newline='') as t:
        readers = csv.DictReader(r), csv.DictReader(t)
        for reader, required in zip(readers, ({'nEvt', 'sample', 'class_auto'}, {'nEvt', 'true_channel'})):
            if not required <= set(reader.fieldnames or []):
                raise ValueError(f'Missing required CSV columns: {sorted(required)}')
        summary = calculate(*readers)
    if hashes != dict(results_sha256=digest(results), truth_sha256=digest(truth)):
        raise ValueError('Inputs changed during evaluation')
    summary['truth_sha256'] = hashes['truth_sha256']
    output.mkdir(parents=True)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    for name, fields, rows in (
        ('per_class.csv', list(summary['per_class'][0]), summary['per_class']),
        ('confusion_matrix.csv', ['true_channel', *LABELS, 'unresolved'],
         [dict(true_channel=a, **summary['confusion'][a]) for a in LABELS]),
    ):
        with (output / name).open('x', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Evaluated {summary['evaluated']}/{summary['truth_total']}; accuracy={summary['accuracy']:.4%}; macro-F1={summary['macro_f1']:.4%}")
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('results', type=Path)
    p.add_argument('truth', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    evaluate(a.results, a.truth, a.output)
