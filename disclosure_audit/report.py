"""One report a model, written to be sent to the model's author as it is.

DIR/reports/<model>/report.md is Markdown (reads as plain text in a mail, renders in a
ticket) and cases.csv holds every explanation of that model that does not fit.

A config file (JSON) is optional. Everything in it is optional too:

    {"from": "who prepared the report",
     "models": {"<model>": {"title": "...", "to": "who it is for", "intro": "a paragraph for the top",
                            "checked": ["a line for 'What was checked'", ...],
                            "breakdown": ["side"],            extra fields to count by
                            "evidence": ["requires"],         extra fields shown beside every case
                            "notes": "file.md"}},             text added near the end (what you suggest)
     "views": {"<name>": {"of": "<model>", "where": {"in_system": true}, ... as a model ...}}}

A view is a report on some of a model's calls, picked by extra fields: for example the
calls a second program agrees with.
"""
import collections
import csv
import datetime
import json
import os

from .checks import CLASSES, CLASS_TEXT
from .records import read_jsonl


def _json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def pct(a, b):
    return f'{100 * a / b:.1f}%' if b else 'n/a'


def md_table(header, rows):
    out = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    out += ['| ' + ' | '.join(str(c).replace('|', '\\|').replace('\n', ' ') for c in row) + ' |' for row in rows]
    return out


def code(text, limit=110):
    text = str(text if text is not None else '')
    return f'`{text[:limit]}`' if text else ''


def auction_text(calls):
    return ' '.join(calls) if calls else '(first to call)'


def where_text(r):
    parts = [str(r[k])[:12] for k in ('event', 'board') if r.get(k) not in (None, '')]
    return ' / '.join(parts)


def class_rows(rows):
    c = collections.Counter(r['class'] for r in rows if r['class'])
    return [[CLASS_TEXT[k], c.get(k, 0)] for k in CLASSES]


def examples(rows, evidence, n=3):
    out, seen = [], set()
    has_where = any(where_text(r) for r in rows)
    for r in sorted(rows, key=lambda r: CLASSES.index(r['class'])):
        if r['hand'] in seen:
            continue
        seen.add(r['hand'])
        row = ([where_text(r)] if has_where else []) + [r.get('seat', ''), code(r['hand']), r['hcp'],
                                                         auction_text(r.get('auction')), r['call'], r.get('text', ''),
                                                         '; '.join(r['wrong'])]
        row += [code((r.get('extra') or {}).get(k), 90) for k in evidence]
        out.append(row)
        if len(out) == n:
            break
    header = (['Event / board'] if has_where else []) + ['Seat', 'Hand (S.H.D.C)', 'HCP', 'Auction before', 'Call',
                                                       'Explanation', 'Does not fit'] + evidence
    return md_table(header, out)


def write_report(name, rows, out, conf, common, counts, today):
    bad = [r for r in rows if r['class']]
    os.makedirs(out, exist_ok=True)
    evidence = conf.get('evidence', [])
    by_class = collections.Counter(r['class'] for r in bad)
    lines = [f"# {conf.get('title') or name + ': explanations that do not fit the hand'}", '',
             f"Prepared {today}" + (f" by {common['from']}" if common.get('from') else '')
             + (f", for {conf['to']}" if conf.get('to') else '') + '.', '', '## In short', '']
    if conf.get('intro'):
        lines += [conf['intro'], '']
    lines += [f"Of {len(rows):,} explanations that state something countable (cards in a suit, a range of high-card "
              f"points, \"balanced\"), **{len(bad):,} ({pct(len(bad), len(rows))}) do not fit the hand that made the call**: "
              f"{by_class.get('length 2+', 0):,} by two or more cards in a suit, {by_class.get('length 1', 0):,} by one card, "
              f"{by_class.get('points 2+', 0):,} by two or more points, {by_class.get('points 1', 0):,} by one point.", '',
              '## What was checked', '']
    lines += [f'- {line}' for line in conf.get('checked', [])]
    if counts:
        lines += [f"- {counts.get('calls', 0):,} calls in the files; {counts.get('explained', 0):,} came with an explanation; "
                  f"{counts.get('checked', 0):,} of those state numbers and were checked"
                  + (f" ({counts['not checkable']:,} have a text without numbers, such as \"natural\" or \"forcing\", "
                     f"and are not judged)." if counts.get('not checkable') else '.')]
    lines += ['- The numbers come from the text, or from the program that wrote it when it gives them. Read: least and '
              'most cards in a suit, least and most high-card points, and "balanced" (taken as no singleton and no void). '
              '"Points" that may count distribution are not checked.',
              '- The hand is the one that made the call, so the comparison is exact. A call is listed when the hand is '
              'outside what was stated. One point outside is counted apart: it is usually an upgrade and matters less.',
              '', '## Numbers', '']
    lines += md_table(['How far off', 'Calls'], class_rows(bad)) + ['']
    for key in ['kind'] + conf.get('breakdown', []):
        value = (lambda r: r['kind']) if key == 'kind' else (lambda r: (r.get('extra') or {}).get(key))
        table = collections.defaultdict(collections.Counter)
        for r in rows:
            table[str(value(r))]['calls'] += 1
            table[str(value(r))]['bad'] += bool(r['class'])
        lines += md_table(['Kind of call' if key == 'kind' else key, 'Checked', 'Do not fit', 'Share'],
                          [[k, v['calls'], v['bad'], pct(v['bad'], v['calls'])] for k, v in sorted(table.items())]) + ['']

    groups = collections.defaultdict(list)
    totals = collections.Counter((r['kind'], r['head']) for r in rows)
    for r in bad:
        groups[r['kind'], r['head']].append(r)
    order = sorted(groups, key=lambda k: -len(groups[k]))
    lines += ['## The explanations that most often do not fit', '',
              'Rate = share of the times the explanation was given in which the hand was outside it.', '']
    table = []
    for k in order[:25]:
        g = groups[k]
        c = collections.Counter(r['class'] for r in g)
        most = collections.Counter(w for r in g for w in r['wrong']).most_common(1)[0][0]
        row = [k[0], code(k[1], 70), len(g), pct(len(g), totals[k]), most,
               c.get('length 2+', 0) + c.get('length 1', 0), c.get('points 2+', 0) + c.get('points 1', 0)]
        for e in evidence:
            row.append(code(collections.Counter(str((r.get('extra') or {}).get(e) or '') for r in g).most_common(1)[0][0]))
        table.append(row)
    lines += md_table(['Call', 'Explanation', 'Do not fit', 'Rate', 'Most frequent misfit', 'By length', 'By points']
                      + evidence, table)
    lines += ['', '## Examples', '']
    for k in order[:conf.get('examples', 10)]:
        lines += [f'**{k[0]}: {code(k[1], 90)}** ({len(groups[k])} calls)', ''] + examples(groups[k], evidence) + ['']
    notes = conf.get('notes')
    if notes:
        path = notes if os.path.isabs(notes) else os.path.join(common['config_dir'], notes)
        with open(path, encoding='utf-8') as f:
            lines += [f.read().rstrip(), '']
    lines += ['## Files', '',
              '`cases.csv`: every call listed here, one a row: where it was (when known), seat, dealer, vulnerability, '
              'hand, points, shape, the auction before, the call, the explanation, what does not fit and how far.', '',
              '_Made with disclosure-audit: the check can be run again on any new set of calls._', '']
    with open(os.path.join(out, 'report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    extra_keys = sorted({k for r in bad for k in (r.get('extra') or {})})
    columns = ['model', 'source', 'event', 'board', 'seat', 'dealer', 'vul', 'hand', 'hcp', 'shape', 'auction', 'call',
               'text', 'wrong', 'class']
    with open(os.path.join(out, 'cases.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(columns + extra_keys)
        for r in bad:
            row = [' '.join(r[c]) if c == 'auction' and isinstance(r.get(c), list) else
                   '; '.join(r[c]) if isinstance(r.get(c), list) else r.get(c, '') for c in columns]
            w.writerow(row + [(r.get('extra') or {}).get(k, '') for k in extra_keys])
    return {'checked': len(rows), 'do not fit': len(bad)}


def run(directory, config=None, today=None):
    today = today or datetime.date.today().isoformat()
    conf = _json(config) if config else {}
    common = {'from': conf.get('from'), 'config_dir': os.path.dirname(os.path.abspath(config)) if config else '.'}
    counts = _json(os.path.join(directory, 'counts.json'))['models']
    by_model = collections.defaultdict(list)
    for r in read_jsonl(os.path.join(directory, 'checked.jsonl')):
        by_model[r['model']].append(r)
    out_root = os.path.join(directory, 'reports')
    done = {}
    for model, rows in by_model.items():
        done[model] = write_report(model, rows, os.path.join(out_root, model), conf.get('models', {}).get(model, {}),
                                   common, counts.get(model), today)
    for name, view in conf.get('views', {}).items():
        rows = [r for r in by_model.get(view['of'], [])
                if all((r.get('extra') or {}).get(k) == v for k, v in view.get('where', {}).items())]
        done[name] = write_report(name, rows, os.path.join(out_root, name), view, common, None, today)
    lines = ['# Explanations that do not fit the hand', '', f'{today}', '']
    lines += md_table(['Model', 'Explanations checked', 'Do not fit', 'Share', 'Report'],
                      [[m, f"{d['checked']:,}", f"{d['do not fit']:,}", pct(d['do not fit'], d['checked']),
                        f'[{m}/report.md]({m}/report.md)'] for m, d in done.items()])
    with open(os.path.join(out_root, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return done
