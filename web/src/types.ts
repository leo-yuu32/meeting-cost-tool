export type PersonId = string;

export interface Person {
  id: PersonId;
  display_name: string;
}

type Table<T> = Record<PersonId, Record<string, Record<string, T>>>;

export interface MeetingInterval {
  id: string;
  start: number; // minutes from midnight
  end: number; // minutes from midnight
}

export interface WorkingWindow {
  start: number; // minutes from midnight
  end: number; // minutes from midnight
}

export interface Lookup {
  seed: number;
  day: string;
  people: Person[];
  slots: number[];
  durations: number[];
  costs: Table<number>;
  longest_block: Table<number>;
  busy: Table<boolean>;
  meetings: Record<PersonId, MeetingInterval[]>;
  window: WorkingWindow;
  attribution: Record<PersonId, Record<string, number>>;
  day_penalty: Record<PersonId, number>;
  retention: Record<PersonId, number>;
  clear_day_yield: Record<PersonId, number>;
}

export interface RankedSlot {
  slot: number;
  totalMinutes: number;
  totalHours: number;
  bookable: boolean;
  busyCount: number;
}

export async function loadLookup(
  path = "/scenarios/lookup.json"
): Promise<Lookup> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`Could not load ${path}: ${res.status}`);
  }
  return (await res.json()) as Lookup;
}

function read<T>(
  table: Table<T>,
  person: PersonId,
  slot: number,
  duration: number
): T {
  const value = table[person]?.[String(slot)]?.[String(duration)];
  if (value === undefined) {
    throw new Error(`No entry for ${person} at ${slot} for ${duration} min`);
  }
  return value;
}

export function costFor(
  lookup: Lookup,
  person: PersonId,
  slot: number,
  duration: number
): number {
  return read(lookup.costs, person, slot, duration);
}

export function longestBlockFor(
  lookup: Lookup,
  person: PersonId,
  slot: number,
  duration: number
): number {
  return read(lookup.longest_block, person, slot, duration);
}

export function isBusy(
  lookup: Lookup,
  person: PersonId,
  slot: number,
  duration: number
): boolean {
  return read(lookup.busy, person, slot, duration);
}

export function busyCount(
  lookup: Lookup,
  people: PersonId[],
  slot: number,
  duration: number
): number {
  return people.filter((p) => isBusy(lookup, p, slot, duration)).length;
}

export function totalCost(
  lookup: Lookup,
  people: PersonId[],
  slot: number,
  duration: number
): number {
  return people.reduce((sum, p) => sum + costFor(lookup, p, slot, duration), 0);
}

export function rankSlots(
  lookup: Lookup,
  people: PersonId[],
  duration: number
): RankedSlot[] {
  return lookup.slots
    .map((slot) => {
      const totalMinutes = totalCost(lookup, people, slot, duration);
      const busy = busyCount(lookup, people, slot, duration);
      return {
        slot,
        totalMinutes,
        totalHours: totalMinutes / 60,
        bookable: busy === 0,
        busyCount: busy,
      };
    })
    .sort((a, b) => {
      if (a.bookable !== b.bookable) return a.bookable ? -1 : 1;
      return a.totalMinutes - b.totalMinutes;
    });
}

export function cheapestBookable(
  lookup: Lookup,
  people: PersonId[],
  duration: number
): RankedSlot | null {
  const first = rankSlots(lookup, people, duration)[0];
  return first && first.bookable ? first : null;
}

/**
 * The bookable slot closest to the midpoint of the working window, ties
 * broken by earliest slot. Deterministic, and independent of cost - unlike
 * cheapestBookable, this is meant as a neutral starting point so the
 * summary row can show a real difference between "selected" and
 * "suggested" from the first render, rather than starting them equal.
 */
export function nearestBookableToMidpoint(
  lookup: Lookup,
  people: PersonId[],
  duration: number
): RankedSlot | null {
  const midpoint = (lookup.window.start + lookup.window.end) / 2;
  const bookable = rankSlots(lookup, people, duration).filter((r) => r.bookable);

  return bookable.reduce<RankedSlot | null>((closest, candidate) => {
    if (!closest) return candidate;
    const closestDistance = Math.abs(closest.slot - midpoint);
    const candidateDistance = Math.abs(candidate.slot - midpoint);
    if (candidateDistance < closestDistance) return candidate;
    if (candidateDistance === closestDistance && candidate.slot < closest.slot) {
      return candidate;
    }
    return closest;
  }, null);
}

export function attendeesBelowThreshold(
  lookup: Lookup,
  people: PersonId[],
  slot: number,
  duration: number,
  thresholdMinutes = 90
): number {
  return people.filter(
    (p) => longestBlockFor(lookup, p, slot, duration) < thresholdMinutes
  ).length;
}

export function meetingsFor(lookup: Lookup, person: PersonId): MeetingInterval[] {
  return lookup.meetings[person] ?? [];
}

export function attributionFor(
  lookup: Lookup,
  person: PersonId,
  meetingId: string
): number {
  const value = lookup.attribution[person]?.[meetingId];
  if (value === undefined) {
    throw new Error(`No attribution for ${person} on meeting ${meetingId}`);
  }
  return value;
}

export function dayPenaltyFor(lookup: Lookup, person: PersonId): number {
  const value = lookup.day_penalty[person];
  if (value === undefined) {
    throw new Error(`No day penalty for ${person}`);
  }
  return value;
}

/**
 * retention = U(M) / U(empty), the share of a person's potential focus
 * time (clear_day_yield) that survived their calendar. Read directly from
 * the export rather than derived from day_penalty here, so there is one
 * source of truth (export_lookup.py computes it from the same
 * day_penalty/clear_day_yield pair).
 */
export function retentionFor(lookup: Lookup, person: PersonId): number {
  const value = lookup.retention[person];
  if (value === undefined) {
    throw new Error(`No retention for ${person}`);
  }
  return value;
}

/**
 * One shared horizontal axis for the whole day view: every element that
 * needs to line up (existing meeting blocks, the candidate band, the cost
 * lane's bars, hour ticks) maps a minutes-from-midnight value through the
 * same axis.percent(), so nothing computes its own position independently.
 *
 * Bounded on the model's working window (lookup.window), not on the data
 * drawn within it - the engine clips out-of-window time and charges
 * nothing for it, so the screen must not draw time the model didn't
 * price. Bounding on data extent instead would also let the axis shift
 * silently between scenarios.
 */
export interface Axis {
  start: number;
  end: number;
  percent: (minutesFromMidnight: number) => number;
}

export function createAxis(lookup: Lookup): Axis {
  const { start, end } = lookup.window;
  const span = end - start || 1;

  return {
    start,
    end,
    percent: (minutesFromMidnight: number) =>
      ((minutesFromMidnight - start) / span) * 100,
  };
}

/**
 * The calendar view's vertical (time-runs-downwards) axis. Same window,
 * same mapping as createAxis - this is not a second computation, just
 * createAxis under a name that reads correctly against top/height instead
 * of left/width, so the scheduler and calendar views can't disagree about
 * the day's bounds.
 */
export function createVerticalAxis(lookup: Lookup): Axis {
  return createAxis(lookup);
}

/**
 * Evenly spaced marks across an axis, `stepMinutes` apart, starting at
 * axis.start. Used to draw gridlines so they can only ever be positioned
 * through axis.percent() - never a hardcoded pixel spacing that could
 * drift out of alignment with the blocks drawn on the same axis.
 */
export function gridMinutes(axis: Axis, stepMinutes: number): number[] {
  const marks: number[] = [];
  for (let t = axis.start; t <= axis.end; t += stepMinutes) {
    marks.push(t);
  }
  return marks;
}

/**
 * Clip a meeting interval to the working window, matching how the engine
 * clips meetings before computing P (model.py's _clip_to_window). Returns
 * null if nothing of the interval falls inside the window.
 */
export function clipToWindow(
  lookup: Lookup,
  interval: { start: number; end: number }
): { start: number; end: number } | null {
  const start = Math.max(interval.start, lookup.window.start);
  const end = Math.min(interval.end, lookup.window.end);
  return end > start ? { start, end } : null;
}

export function slotLabel(minutesFromMidnight: number): string {
  const h = Math.floor(minutesFromMidnight / 60);
  const m = minutesFromMidnight % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function minutesLabel(minutes: number): string {
  return `${Math.round(minutes)} min`;
}

export function hoursLabel(minutes: number): string {
  return `${(minutes / 60).toFixed(1)} hrs`;
}

export function percentLabel(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}
