"""How much wider would a model's explanations have to be to be true of the hands it holds?

For each kind of explanation (the kind of call and the words of the text) the smallest
widening is fitted that leaves at most `target` of the calls outside: cards below a stated
least, cards above a stated most, points below, points above. The widening depends on the
explanation only, never on the hand, so a text widened this way describes the bidder's
practice without telling more about one hand than the practice shows.

    disclosure-audit calibrate DIR --model NAME --out calibration.json     (DIR of `check`)
    disclosure-audit check held-out.records.jsonl --out DIR2 --calibration calibration.json

Fit on one set of boards and check on another: the second line shows what is left on boards
the fit has not seen. What is left after widening are the bidder's real deviations.

The table: {"model", "target", "caps", "heads": {"<kind>|<words>": [l-, l+, p-, p+]},
"fallback": {"<kind>": [...]}}. A program that writes the explanations applies it (BEN:
src/disclosure.py).
"""
import collections

SUITS = 'SHDC'


def deficits(r):
    """(cards short of a stated least, cards over a stated most, points short, points over) of a checked record."""
    stated = r.get('stated')
    if stated is None:
        from . import readers
        stated = readers.read(r['text'], r.get('dialect') or 'auto')
    shape = dict(zip(SUITS, (len(s) for s in r['hand'].split('.'))))
    short = over = 0
    for suit, (lo, hi) in (stated.get('lengths') or {}).items():
        if lo:
            short = max(short, lo - shape[suit])
        if hi is not None:
            over = max(over, shape[suit] - hi)
    lo, hi = stated.get('points') or (None, None)
    return short, over, max((lo or 0) - r['hcp'], 0), max(r['hcp'] - hi, 0) if hi is not None else 0


def left(rows, slack):
    return sum(any(d[i] > slack[i] for i in range(4)) for d in rows)


def fit(rows, target, caps):
    """The smallest widening [l-, l+, p-, p+] within caps that leaves at most `target` of rows outside:
    one step at a time, each time the step that brings most calls inside."""
    slack = [0, 0, 0, 0]
    while left(rows, slack) > target * len(rows):
        best = None
        for i in range(4):
            if slack[i] < caps[i]:
                trial = slack.copy()
                trial[i] += 1
                gain = left(rows, slack) - left(rows, trial)
                if gain > 0 and (best is None or gain > best[0]):
                    best = (gain, trial)
        if best is None:
            break
        slack = best[1]
    return slack


def fit_table(checked, model, target=0.03, caps=(1, 1, 3, 3), min_calls=30):
    by_head = collections.defaultdict(list)
    by_kind = collections.defaultdict(list)
    for r in checked:
        if r['model'] == model:
            d = deficits(r)
            by_head[f"{r['kind']}|{r['head']}"].append(d)
            by_kind[r['kind']].append(d)
    if not by_kind:
        raise SystemExit(f'no checked calls of model {model!r}')
    heads = {k: fit(rows, target, caps) for k, rows in by_head.items() if len(rows) >= min_calls}
    # the explanations seen too seldom for a widening of their own share one, fitted on them together
    rare = collections.defaultdict(list)
    for k, rows in by_head.items():
        if k not in heads:
            rare[k.split('|')[0]] += rows
    fallback = {k: fit(rare[k], target, caps) if rare.get(k) else [0, 0, 0, 0] for k in by_kind}
    n = sum(map(len, by_kind.values()))
    before = sum(left(rows, [0, 0, 0, 0]) for rows in by_head.values())
    after = sum(left(rows, heads.get(k) or fallback[k.split('|')[0]]) for k, rows in by_head.items())
    return {'model': model, 'target': target, 'caps': list(caps), 'min_calls': min_calls,
            'fitted on': {'calls': n, 'outside before': before, 'outside after': after},
            'fallback': fallback, 'heads': dict(sorted(heads.items(), key=lambda kv: -len(by_head[kv[0]])))}


def slack_for(table, kind, head):
    return table.get('heads', {}).get(f'{kind}|{head}') or table.get('fallback', {}).get(kind) or [0, 0, 0, 0]


def widen(stated, slack):
    """`stated` with its numbers widened; what is not stated stays not stated."""
    less, more, lighter, heavier = slack
    lengths = {}
    for suit, (lo, hi) in (stated.get('lengths') or {}).items():
        lo = max(lo - less, 0) or None if lo else lo
        hi = hi + more if hi is not None else None
        lengths[suit] = [lo, None if hi is not None and hi >= 13 else hi]
    lo, hi = stated.get('points') or (None, None)
    lo = max(lo - lighter, 0) or None if lo else lo
    hi = hi + heavier if hi is not None else None
    return {**stated, 'lengths': lengths, 'points': [lo, hi]}
