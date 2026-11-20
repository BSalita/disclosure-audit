"""Check records and keep the results: DIR/checked.jsonl, bad.jsonl, counts.json."""
import collections
import json
import os

from . import calibrate, checks, readers
from .records import call_kind, read_jsonl, write_jsonl


def check_record(r, dialect='auto', calibration=None):
    """The record with its verdict added, or None when nothing in it can be checked.
    Adds: hcp, shape, kind (pass, double, bid), head, wrong, class, cards_off, points_off."""
    if not r.get('text') and not r.get('stated'):
        return None
    if checks.hand_problem(r['hand']):
        raise ValueError(f"{r['hand']!r}: {checks.hand_problem(r['hand'])}")
    d = r.get('dialect') or dialect
    stated = r.get('stated') or readers.read(r['text'], d)
    if not checks.states_something(stated):
        return None
    hcp, _ = checks.hand_facts(r['hand'])
    symbols = d == 'symbols' or (d == 'auto' and readers.looks_like_symbols(r.get('text', '')))
    kind = call_kind(r['call'])
    head = readers.head(r['text']) if symbols else r['text'].strip()
    # cards of a suit in rank order, however the source wrote them
    r = {**r, 'hand': '.'.join(''.join(sorted(suit, key=checks.RANKS.index)) for suit in r['hand'].split('.'))}
    out = {**r, 'hcp': hcp, 'shape': checks.shape_text(r['hand']), 'kind': kind, 'head': head}
    if calibration and r['model'] == calibration.get('model'):
        # judged as the explanation would read once widened (calibrate.py); the record keeps the text as given
        stated = calibrate.widen(stated, calibrate.slack_for(calibration, kind, head))
        out['stated'] = stated
        out['widened'] = True
    return {**out, **checks.misfits(r['hand'], stated)}


def run(paths, out, dialect='auto', calibration=None):
    os.makedirs(out, exist_ok=True)
    if isinstance(calibration, str):
        with open(calibration, encoding='utf-8') as f:
            calibration = json.load(f)
    counts = {}
    unread = collections.defaultdict(collections.Counter)
    checked = []
    for r in read_jsonl(paths):
        c = counts.setdefault(r['model'], collections.Counter())
        c['calls'] += 1
        if not r.get('text') and not r.get('stated'):
            c['without an explanation'] += 1
            continue
        c['explained'] += 1
        try:
            v = check_record(r, dialect, calibration)
        except ValueError:
            c['bad hand, left out'] += 1
            continue
        if v is None:
            c['not checkable'] += 1
            unread[r['model']][r['text']] += 1
            continue
        c['checked'] += 1
        if v['class']:
            c['do not fit'] += 1
            c[v['class']] += 1
        checked.append(v)
    write_jsonl(os.path.join(out, 'checked.jsonl'), checked)
    write_jsonl(os.path.join(out, 'bad.jsonl'), (v for v in checked if v['class']))
    summary = {'sources': [paths] if isinstance(paths, str) else list(paths), 'dialect': dialect,
               'models': {m: dict(c) for m, c in counts.items()},
               'texts not checkable, most frequent': {m: u.most_common(40) for m, u in unread.items()}}
    with open(os.path.join(out, 'counts.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)
    return summary
