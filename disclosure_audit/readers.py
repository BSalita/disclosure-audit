"""Read what an explanation text states: cards in a suit, a point range, balanced.

Two dialects cover the texts seen so far; `auto` picks by the look of the text.

  words    "5+ hearts, 12+ hcp", "4+ S, 6-9 hcp", "Balanced hand, 15-17 HCP", "12-14"   (Brill's robots)
  symbols  "Bidable suit -- 5+!S; 6-!H; 9-11 HCP", "3+ ♣; 11-21 HCP; 12-22 total points"  (EPBot through BEN, GIB)

Only high-card points are read. "points" or "total points" may count distribution and are
left alone. A text nothing can be read from is reported as not checked, never as fitting.
"""
import re

SYMBOL = {'♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C'}
_SUIT_WORD = r'((?i:spades?|hearts?|diamonds?|clubs?)|[SHDC])\b'
_SUIT_SYM = r'(?:!\s*([SHDC])|([♠♥♦♣]))'
_HCP = r'hcp\b'


def _points(text):
    lo = hi = None
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*' + _HCP, text, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d+)\+\s*' + _HCP, text, re.I)
    if m:
        lo = int(m.group(1))
    m = re.search(r'(?<![\d-])(\d+)-\s*' + _HCP, text, re.I)
    if m:
        hi = int(m.group(1))
    m = re.search(r'hcp\s*(<=|<|>=|>)\s*(\d+)', text, re.I)
    if m:
        n = int(m.group(2))
        if m.group(1) == '<':
            hi = n - 1
        elif m.group(1) == '<=':
            hi = n
        elif m.group(1) == '>':
            lo = n + 1
        else:
            lo = n
    return lo, hi


def read_words(text):
    lengths = {}
    for m in re.finditer(r'(\d+)\s*-\s*(\d+)\s*' + _SUIT_WORD, text):
        lengths[m.group(3)[0].upper()] = [int(m.group(1)), int(m.group(2))]
    for m in re.finditer(r'(\d+)\+\s*(?:card\s+)?' + _SUIT_WORD, text):
        lengths.setdefault(m.group(2)[0].upper(), [int(m.group(1)), None])
    for m in re.finditer(r'(?<![\d-])(\d+)-\s*' + _SUIT_WORD, text):
        lengths.setdefault(m.group(2)[0].upper(), [None, int(m.group(1))])
    lo, hi = _points(text)
    if lo is None and hi is None:
        # a bare range, the whole text or one part of it: '15-17', '12-17, 4+ H', 'Balanced 22-24'
        for part in re.split(r'[,;]', text):
            m = re.fullmatch(r'\s*(?:balanced(?: hand)?\s+)?(\d+)\s*-\s*(\d+)\s*', part, re.I)
            if m and int(m.group(2)) > 7:
                lo, hi = int(m.group(1)), int(m.group(2))
    balanced = bool(re.search(r'\bbalanced\b', text, re.I)) and not re.search(r'un-?balanced|semi', text, re.I)
    return {'lengths': lengths, 'points': [lo, hi], 'balanced': balanced}


def read_symbols(text):
    lengths = {}

    def suit(m, first):
        return m.group(first) or SYMBOL[m.group(first + 1)]

    for m in re.finditer(r'(\d+)\s*-\s*(\d+)\s*' + _SUIT_SYM, text):
        lengths[suit(m, 3)] = [int(m.group(1)), int(m.group(2))]
    for m in re.finditer(r'(\d+)\s*=\s*' + _SUIT_SYM, text):
        lengths.setdefault(suit(m, 2), [int(m.group(1)), int(m.group(1))])
    for m in re.finditer(r'(\d+)\+\s*' + _SUIT_SYM, text):
        lengths.setdefault(suit(m, 2), [int(m.group(1)), None])
    for m in re.finditer(r'(?<![\d-])(\d+)-\s*' + _SUIT_SYM, text):
        lengths.setdefault(suit(m, 2), [None, int(m.group(1))])
    lo, hi = _points(text)
    return {'lengths': lengths, 'points': [lo, hi], 'balanced': False}


def looks_like_symbols(text):
    return bool(re.search(r'!\s*[SHDC]|[♠♥♦♣]', text)) or ' -- ' in text


def read(text, dialect='auto'):
    """What the text states, as checks.misfits takes it."""
    if dialect == 'symbols' or (dialect == 'auto' and looks_like_symbols(text)):
        return read_symbols(text)
    return read_words(text)


def head(text):
    """The words of a text without its numbers part: what explanations are grouped by in the reports."""
    if ' -- ' in text or text.lstrip().startswith('--'):
        return text.split('--')[0].strip() or '(numbers only)'
    return text.strip()
