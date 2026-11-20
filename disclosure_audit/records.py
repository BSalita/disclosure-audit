"""The record every source is turned into: one explained call a line (JSON lines).

    model    whose call and explanation it is (a robot, a program, a player); one report a model
    hand     the 13 cards of the caller, spades.hearts.diamonds.clubs: "AQ965.KJT98.2.74"
    call     P, X, XX, 1C .. 7N
    text     the explanation as given
    auction  the calls before it, from the dealer: ["1C", "P"]            (optional, for the reports)
    seat, dealer (N E S W), vul (None NS EW All), event, board, source    (optional, for the reports)
    stated   {"lengths": {"S": [5, null]}, "points": [11, 20], "balanced": false}   (optional)
             the numbers behind the text when the source has them; without it the text is read
    extra    anything else worth showing: the rule that fired, the call another program makes ...
"""
import json

SEATS = 'NESW'


def normalize_call(call):
    c = call.strip().rstrip('!').upper()
    if c in ('P', 'PASS', '--', 'AP'):
        return 'P'
    if c in ('X', 'D', 'DB', 'DBL', 'DOUBLE'):
        return 'X'
    if c in ('XX', 'R', 'RD', 'RDBL', 'REDOUBLE'):
        return 'XX'
    if len(c) >= 2 and c[0] in '1234567' and c[1] in 'CDHSN':
        return c[:2]
    raise ValueError(f'not a call: {call!r}')


def call_kind(call):
    return 'pass' if call == 'P' else 'double' if call in ('X', 'XX') else 'bid'


def hands_nesw(deal):
    """The four hands of a PBN deal string ("N:... ... ... ..."), North first."""
    first = SEATS.index(deal[0])
    hands = deal[2:].split()
    return [hands[(i - first) % 4] for i in range(4)]


def read_jsonl(paths):
    for path in [paths] if isinstance(paths, str) else paths:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def write_jsonl(path, rows):
    n = 0
    with open(path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            n += 1
    return n
