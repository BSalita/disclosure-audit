"""Importers: files of explained calls in other formats -> records (records.py).

  brill   the saved answers of the Brill Bridge Challenge /bid service
  lin     BBO .lin files (explanations in an| after a call)
  pbn     PBN files with [Note "n:text"] referred to as =n= in the auction

An engine that can explain its own calls needs no importer: have it write the records
itself (adapters/ben_epbot.py does that for BEN with EPBot).
"""
import re

from .records import SEATS, hands_nesw, normalize_call

RANK_ORDER = 'AKQJT98765432'


def _text(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


# ----------------------------------------------------------------------- Brill

def brill(paths, model='brill-robots'):
    """Cache lines {"key": "seat|hand|dealer|vul|scoring|ctx", "bid", "means", "requires", "ruleSet"}.
    Answers without a text are not explained calls and are left out (counted by the caller)."""
    import json
    seen = set()
    for path in paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                if r['key'] in seen:
                    continue
                seen.add(r['key'])
                seat, hand, dealer, vul, scoring, ctx = r['key'].split('|')
                text = r.get('means')
                yield {'model': model, 'source': 'brill /bid', 'seat': seat, 'dealer': dealer, 'vul': vul, 'hand': hand,
                       'auction': [normalize_call(ctx[i:i + 2]) for i in range(0, len(ctx), 2)],
                       'call': normalize_call(r['bid']), 'text': text or '', 'dialect': 'words',
                       'extra': {'side': 'partner' if seat == 'N' else 'opponent', 'scoring': scoring,
                                 'rule_set': r.get('ruleSet'), 'requires': r.get('requires')}}


# ------------------------------------------------------------------------- LIN

def _lin_hand(text):
    """'SAKQHT9D32C5' -> 'AKQ.T9.32.5'"""
    suits = {s: '' for s in 'SHDC'}
    current = None
    for c in text.upper():
        if c in suits:
            current = c
        elif current and c in RANK_ORDER:
            suits[current] += c
    return '.'.join(''.join(sorted(suits[s], key=RANK_ORDER.index)) for s in 'SHDC')


def _fourth_hand(hands):
    out = []
    for i in range(4):
        used = set(''.join(h.split('.')[i] for h in hands))
        out.append(''.join(r for r in RANK_ORDER if r not in used))
    return '.'.join(out)


def lin(paths, model=None):
    """BBO .lin: md|<dealer digit><South>,<West>,<North>[,<East>]| sv|o n e b| mb|call| an|text| ...
    One board a qx| or md| group; pn| gives the players South, West, North, East.
    model: one name for every call, or None = the player's name (lower case)."""
    for path in paths:
        text = _text(path)
        tokens = text.replace('\r', '').replace('\n', '').split('|')
        pairs = list(zip(tokens[0::2], tokens[1::2]))
        players = ['South', 'West', 'North', 'East']
        board = {}
        calls = []

        def flush():
            if board.get('hands') and calls:
                dealer = board['dealer']
                for i, (call, note) in enumerate(calls):
                    seat = (dealer + i) % 4
                    if note:
                        name = players['SWNE'.index(SEATS[seat])]
                        yield {'model': model or name.lower(), 'source': path, 'event': board.get('event'),
                               'board': board.get('number'), 'seat': SEATS[seat], 'dealer': SEATS[dealer],
                               'vul': board.get('vul', 'None'), 'hand': board['hands'][seat],
                               'auction': [c for c, _ in calls[:i]], 'call': call, 'text': note,
                               'extra': {'player': name}}

        for key, value in pairs:
            key = key.strip().lower()
            if key == 'pn':
                names = value.split(',')
                if len(names) >= 4:
                    players = names[:4]
            elif key == 'qx':
                yield from flush()
                board, calls = {'number': value}, []
            elif key == 'md':
                if board.get('hands'):
                    yield from flush()
                    board, calls = {'number': board.get('number')}, []
                parts = value[1:].split(',')
                hands = [_lin_hand(p) for p in parts[:4] if p]
                if len(hands) == 3:
                    hands.append(_fourth_hand(hands))
                if len(hands) == 4:           # LIN order is South, West, North, East
                    board['hands'] = [hands[2], hands[3], hands[0], hands[1]]
                    board['dealer'] = SEATS.index('SWNE'[int(value[0]) - 1])
            elif key == 'sv':
                board['vul'] = {'o': 'None', '0': 'None', 'n': 'NS', 'e': 'EW', 'b': 'All'}.get(value.lower(), 'None')
            elif key == 'ah':
                board.setdefault('number', value.replace('Board', '').strip())
            elif key == 'mb':
                try:
                    calls.append([normalize_call(value), ''])
                except ValueError:
                    pass
            elif key == 'an' and calls:
                calls[-1][1] = value.strip()
        yield from flush()


# ------------------------------------------------------------------------- PBN

def pbn(paths, model=None):
    """PBN games: [Deal], [Dealer], [Vulnerable], [Auction "X"] with calls and =n= references, [Note "n:text"].
    model: one name for every call, or None = the player's name from [North] .. [West] (lower case)."""
    vul_of = {'none': 'None', 'love': 'None', '-': 'None', 'ns': 'NS', 'n-s': 'NS', 'ew': 'EW', 'e-w': 'EW',
              'all': 'All', 'both': 'All'}
    for path in paths:
        games = re.split(r'\n\s*\n', _text(path).replace('\r', ''))
        for game in games:
            tags = dict(re.findall(r'\[(\w+)\s+"([^"]*)"\]', game))
            m = re.search(r'\[Auction\s+"([NESW])"\]\s*\n(.*?)(?=\n\[|\Z)', game, re.S)
            if not m or 'Deal' not in tags:
                continue
            notes = {}
            for n, text in re.findall(r'\[Note\s+"(\d+):([^"]*)"\]', game):
                notes[n] = text.strip()
            hands = hands_nesw(tags['Deal'])
            first = SEATS.index(m.group(1))
            calls = []
            for token in m.group(2).split():
                ref = re.fullmatch(r'=(\d+)=', token)
                if ref:
                    if calls:
                        calls[-1][1] = notes.get(ref.group(1), '')
                    continue
                if token.upper() == 'AP':
                    calls += [['P', ''], ['P', ''], ['P', '']]
                    continue
                try:
                    calls.append([normalize_call(token.replace('NT', 'N')), ''])
                except ValueError:
                    continue
            for i, (call, note) in enumerate(calls):
                if not note:
                    continue
                seat = (first + i) % 4
                name = tags.get(['North', 'East', 'South', 'West'][seat], SEATS[seat])
                yield {'model': model or name.lower(), 'source': path, 'event': tags.get('Event'), 'board': tags.get('Board'),
                       'seat': SEATS[seat], 'dealer': tags.get('Dealer', m.group(1)),
                       'vul': vul_of.get(tags.get('Vulnerable', 'None').lower(), 'None'), 'hand': hands[seat],
                       'auction': [c for c, _ in calls[:i]], 'call': call, 'text': note, 'extra': {'player': name}}
