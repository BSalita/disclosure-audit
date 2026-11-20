"""disclosure-audit: do the explanations of bridge calls fit the hands that made them?

    disclosure-audit import brill CACHE.jsonl ... --out records.jsonl
    disclosure-audit import lin FILE.lin ... --out records.jsonl [--model NAME]
    disclosure-audit import pbn FILE.pbn ... --out records.jsonl [--model NAME]
    disclosure-audit check records.jsonl ... --out DIR [--dialect auto|words|symbols]
    disclosure-audit report DIR [--config audit.json]

import  turns a file of explained calls into records (one call a line; see records.py).
check   compares every explanation with the hand and writes DIR/checked.jsonl (every call
        that could be judged), DIR/bad.jsonl (the log of those that do not fit) and
        DIR/counts.json.
report  writes DIR/reports/<model>/report.md and cases.csv, one pair a model, ready to send.
"""
import argparse
import json
import sys

from . import audit, report, sources
from .records import write_jsonl


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
        summary = audit.run(args.records, args.out, args.dialect)
        for model, c in summary['models'].items():
            print(f"{model}: {c.get('checked', 0):,} explanations checked of {c.get('explained', 0):,} "
                  f"({c.get('calls', 0):,} calls), {c.get('do not fit', 0):,} do not fit "
                  f"({report.pct(c.get('do not fit', 0), c.get('checked', 0))})")
    else:
        done = report.run(args.dir, args.config, args.date)
        print(json.dumps(done, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
