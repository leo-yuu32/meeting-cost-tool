# Meeting Cost Tool

Organiser-facing decision support for the moment of booking a meeting: for
each candidate slot, how much focus time does it destroy across the invite
list? Built as a Markel intern project exploring hybrid working and
rethinking collaboration beyond back-to-back meetings.

The core premise: fatigue is driven mainly by the **fragmentation** of
focus time, not by total meeting hours. A calendar with three short gaps
between meetings can leave someone with less usable focus time than one
with a single long block, even at the same total meeting load. This tool
prices that effect in minutes, at the moment an organiser is choosing a
slot, duration, or invite list — not after the fact.

It has two jobs:

1. Help the organiser pick the slot that's best for the group, not just
   convenient for the organiser.
2. Act as a social cue to reconsider whether the meeting, its length, or
   its invite list is justified at all.

This is **not** an attendee-facing tool and **not** a reporting dashboard.
See [`CLAUDE.md`](./CLAUDE.md) for the full model spec, open questions,
and phase 1 scope.

## How the model works

For each person, each day, a working window `W` (default 09:00–17:00) is
partitioned by that day's meetings into meeting runs and free gaps. Two
costs eat into the window:

- **Re-entry cost `c`** (default 20 min) — minutes lost at the start of
  every free gap getting back into focused work. A gap shorter than `c`
  yields nothing.
- **Fatigue `Φ`** — a penalty on meeting runs that exceed a fatigue
  threshold `r*` (default 90 min), at rate `λ` (default 0.4).

That gives usable focus time `U(M)` for a calendar `M`, and the **day
penalty**:

```
U(M) = Σ max(0, gap - c)  -  Φ(M)  -  Λ(M)   (Λ = lunch-protection penalty, see CLAUDE.md)
P(M) = U(empty) - U(M)                        (minutes of focus time destroyed)
```

Booking a candidate meeting `m` into an existing calendar has a
**marginal cost** — how much additional focus time it destroys given
what's already booked:

```
Cost(m | M) = U(M) - U(M + m)
```

This is what ranks candidate slots and attendee subsets prospectively. It
is order-dependent, so for *retrospective* questions — which of a
person's existing meetings did the most damage this week? — the engine
instead attributes the day penalty across meetings by **Shapley value**,
which is efficient (attributions sum exactly to `P`) and order-independent.

**Every model output is in minutes of focus time destroyed** (or hours
derived from that). There is no abstract cost index anywhere.

Full formulas, the closed form for a single-gap booking, lunch
protection, and the list of open modelling questions live in
[`CLAUDE.md`](./CLAUDE.md) — that file is the spec; this README is the map.

## Repository layout

```
engine/   Python cost model - pure, deterministic, synthetic data only
web/      React front end - a mock-up of the organiser booking view
```

### `engine/`

```
src/meeting_cost/
  types.py          Person, Meeting, Interval - the plain data model
  model.py          Day penalty: gaps, fatigue, lunch protection, U(M)/P(M)
  marginal.py       Marginal cost of booking a candidate meeting
  slots.py          Slot ranking + duration/attendee sensitivities
  shapley.py        Retrospective Shapley attribution (exact + Monte Carlo)
  calibration.py    Grid search against self-reported week rankings
  synthetic.py      Synthetic calendar generator (no real calendar data)
  api.py            JSON-shaping layer - the only module that touches dicts
scripts/
  export_lookup.py     Builds web/public/scenarios/lookup.json (what the front end reads)
  export_fixtures.py   Builds standalone example fixtures under engine/fixtures/
tests/                  pytest suite, one file per module above
```

The engine is pure Python with no calendar-API dependency (no Graph SDK,
no OAuth, no live ingestion) — its boundary is plain intervals and ids.
That's deliberate: it keeps the model testable and means the real
integration question, if it ever comes up, has a one-line answer. It's
also deterministic apart from Monte Carlo Shapley estimation, which
always takes an explicit seed.

### `web/`

A Vite + React + TypeScript app that reads the static JSON produced by
`export_lookup.py` and renders two views:

- **Scheduler** — pick attendees and a duration, see slots ranked by
  total marginal cost, and each attendee's resulting day state.
- **Calendar** — each attendee's actual day, with meetings attributed
  (Shapley) and the day's total penalty.

There is no backend server and no live calendar integration — this is a
mock-up of the booking experience for a presentation, not a product to
ship (see `CLAUDE.md` section 5).

## Getting started

### Engine (Python 3.11+)

```bash
cd engine
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
pytest
```

Regenerate the scenario the front end reads (writes
`web/public/scenarios/lookup.json`):

```bash
python scripts/export_lookup.py
```

### Front end (Node.js)

```bash
cd web
npm install
npm run dev      # local dev server
npm run build    # type-check (tsc -b) + production build
npm run lint      # oxlint
```

## Status

Phase 1: penalty function, marginal cost and slot ranking, Shapley
attribution, a synthetic calendar generator, and the React mock-up above.
All calendar data in this repo is synthetic — there is no real calendar
ingestion, and none is planned here. Explicitly out of scope for this
repo: live calendar integration, the preference/personalisation survey,
salary weighting, attendee-facing views, and any claim about whether a
meeting was worth having (the model prices cost only, never benefit).
See `CLAUDE.md` section 7 for the full list of open modelling and
product questions.
