# Meeting Cost Tool

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Status](https://img.shields.io/badge/status-phase%201%20prototype-orange?style=flat-square)](#status)

When you book a meeting, Teams tells you who is free. Free is binary: it
has no notion that 15:00 might suit the whole group while 11:00 fragments
four people's mornings.

This engine supplies the missing number. For any candidate slot it
computes how much usable focus time the meeting would cost across
everyone invited, so the cost of a meeting can be optimised to boost
productivity company-wide. So the next time your boss complains about you
scheduling a meeting at 4:30pm, you can tell them it was "mathematically
optimal".

The full mathematical write-up, derivations, the closed form for a
single-gap booking, and the model's limitations, is in
[`docs/focus-cost-model.pdf`](./docs/focus-cost-model.pdf)
([LaTeX source](./docs/focus-cost-model.tex)).

The core premise: fatigue is driven mainly by the **fragmentation** of
focus time, not by total meeting hours. A calendar with three short gaps
between meetings can leave someone with less usable focus time than one
with a single long block, even at the same total meeting load. This tool
prices that effect in minutes, at the moment an organiser is choosing a
slot, duration, or invite list, not after the fact.

It has two jobs:

1. Help the organiser pick the slot that's best for the group, not just
   convenient for the organiser.
2. Act as a social cue to reconsider whether the meeting, its length, or
   its invite list is justified at all.

This is **not** an attendee-facing tool and **not** a reporting
dashboard; the per-attendee numbers below are for the organiser at
booking time only.

## How the model works

For each person, each day, a working window $W$ (default 09:00 to 17:00)
is partitioned by that day's meetings into meeting runs and free gaps.
Two costs eat into the window:

- **Re-entry cost $c$** (default 20 min): minutes lost at the start of
  every free gap getting back into focused work. A gap shorter than $c$
  yields nothing:

$$u(g) = \max(0,\ |g| - c)$$

- **Fatigue $\Phi$**: a penalty on meeting runs that exceed a fatigue
  threshold $r^{*}$ (default 90 min), at rate $\lambda$ (default 0.4):

$$\Phi(M) = \lambda \sum_{r \in R(M)} \max(0,\ |r| - r^{*})$$

Usable focus time for a calendar $M$ subtracts both charges, plus a
lunch-protection penalty $\Lambda(M)$ (see the PDF above for its
definition), from the total gap yield:

$$U(M) = \sum_{g \in G(M)} \max(0,\ |g| - c) \; - \; \Phi(M) \; - \; \Lambda(M)$$

An empty day has a single gap spanning $W$, giving $U(\varnothing) = |W| - c$.
The **day penalty** is the shortfall against that empty day, in minutes
of focus time destroyed:

$$P(M) = U(\varnothing) - U(M)$$

Booking a candidate meeting $m$ into an existing calendar has a
**marginal cost**, how much additional focus time it destroys given
what's already booked:

$$\mathrm{Cost}_p(m \mid M) = P(M \cup \{m\}) - P(M) = U(M) - U(M \cup \{m\})$$

This is what ranks candidate slots and attendee subsets prospectively. It
is order-dependent, so for *retrospective* questions (which of a
person's existing meetings did the most damage this week?) the engine
instead attributes the day penalty across meetings by **Shapley value**:

$$\varphi_i = \sum_{S \subseteq N \setminus \{i\}} \frac{|S|!\,(n-|S|-1)!}{n!}\Big[P(S \cup \{i\}) - P(S)\Big]$$

which is efficient (attributions sum exactly to $P(N)$) and order-independent.

**Every model output is in minutes of focus time destroyed** (or hours
derived from that). There is no abstract cost index anywhere.

## Repository layout

```
engine/   Python cost model - pure, deterministic, synthetic data only
web/      React front end - a mock-up of the organiser booking view
docs/     Standalone write-up of the maths (LaTeX source + compiled PDF)
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
no OAuth, no live ingestion); its boundary is plain intervals and ids.
That's deliberate: it keeps the model testable and means the real
integration question, if it ever comes up, has a one-line answer. It's
also deterministic apart from Monte Carlo Shapley estimation, which
always takes an explicit seed.

### `web/`

A Vite + React + TypeScript app that reads the static JSON produced by
`export_lookup.py` and renders two views:

- **Scheduler**: pick attendees and a duration, see slots ranked by
  total marginal cost, and each attendee's resulting day state.
- **Calendar**: each attendee's actual day, with meetings attributed
  (Shapley) and the day's total penalty.

There is no backend server and no live calendar integration; this is a
mock-up of the booking experience for a presentation, not a product to
ship.

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

All calendar data in this repo is synthetic: there is no real calendar
ingestion, and none is planned here. This is a mock-up built to
demonstrate the model, not a product to ship.

Phase 1 covers the penalty function, marginal cost and slot ranking,
Shapley attribution, a synthetic calendar generator, and the React
mock-up above. Explicitly out of scope for this repo: live calendar
integration, a preference/personalisation survey, salary weighting,
attendee-facing views, and any claim about whether a meeting was worth
having (the model prices cost only, never benefit). Parameter values
($c$, $\lambda$, $r^{*}$) are starting points pending calibration against
self-reported rankings; see the limitations section of the PDF above for
the details.
