"""disclosure-audit: do the explanations of bridge calls fit the hands that made them?

    disclosure-audit import brill CACHE.jsonl ... --out records.jsonl
    disclosure-audit import lin FILE.lin ... --out records.jsonl [--model NAME]
    disclosure-audit import pbn FILE.pbn ... --out records.jsonl [--model NAME]
    disclosure-audit check records.jsonl ... --out DIR [--dialect auto|words|symbols]
    disclosure-audit report DIR [--config audit.json]
    disclosure-audit calibrate DIR --model NAME --out calibration.json

import  turns a file of explained calls into records (one call a line; see records.py).
check   compares every explanation with the hand and writes DIR/checked.jsonl (every call
        that could be judged), DIR/bad.jsonl (the log of those that do not fit) and
        DIR/counts.json.
report  writes DIR/reports/<model>/report.md and cases.csv, one pair a model, ready to send.
calibrate  fits, from the verdicts in DIR, how much wider a model's explanations would have
        to be to be true of the hands it holds (calibrate.py); `check --calibration FILE`
        then judges records as they would read once widened.
"""
import argparse
import json
import os
import sys

from . import audit, calibrate, report, sources
from .records import read_jsonl, write_jsonl


def main(argv=None):
    parser = argparse.ArgumentParser(prog='disclosure-audit', description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='what', required=True)
    i = sub.add_parser('import', help='another format -> records')
    i.add_argument('format', choices=['brill', 'lin', 'pbn'])
    i.add_argument('files', nargs='+')
    i.add_argument('--out', required=True)
    i.add_argument('--model', help='name for every call (default: brill-robots, or the player\'s name)')
    c = sub.add_parser('check', help='records -> verdicts')
    c.add_argument('records', nargs='+')
    c.add_argument('--out', required=True)
    c.add_argument('--dialect', choices=['auto', 'words', 'symbols'], default='auto')
    c.add_argument('--calibration', help='a table of `calibrate`: judge its model as widened by it')
    k = sub.add_parser('calibrate', help="verdicts -> the widening that would make a model's explanations true")
    k.add_argument('dir')
    k.add_argument('--model', required=True)
    k.add_argument('--out', required=True)
    k.add_argument('--target', type=float, default=0.03, help='share of calls that may stay outside, for each kind of explanation')
    k.add_argument('--caps', default='1,1,3,3', help='most widening: cards below, cards above, points below, points above')
    k.add_argument('--min-calls', type=int, default=30, help='explanations seen less often use the widening of their kind of call')
    r = sub.add_parser('report', help='verdicts -> one report a model')
    r.add_argument('dir')
    r.add_argument('--config')
    r.add_argument('--date', help='date printed in the reports (default: today)')
    args = parser.parse_args(argv)

    if args.what == 'import':
        kwargs = {'model': args.model} if args.model else {}
        n = write_jsonl(args.out, getattr(sources, args.format)(args.files, **kwargs))
        print(f'{n} calls -> {args.out}')
    elif args.what == 'check':
        summary = audit.run(args.records, args.out, args.dialect, args.calibration)
        for model, c in summary['models'].items():
            print(f"{model}: {c.get('checked', 0):,} explanations checked of {c.get('explained', 0):,} "
                  f"({c.get('calls', 0):,} calls), {c.get('do not fit', 0):,} do not fit "
                  f"({report.pct(c.get('do not fit', 0), c.get('checked', 0))})")
    elif args.what == 'calibrate':
        table = calibrate.fit_table(read_jsonl(os.path.join(args.dir, 'checked.jsonl')), args.model, args.target,
                                    tuple(int(n) for n in args.caps.split(',')), args.min_calls)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(table, f, indent=1, ensure_ascii=False)
        fitted = table['fitted on']
        print(f"{args.model}: {fitted['calls']:,} calls, outside {fitted['outside before']:,} -> {fitted['outside after']:,} "
              f"once widened; {len(table['heads'])} kinds of explanation with their own widening -> {args.out}")
    else:
        done = report.run(args.dir, args.config, args.date)
        print(json.dumps(done, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
