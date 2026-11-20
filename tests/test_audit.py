import json
import os
import tempfile
import unittest

from disclosure_audit import audit, checks, readers, report, sources
from disclosure_audit.records import normalize_call, write_jsonl


class Checks(unittest.TestCase):
    def test_hand(self):
        self.assertEqual(checks.hand_facts('AQ965.KJT98.2.74'), (10, {'S': 5, 'H': 5, 'D': 1, 'C': 2}))
        self.assertIsNone(checks.hand_problem('AQ965.KJT98.2.74'))
        self.assertIsNotNone(checks.hand_problem('AQ965.KJT98.2.7'))

    def test_fits(self):
        v = checks.misfits('AQ965.KJT98.2.74', {'lengths': {'S': [5, None]}, 'points': [8, 11]})
        self.assertEqual((v['wrong'], v['class']), ([], None))

    def test_classes(self):
        hand = 'AQ965.KJT98.2.74'            # 10 points, 5=5=1=2
        self.assertEqual(checks.misfits(hand, {'points': [11, 20]})['class'], 'points 1')
        self.assertEqual(checks.misfits(hand, {'points': [12, None]})['class'], 'points 2+')
        self.assertEqual(checks.misfits(hand, {'lengths': {'S': [6, None]}})['class'], 'length 1')
        self.assertEqual(checks.misfits(hand, {'lengths': {'H': [None, 3]}})['class'], 'length 2+')
        self.assertEqual(checks.misfits(hand, {'balanced': True})['class'], 'length 1')
        # the worse of the two decides
        self.assertEqual(checks.misfits(hand, {'lengths': {'S': [6, None]}, 'points': [15, 17]})['class'], 'length 1')


class Readers(unittest.TestCase):
    def test_words(self):
        self.assertEqual(readers.read('5+ hearts, 12+ hcp', 'words'),
                         {'lengths': {'H': [5, None]}, 'points': [12, None], 'balanced': False})
        self.assertEqual(readers.read('Balanced hand, 15-17 HCP', 'words')['points'], [15, 17])
        self.assertTrue(readers.read('Balanced hand, 15-17 HCP', 'words')['balanced'])
        self.assertEqual(readers.read('12-17, 4+ S', 'words'), {'lengths': {'S': [4, None]}, 'points': [12, 17], 'balanced': False})
        self.assertEqual(readers.read('Jacoby, Transfer to Hearts (5+ Hearts)', 'words')['lengths'], {'H': [5, None]})
        self.assertEqual(readers.read('hcp < 6', 'words')['points'], [None, 5])
        self.assertEqual(readers.read('Splinter, 4+ H, 0-1 D', 'words')['lengths'], {'D': [0, 1], 'H': [4, None]})

    def test_words_leave_alone(self):
        for text in ('Nat', 'T/O', '1 or 4 keycards', '5-5 in other Major and a minor', '10-16 total points'):
            self.assertFalse(checks.states_something(readers.read(text, 'words')), text)

    def test_symbols(self):
        s = readers.read('NT style -- 2-6!C; 2-6!D; 2-5!H; 2-5!S; 15-17 HCP')
        self.assertEqual(s['lengths'], {'C': [2, 6], 'D': [2, 6], 'H': [2, 5], 'S': [2, 5]})
        self.assertEqual(s['points'], [15, 17])
        s = readers.read('Nat. -- 3=!S; 10-10 HCP')
        self.assertEqual((s['lengths'], s['points']), ({'S': [3, 3]}, [10, 10]))
        s = readers.read(' -- 6-!H; 4+!S; 8- HCP')
        self.assertEqual((s['lengths'], s['points']), ({'H': [None, 6], 'S': [4, None]}, [None, 8]))
        s = readers.read('Minor suit opening -- 3+ ♣; 11-21 HCP; 12-22 total points')
        self.assertEqual((s['lengths'], s['points']), ({'C': [3, None]}, [11, 21]))

    def test_head(self):
        self.assertEqual(readers.head('Bidable suit -- 5+!S; 9-11 HCP'), 'Bidable suit')
        self.assertEqual(readers.head(' -- ; 8- HCP'), '(numbers only)')


LIN = ('pn|South,West,North,East|st||md|3SAKQ4HT93D852CKJ7,S85HKQJ4DAQT4C652,SJT973HA7DK63CA94|sv|n|'
       'mb|1S|an|5+ spades; 11-21 HCP|mb|p|mb|4S!|an|Major suit opening -- 6+ ♠; 11+ HCP|mb|p|mb|p|mb|p|pc|D3|')

PBN = """[Event "Test"]
[Board "7"]
[North "Robo"]
[South "Me"]
[Dealer "S"]
[Vulnerable "All"]
[Deal "S:AKQ4.T93.852.KJ7 85.KQJ4.AQT4.652 JT973.A7.K63.A94 62.8652.J97.QT83"]
[Auction "S"]
1NT =1= Pass 2H =2= Pass
2S AP
[Note "1:15-17 HCP, balanced"]
[Note "2:Transfer, 5+ spades"]
"""


class Sources(unittest.TestCase):
    def test_calls(self):
        self.assertEqual([normalize_call(c) for c in ('pass', '--', 'Db', 'd', 'RD', '3NT', '2d!')],
                         ['P', 'P', 'X', 'X', 'XX', '3N', '2D'])

    def test_lin(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'a.lin')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(LIN)
            rows = list(sources.lin([path]))
        self.assertEqual(len(rows), 2)
        north, south = rows
        self.assertEqual((north['seat'], north['hand'], north['call'], north['model']), ('N', 'JT973.A7.K63.A94', '1S', 'north'))
        self.assertEqual((south['seat'], south['hand'], south['auction'], south['call']), ('S', 'AKQ4.T93.852.KJ7', ['1S', 'P'], '4S'))
        self.assertEqual(north['vul'], 'NS')

    def test_pbn(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'a.pbn')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(PBN)
            rows = list(sources.pbn([path]))
        self.assertEqual([(r['seat'], r['call'], r['text'], r['model']) for r in rows],
                         [('S', '1N', '15-17 HCP, balanced', 'me'), ('N', '2H', 'Transfer, 5+ spades', 'robo')])
        self.assertEqual(rows[1]['hand'], 'JT973.A7.K63.A94')
        self.assertEqual(rows[1]['auction'], ['1N', 'P'])

    def test_brill(self):
        line = {'key': 'W|A.T8752.QJ97.T52|W|None|MP|----1C--1H--1S--', 'bid': '1N', 'means': '4+S, 7-9',
                'requires': 'hcp <= 9 and spades < 4', 'ruleSet': 'Responses'}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'c.jsonl')
            with open(path, 'w') as f:
                f.write(json.dumps(line) + '\n' + json.dumps(line) + '\n')
            rows = list(sources.brill([path]))
        self.assertEqual(len(rows), 1)                       # the same request twice counts once
        self.assertEqual(rows[0]['auction'], ['P', 'P', '1C', 'P', '1H', 'P', '1S', 'P'])
        v = audit.check_record(rows[0])
        self.assertEqual((v['class'], v['wrong']), ('length 2+', ['1 S, stated 4+']))


class EndToEnd(unittest.TestCase):
    def test_check_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            pbn = os.path.join(d, 'a.pbn')
            with open(pbn, 'w', encoding='utf-8') as f:
                f.write(PBN)
            recs = os.path.join(d, 'records.jsonl')
            write_jsonl(recs, sources.pbn([pbn], model='pair'))
            out = os.path.join(d, 'out')
            summary = audit.run([recs], out)
            self.assertEqual(summary['models']['pair']['checked'], 2)
            self.assertEqual(summary['models']['pair']['do not fit'], 1)      # South opened 1N with 13 points
            done = report.run(out, today='2026-01-01')
            self.assertEqual(done['pair'], {'checked': 2, 'do not fit': 1})
            with open(os.path.join(out, 'reports', 'pair', 'report.md'), encoding='utf-8') as f:
                self.assertIn('13 HCP, stated 15-17', f.read())
            self.assertTrue(os.path.exists(os.path.join(out, 'reports', 'pair', 'cases.csv')))


if __name__ == '__main__':
    unittest.main()
