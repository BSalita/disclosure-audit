"""The comparison itself: what an explanation states against the hand that made the call."""

SUITS = 'SHDC'
HCP = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}
RANKS = 'AKQJT98765432'

# Worst first. A call gets the worst class that applies.
CLASSES = ['length 2+', 'length 1', 'points 2+', 'points 1']
CLASS_TEXT = {'length 2+': 'a suit two or more cards off', 'length 1': 'a suit one card off',
              'points 2+': 'points two or more outside', 'points 1': 'points one outside'}


def hand_problem(hand):
    """Why the text is not a hand of 13 cards written spades.hearts.diamonds.clubs, or None."""
    suits = hand.split('.')
    if len(suits) != 4:
        return 'not four suits'
    for holding in suits:
        if any(c not in RANKS for c in holding) or len(set(holding)) != len(holding):
            return 'not cards'
    return None if sum(map(len, suits)) == 13 else f'{sum(map(len, suits))} cards'


def hand_facts(hand):
    """(high-card points, {suit: cards}) of 'S.H.D.C'."""
    return sum(HCP.get(c, 0) for c in hand), {s: len(cards) for s, cards in zip(SUITS, hand.split('.'))}


def shape_text(hand):
    return '='.join(str(len(cards)) for cards in hand.split('.'))


def misfits(hand, stated):
    """How the hand is outside what was stated.

    stated: {'lengths': {suit: [least, most]}, 'points': [least, most], 'balanced': bool}; None = not stated.
    Returns {'wrong': [texts], 'class': one of CLASSES or None, 'cards_off': n, 'points_off': n}.
    """
    hcp, shape = hand_facts(hand)
    wrong, cards_off, points_off = [], 0, 0
    for suit, (lo, hi) in (stated.get('lengths') or {}).items():
        n = shape[suit]
        open_top = hi is None or hi >= 13
        if lo and n < lo:
            wrong.append(f'{n} {suit}, stated {lo}+' if open_top else f'{n} {suit}, stated {lo}-{hi}')
            cards_off = max(cards_off, lo - n)
        elif not open_top and n > hi:
            wrong.append(f'{n} {suit}, stated at most {hi}' if not lo else f'{n} {suit}, stated {lo}-{hi}')
            cards_off = max(cards_off, n - hi)
    lo, hi = stated.get('points') or (None, None)
    open_top = hi is None or hi >= 37
    if lo and hcp < lo:
        wrong.append(f'{hcp} HCP, stated {lo}+' if open_top else f'{hcp} HCP, stated {lo}-{hi}')
        points_off = lo - hcp
    elif not open_top and hcp > hi:
        wrong.append(f'{hcp} HCP, stated at most {hi}' if not lo else f'{hcp} HCP, stated {lo}-{hi}')
        points_off = hcp - hi
    if stated.get('balanced') and min(shape.values()) < 2:
        wrong.append('a singleton or void, stated balanced')
        cards_off = max(cards_off, 2 - min(shape.values()))
    kind = ('length 2+' if cards_off >= 2 else 'length 1' if cards_off == 1 else
            'points 2+' if points_off >= 2 else 'points 1' if points_off == 1 else None)
    return {'wrong': wrong, 'class': kind, 'cards_off': cards_off, 'points_off': points_off}


def states_something(stated):
    return bool(stated and (stated.get('lengths') or stated.get('balanced')
                            or any(v is not None for v in (stated.get('points') or ()))))
