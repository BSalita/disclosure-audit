#!/usr/bin/env python3
"""Records for disclosure-audit from BEN: the explanation BEN's REST API sends with each call.

Runs where BEN runs (it loads EPBot through BEN's bba/BBA.py); it does not need the
disclosure_audit package, so the file can be copied into a BEN container by itself.

    python ben_epbot.py --ben /path/to/ben --conf CONF --out records.jsonl --model NAME \
        (--games games.jsonl | --deals DEALS.jsonl --replay REPLAY.jsonl) [--seat S]

For every call of --seat in every board, the explanation is rebuilt the way gameapi.py
builds it (BBABotBid.explain_last_bid with the config's convention cards), and the numbers
behind the text are taken from EPBot directly (least and most cards a suit, features 402
and 403 for the points), so nothing has to be read back from the text.

extra.system_call is the call EPBot itself makes with the hand, extra.in_system whether the
call made is that one: a bad explanation of a system call is the describing program's
defect, a call outside the system is the bidder's.

--calibration FILE writes the text as BEN sends it with [sampling] disclosure_calibration
= FILE (BEN's src/disclosure.py widens the numbers), and leaves `stated` out, so that the
audit reads the numbers from the final text, as a receiver would.

Boards: --games (one line a deal with hands [N, E, S, W], calls, dealer, vul; the format of
BEN's scripts/selfplay/selfplay_gen.py), or --deals (tournament_id, board, deal in PBN
form, dealer, vul, scoring) with --replay (tournament_id, board, walk = the calls).
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
from configparser import ConfigParser

SEATS = 'NESW'
VULN = {'None': [False, False], 'NS': [True, False], 'EW': [False, True], 'All': [True, True]}
W = {}


def hands_nesw(deal):
    first = SEATS.index(deal[0])
    hands = deal[2:].split()
    return [hands[(i - first) % 4] for i in range(4)]


def init(cfg):
    src = os.path.join(cfg['ben'], 'src')
    sys.path.insert(0, src)
    os.chdir(src)
    W['cfg'] = cfg


def chunk(boards):
    from bba.BBA import BBABotBid
    cfg = W['cfg']
    seat = SEATS.index(cfg['seat'])
    out = []
    for b in boards:
        try:
            hand = hands_nesw(b['deal'])[seat]
            dealer_i = SEATS.index(b['dealer'])
            bot = BBABotBid(cfg['our_cc'], cfg['their_cc'], seat, hand, VULN[b['vul']], dealer_i, b.get('scoring') == 'MP', False)
            calls = ['PASS' if c == 'P' else c for c in b['walk']]
            for i, call in enumerate(calls):
                if (dealer_i + i) % 4 != seat:
                    continue
                before = ['PAD_START'] * dealer_i + calls[:i]
                try:
                    system_call = bot.bid(before).bid
                except Exception as error:
                    system_call = f'error: {error}'
                text, artificial = bot.explain_last_bid(before + [call])
                if cfg['calibration']:
                    import disclosure
                    text = disclosure.calibrate_text(text, call, disclosure.load(cfg['calibration']))
                player = bot.players[bot.position]
                least = player.get_info_min_length(seat)
                most = player.get_info_max_length(seat)
                lo, hi = bot.extract_hcp(seat)[:2]
                # EPBot's suit order is clubs, diamonds, hearts, spades
                lengths = {s: [int(least[k]) or None, int(most[k]) if int(most[k]) < 13 else None] for k, s in enumerate('CDHS')}
                out.append({'model': cfg['model'], 'source': cfg['source'], 'event': b.get('tournament_id'), 'board': b.get('board'),
                            'seat': cfg['seat'], 'dealer': b['dealer'], 'vul': b['vul'], 'hand': hand,
                            'auction': b['walk'][:i], 'call': b['walk'][i], 'text': text, 'dialect': 'symbols',
                            **({} if cfg['calibration'] else {
                                'stated': {'lengths': {s: v for s, v in lengths.items() if v != [None, None]},
                                           'points': [int(lo) if lo > 0 else None, int(hi) if hi < 37 else None]}}),
                            'extra': {'system_call': 'P' if system_call == 'PASS' else system_call,
                                      'in_system': system_call == call, 'artificial': bool(artificial),
                                      'our_call_number': sum(1 for j in range(i) if (dealer_i + j) % 4 == seat) + 1}})
        except Exception as error:
            out.append({'error': f'{type(error).__name__}: {error}', 'event': b.get('tournament_id'), 'board': b.get('board')})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--ben', default=os.environ.get('BEN_ROOT'), help='the BEN folder (default: $BEN_ROOT)')
    p.add_argument('--conf', required=True, help='BEN config; its [models] bba_our_cc and bba_their_cc are used')
    p.add_argument('--out', required=True)
    p.add_argument('--model', required=True, help='name of the bidder in the reports')
    p.add_argument('--source', help='name of this set of boards in the records (default: the file name)')
    p.add_argument('--games')
    p.add_argument('--deals')
    p.add_argument('--replay')
    p.add_argument('--seat', default='S')
    p.add_argument('--calibration', help='a table of `disclosure-audit calibrate`: the text as BEN sends it with that table')
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--limit', type=int, default=0)
    args = p.parse_args()
    if not args.ben or not os.path.isdir(os.path.join(args.ben, 'src', 'bba')):
        raise SystemExit('Give --ben (the BEN folder, with src/bba in it).')
    conf = ConfigParser()
    with open(args.conf) as f:
        conf.read_file(f)
    ccs = [os.path.join(args.ben, conf.get('models', key)) for key in ('bba_our_cc', 'bba_their_cc')]   # as Models.from_conf
    for cc in ccs:
        if not os.path.isfile(cc):
            raise SystemExit(f'convention card not found: {cc}')
    boards = []
    if args.games:
        for line in open(args.games, encoding='utf-8'):
            g = json.loads(line)
            if 'error' not in g:
                boards.append({**{k: g.get(k) for k in ('tournament_id', 'board', 'dealer', 'vul', 'scoring')},
                               'deal': 'N:' + ' '.join(g['hands']), 'walk': g['calls']})
    elif args.deals and args.replay:
        deals = {}
        for line in open(args.deals, encoding='utf-8'):
            d = json.loads(line)
            deals[d['tournament_id'], d['board']] = d
        for line in open(args.replay, encoding='utf-8'):
            r = json.loads(line)
            d = deals.get((r['tournament_id'], r['board']))
            if d is not None and 'walk' in r:
                boards.append({**{k: d.get(k) for k in ('tournament_id', 'board', 'deal', 'dealer', 'vul', 'scoring')}, 'walk': r['walk']})
    else:
        raise SystemExit('Give --games, or --deals and --replay.')
    if args.limit:
        boards = boards[:args.limit]
    source = args.source or os.path.basename(args.games or args.replay)
    cfg = {'ben': os.path.abspath(args.ben), 'our_cc': ccs[0], 'their_cc': ccs[1], 'seat': args.seat, 'model': args.model, 'source': source,
           'calibration': os.path.abspath(args.calibration) if args.calibration else None}
    chunks = [boards[i:i + 20] for i in range(0, len(boards), 20)]
    n = errors = 0
    with mp.get_context('spawn').Pool(min(args.workers, max(1, len(chunks))), initializer=init, initargs=(cfg,)) as pool, \
            open(args.out, 'w', encoding='utf-8') as out:
        for part in pool.imap(chunk, chunks):
            for r in part:
                if 'error' in r:
                    errors += 1
                    if errors <= 5:
                        print(r, file=sys.stderr)
                    continue
                out.write(json.dumps(r) + '\n')
                n += 1
    print(f'{n} calls of {len(boards)} boards -> {args.out}' + (f'; {errors} boards failed' if errors else ''))


if __name__ == '__main__':
    main()
