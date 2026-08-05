# CLAUDE.md

## 1. What this is

Organiser-facing decision support inside the meeting scheduling flow. When someone books a meeting, the tool shows how much focus time each candidate slot destroys across the invite list.

Two jobs:

1. Pick the slot that is best for the group rather than for the organiser.
2. Act as a social cue to reconsider whether the meeting, its length, or its invite list is justified.

The intervention point is the moment of booking, when the slot, duration, attendee list and the decision to meet at all are all still open. This is not an attendee-facing tool and not a reporting dashboard.

Context: Markel intern project. Brief is "hybrid working, rethinking collaboration beyond back to back meetings". Core premise: fatigue is driven mainly by fragmentation of focus time, not by total meeting hours.

## 2. Cost model

### Per person, per day

`W` is the working window, per person, default 09:00 to 17:00 so `|W| = 480` minutes.

`M` is that person's set of meetings that day. `M` partitions `W` into meeting intervals and free intervals (gaps).

`c` is the re-entry cost: minutes lost at the start of any free stretch getting back into work. Default 20.

Gap yield:

```
u(g) = max(0, |g| - c)
```

Fatigue, summed over maximal contiguous meeting runs `r`:

```
Phi(M) = lambda * SUM_r max(0, |r| - r*)
```

`r*` is the fatigue threshold, default 90 minutes. `lambda` is the fatigue rate, starting range 0.3 to 0.5.

Usable focus time and day penalty:

```
U(M) = SUM_{g in gaps(M)} max(0, |g| - c)  -  Phi(M)
U(empty) = |W| - c
P(M) = U(empty) - U(M)
```

**Units: minutes of focus time destroyed.** Every model output is in this unit or hours derived from it. There is no abstract index anywhere in the system.

### Marginal cost

```
Cost_p(m | M) = P(M + m) - P(M) = U(M) - U(M + m)
Cost(m)       = SUM over attendees p of Cost_p(m | M_p)
```

Marginal cost is a function of calendar state, not a property of the meeting. It is not additive: subadditive when meetings abut, since the second pays only its duration, and superadditive once a run passes `r*`.

### Single-gap closed form

A meeting of duration `D` inside a gap of length `g`, leaving fragment `a` on the left and `b` on the right, with `a + D + b = g`:

```
Cost = max(0, g-c) - max(0, a-c) - max(0, b-c)
```

| Condition | Cost |
|---|---|
| `a >= c` and `b >= c` | `D + c` |
| `a < c`, `b >= c` | `D + a` |
| `a >= c`, `b < c` | `D + b` |
| `a < c` and `b < c` | `g - c` |

Consequence: cost is flat at `D + c` across the interior of a gap and falls linearly to `D` at the edges. Interior slots are genuinely equivalent, and slot ranking should surface that rather than implying a false distinction.

### Retrospective attribution

Marginal cost depends on booking order, so it cannot be used to rank meetings against each other. For retrospective analysis, attribute the day penalty across the meetings in a person-day by Shapley value:

```
phi_i = SUM_{S subset of N\{i}} [ |S|!(n-|S|-1)!/n! ] * [ P(S + i) - P(S) ]
```

This gives efficiency (attributions sum to `P(N)`), symmetry, and the null player property. Exact computation is `n * 2^(n-1)` evaluations of `P`, which is fine up to roughly `n = 12`. Above that, Monte Carlo over sampled permutations with a reported standard error.

**Rule: marginal for prospective slot ranking, Shapley for retrospective ranking of meetings and recurring series.**

### Calibration

`c`, `lambda` and `r*` are starting values, not measurements. Calibrate by grid search maximising Spearman rank correlation between `P` and self-reported rankings of past weeks, from around twenty people ranking their own weeks worst to best. If the correlation is weak, report that rather than tuning until it fits.

## 3. Personalisation inputs

Design principle: calendar-derived base, preferences as a bounded adjustment layer. The base model must run on defaults for everyone so non-responders are still scored. Three questions maximum.

1. Meetings batched into fewer days, or spread out?
2. Preferred gap between meetings?
3. Which day should be prioritised for meetings?

**None of these has a defined mapping into the model as specified.** Specifically:

- Q1: the model always rewards batching, because fewer gaps means paying `c` fewer times. A stated preference for spreading meetings out is not representable without a new term.
- Q2: there is no minimum-buffer term.
- Q3: `P` is per-day and day-agnostic, so there is no cross-day weighting to attach a day preference to.

Personalisable today without new terms: `W`, and in principle per-person `c`, `lambda`, `r*`. Any preference adjustment is intended to be bounded, on the order of plus or minus 25% on a coefficient, so preferences tilt the result without dominating it.

Do not invent mappings. All of this sits under open questions until decided.

## 4. Engine inputs and outputs

Data shapes, not implementation.

**Inputs**

- Person: id, working window start and end per weekday, optional per-person `c`, `lambda`, `r*`.
- Meeting: id, start, end, attendee ids, optional recurring series id.
- Slot query: duration, attendee ids, candidate window, grid granularity (default 15 minutes).

**Outputs**

- Day penalty: person id, date, `P` in minutes, plus the derived gap structure (gaps and their yields) for explainability.
- Slot ranking: for each candidate start time, total cost in minutes, per-attendee costs, and the resulting day state per attendee (longest remaining usable block). Ranked ascending by total cost.
- Sensitivities: cost recomputed across a set of durations, and per-attendee marginals so attendees can be ranked by the cost of including them.
- Attribution: Shapley value per meeting for a given person-day, and roll-up by recurring series.

Post-booking state must always be returned alongside marginal cost. Marginal cost alone incentivises booking early to claim cheap slots; absolute state is not gameable by ordering.

Per-attendee costs are for the organiser at booking time only. Never expose them to an attendee-facing surface, and keep analytics aggregate.

## 5. Architecture constraints

- Python engine, React front end.
- All data is synthetic. There is no real calendar ingestion in this repo, and none is planned. This codebase exists to demonstrate the model in a presentation, not to ship.
- The engine must not import anything calendar-API specific: no Graph SDK, no Outlook or Google Calendar types, no auth. Its boundary is plain intervals and ids. This is for testability, and so the integration question has a one-line answer if it comes up, not because ingestion is coming.
- The engine is pure and deterministic apart from Monte Carlo Shapley, which must take a seed.
- The front end is a mock-up of the scheduling experience, not an integration.

## 6. Phase 1 scope

**In scope**

- Penalty function with fixed default parameters.
- Marginal cost, slot ranking on a 15-minute grid, duration and attendee sensitivities.
- Shapley attribution and recurring series ranking.
- Synthetic calendar generator.
- React mock-up of the organiser booking view.
- Calibration harness for the week-ranking exercise.
- Quantified prize: focus-hours recoverable through better slot selection.

**Explicitly not in phase 1**

- Outlook add-in or any live calendar integration.
- Preference survey and personalisation layer.
- Salary weighting and any monetary output.
- Attendee-facing views of any kind.
- Post-meeting value or effectiveness capture.
- Meeting classification by type or importance.
- Any claim about whether a meeting was worth having. The model prices cost only, never benefit.

## 7. Open questions

**Model**

- `kappa`, the out-of-hours multiplier for meetings outside `W`. Undefined.
- Whether a lunch interval is protected. Undefined.
- What counts as a contiguous run for the fatigue term: whether a short gap breaks a run, and whether that threshold is `c` or a separate parameter.
- How day penalties aggregate into a week-level figure. Undefined.
- Non-working days, leave, and part-time patterns.
- Meetings that fall partially outside `W`.
- Overlapping and double-booked meetings.
- Declined, tentative, and optional attendance.
- All-day events and self-booked focus blocks: meetings, protected time, or excluded.
- Final values of `c`, `lambda`, `r*`, pending calibration.

**Personalisation**

- Whether the model should represent a preference for spread-out meetings at all, and what term would express it.
- The mapping from each survey answer to a parameter adjustment.
- Whether preferences act as per-person parameters or as a post-hoc multiplier.

**Product and business**

- Whether phase 1 delivers a prototype or an analysis. Sponsor decision.
- Outlook add-in feasibility at Markel.
- Overlap with Viva Insights or Copilot Analytics, if licensed.
- Salary band granularity, and whether the monetary layer is wanted at all.
- Pilot team and the calendar data access route.
- The brief is hybrid working, but the model has no location dimension. Whether in-office versus remote days should affect `W`, `c`, or anything else is undecided.
