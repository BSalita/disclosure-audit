# disclosure-audit

Do the explanations of bridge calls fit the hands that made them?

A call at bridge comes with an explanation: "5+ spades, 11-21 HCP". This tool takes
explained calls from any source (a robot, a bidding program, a file of played boards),
compares each explanation with the hand that made the call, logs the ones that do not fit,
and writes one report for each bidder ("model"), ready to send to its author.

It finds two different defects, and helps to tell them apart:

- **a mistaken explanation**: the call is the one the system makes with the hand, and the
  text describes it wrongly;
- **a mistaken call**: the text describes the system correctly, and the bidder made the
  call with a hand it does not show.

Plain Python (3.9 or later), no other packages.

## Install

```
git clone https://github.com/BSalita/disclosure-audit
cd disclosure-audit
python -m pip install -e .
```

That gives the command `disclosure-audit`. Without installing, run it from the folder as
`python -m disclosure_audit ...`. Tests: `python -m unittest discover -s tests`.

## The three steps

```
disclosure-audit import <format> FILES... --out records.jsonl      1. a source -> records
disclosure-audit check records.jsonl ... --out DIR                 2. records -> verdicts
disclosure-audit report DIR [--config audit.json]                  3. verdicts -> one report a model
disclosure-audit calibrate DIR --model NAME --out FILE             optional: the widening that would make the texts true
```

A **record** is one explained call, one JSON object a line:

```json
{"model": "my-robot", "hand": "AQ965.KJT98.2.74", "call": "1S", "text": "5+ spades, 11-21 HCP",
 "auction": ["1C", "P"], "seat": "S", "dealer": "W", "vul": "NS", "event": "club night", "board": 7}
```

Only `model`, `hand` (spades.hearts.diamonds.clubs), `call` (`P`, `X`, `XX`, `1C` .. `7N`)
and `text` are needed; the rest makes the reports readable. Two optional fields:

- `stated`: the numbers behind the text when the source has them, for example
  `{"lengths": {"S": [5, null]}, "points": [11, 21], "balanced": false}`. Then the text is
  not parsed at all.
- `extra`: anything worth showing beside a case, such as the rule that fired or the call
  another program would make. Reports can count by these fields and show them.

Anything that can write such lines can be audited; the importers below are conveniences.

## Sources

### PBN files

Explanations are the notes of the auction section (`=1=` after a call, `[Note "1:..."]`).

```
disclosure-audit import pbn games.pbn --out records.jsonl
disclosure-audit check records.jsonl --out out
disclosure-audit report out
```

Try it on `examples/sample.pbn`: South opens 1NT, explained as 15-17, on 13 points, and
the report for `me` lists it as two points outside.

Every explained call becomes a record. The model is the player's name from the `[North]`
.. `[West]` tags (lower case), so each player gets a report; `--model NAME` puts all calls
under one name instead.

### BBO LIN files

Explanations are the `an|...|` entries after a call (`mb|1S|an|5+ spades|`).

```
disclosure-audit import lin hands.lin --out records.jsonl
```

The model is the player's name from `pn|`, or `--model NAME`. Files with three hands in
`md|` are completed with the fourth. This covers GIB and any other robot or player whose
explained auctions were saved from BBO.

### Brill Bridge Challenge robots

The saved answers of the `/bid` service, one JSON line each with `key`
(`seat|hand|dealer|vul|scoring|ctx`), `bid`, `means`, `requires` and `ruleSet`:

```
disclosure-audit import brill robot_calls.jsonl --out brill.records.jsonl
```

The model is `brill-robots`. The rule's own condition (`requires`) goes into `extra`, and
the report can show it beside every case: a text that says "4+ spades" next to a rule that
requires fewer than four is the whole argument. `extra.side` tells the entrant's partner
(North) from the opponents.

### BEN, EPBot and Morty AI

BEN's REST API sends EPBot's explanation with every call, whoever chose the call: EPBot
itself, the neural network, or the search. `adapters/ben_epbot.py` rebuilds that
explanation for every call of one seat and writes records with EPBot's own numbers in
`stated`. It needs BEN (it loads EPBot through BEN's `bba/BBA.py`) and nothing else, so
copy the one file to where BEN runs:

```
python ben_epbot.py --ben /path/to/ben --conf my.conf --model morty-ai --games games.jsonl --out morty.records.jsonl
```

Boards come from `--games` (one line a deal with `hands` [N, E, S, W], `calls`, `dealer`,
`vul`) or from `--deals` with `--replay` (see the script's help). Then, anywhere:

```
disclosure-audit check morty.records.jsonl --out out
disclosure-audit report out --config audit.json
```

The adapter also notes the call EPBot itself makes with the hand (`extra.system_call`) and
whether the call made is that one (`extra.in_system`). That splits the result in two:

| The call made | A misfit is | Report |
|---|---|---|
| is EPBot's own call (`in_system` true) | EPBot's: it describes its own call in a way that excludes the hand | the view `epbot` below |
| is not EPBot's call | the bidder's (Morty's network or search left the system) | the view `morty-outside-system` |

Views are set in the config:

```json
{"from": "the Morty AI team",
 "models": {"morty-ai": {"to": "us", "breakdown": ["in_system"], "evidence": ["system_call"]}},
 "views": {"epbot": {"of": "morty-ai", "where": {"in_system": true},
                     "title": "EPBot explanations that do not fit the hand EPBot bids them with",
                     "to": "the maintainers of BEN and EPBot"},
           "morty-outside-system": {"of": "morty-ai", "where": {"in_system": false}}}}
```

Any other engine works the same way: have it write records, with `stated` if it knows its
own numbers.

## The report config

Optional, JSON. For each model (or view): `title`, `to` (who the report is for), `intro`
(a paragraph for the top), `checked` (lines for "What was checked"), `breakdown` (extra
fields to count by), `evidence` (extra fields shown beside every case), `examples` (how
many explanations get an example table, default 10) and `notes` (a Markdown file added
near the end: what you think is going on, what you suggest). `from` says who prepared the
reports.

## Sending the findings: the issue layout

With `"style": "issue"` for a model or a view, `report` also writes `issue.md`: the findings
laid out the way a tracker expects them. The first line is the title; everything under the
rule is the body, ready to paste into a new issue. For a maintainer without a tracker the
same text is the mail, with the title as its subject. `cases.csv` is the attachment.

The body has: a summary with the headline number; what is expected and what happens; the
explanations that most often do not fit, with their rates; cases to reproduce; your notes
(what you think is going on, a suggested fix); how it was checked; and how the reader can
install this tool and run the same check, so that a correction can be verified by whoever
makes it. Settings for it:

- `expected`: one sentence for "Expected".
- `reproduce`: lines of Markdown with the commands for this source (default: the three steps).
- `labels`: readable names for `extra` fields, such as `{"requires": "The rule's own condition"}`.
- `top_evidence`: the `extra` fields shown in the table of explanations (default: `evidence`).
- `show_event`: `false` leaves the event and board out of the cases (they mean nothing to
  someone who does not have your boards).
- `issue_notes`: a notes file for the issue only, when the report's notes are for yourself.
- `tool.url` (top level): where the reader gets this tool.

## What comes out

```
DIR/checked.jsonl               every call that could be judged, with its verdict
DIR/bad.jsonl                   the log: the calls whose explanation does not fit
DIR/counts.json                 counts for each model, and the texts that could not be checked
DIR/reports/README.md           one line a model
DIR/reports/<model>/report.md   the report, to send as it is (Markdown: reads as plain text in a mail, renders in a ticket)
DIR/reports/<model>/issue.md    the same findings as an issue for a tracker, when the config asks for it
DIR/reports/<model>/cases.csv   every case of that model, for a spreadsheet
```

## Reading the results

**What "does not fit" means.** From each explanation the tool takes what can be counted:
the least and most cards in a suit, the least and most high-card points, and "balanced"
(taken as no singleton and no void). A call is listed when the hand is outside any of
those. Each listed call gets the worst class that applies:

| Class | Meaning | How to take it |
|---|---|---|
| `length 2+` | a suit two or more cards off | A different hand type than described. The serious ones: an artificial call misread, a wrong rule's text, a psychic or tactical call. |
| `length 1` | a suit one card off | Usually a boundary the text draws too tightly ("4+" where the rule takes three), or a judgment call. |
| `points 2+` | points two or more outside | Either the bidder counts something else than high-card points, or it deviated. |
| `points 1` | points one outside | Mostly upgrades and downgrades. Counted apart, and safe to leave for last. |

**The rate matters more than the count.** The table "explanations that most often do not
fit" gives, for each text, the share of the times it was given in which the hand was
outside it. A text that is wrong 70% of the time is a wrong text: correct the text. A text
that is wrong 3% of the time is a right text with exceptions: look at the calls.

**Mistaken explanation or mistaken call.** The tool cannot decide that by itself: it needs
to know what the system call was. Two ways to tell:

- the source knows the rule that fired (Brill's `requires`): when the hand satisfies the
  rule and not the text, the text is wrong;
- a second opinion on the call (EPBot's own call in `extra.system_call`): when the bidder
  made the system call and the text excludes the hand, the describing program is wrong;
  when the bidder made another call, the bidder left the system.

**Later calls repeat earlier misfits.** A program that describes a hand cumulatively (EPBot
does) attaches the same picture to every later call, passes included. One early call
outside its description can show as three listed calls on the board. Count boards, or look
at the first listed call of a board, to see where the trouble starts.

**What is not judged.** Texts without numbers ("natural", "forcing", "takeout") are counted
as not checkable, never as fitting; `counts.json` lists the most frequent ones. "Points"
that may include distribution, key-card answers, stoppers and controls are not checked
yet. So the share of bad explanations is a floor on what is wrong, not the whole of it.

**A misfit is not always an offence.** The Laws of bridge ask for the partnership's
agreement, not the hand: a deliberate deviation with a correct explanation is legal. For a
robot, though, a call it makes regularly with hands outside the description is part of its
method, and the description should say so.

## Correcting a model's explanations

When the calls are right and the text is too narrow, the text can be widened to what the
bidder's calls show in practice. `calibrate` fits that widening from the verdicts:

```
disclosure-audit check fit.records.jsonl --out fit
disclosure-audit calibrate fit --model morty-ai --out calibration.json
disclosure-audit check other.records.jsonl --out after --calibration calibration.json
```

For each kind of explanation (the kind of call and the words of the text) it finds the
smallest widening that leaves at most `--target` of the calls outside (default 3%), within
`--caps` (default: one card below a stated least, one above a stated most, three points
either way). Explanations seen fewer than `--min-calls` times share one widening. The
table depends on the explanation only, never on the hand, so a widened text says nothing
about one hand that the bidder's method does not show anyway.

Fit on one set of boards and check on another: the third line judges records as they would
read once widened, on boards the fit has not seen. What is still outside after widening are
the bidder's real deviations: look at those calls rather than at the text.

Applying the table is the job of the program that writes the explanations. BEN does it in
`src/disclosure.py` when its config has `[sampling] disclosure_calibration = <file>`, and
`adapters/ben_epbot.py --calibration <file>` exports the text exactly as BEN then sends it,
without the numbers, so that the audit reads the final text as a receiver would.

Before widening, test the other correction: make the bidder keep to the system where its
hand is far outside the text, and measure what that costs. If it costs nothing, correct
the calls; if it loses, the calls are worth keeping and the text is what to correct.

## Adding a source or a dialect

- A source is a function in `disclosure_audit/sources.py` that yields records; add it to
  the `import` choices in `cli.py`.
- Texts are read by `disclosure_audit/readers.py`: `words` ("5+ hearts, 12+ hcp") and
  `symbols` ("5+!S; 9-11 HCP", "3+ ♣; 11-21 HCP"). `check --dialect` forces one; a record
  can name its own in `dialect`. A new way of writing explanations needs a new reader
  there and a test in `tests/`.
- The comparison is `disclosure_audit/checks.py`; a new kind of statement (key cards,
  stoppers) is a new field of `stated` and a few lines in `misfits`.

## License

MIT, see `LICENSE`.
