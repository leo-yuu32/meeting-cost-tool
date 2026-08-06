export type PersonId = string;

export interface Person {
  id: PersonId;
  display_name: string;
}

type Table<T> = Record<PersonId, Record<string, Record<string, T>>>;

export interface Lookup {
  seed: number;
  day: string;
  people: Person[];
  slots: number[];
  durations: number[];
  costs: Table<number>;
  longest_block: Table<number>;
  busy: Table<boolean>;
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

export function slotLabel(minutesFromMidnight: number): string {
  const h = Math.floor(minutesFromMidnight / 60);
  const m = minutesFromMidnight % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function hoursLabel(minutes: number): string {
  return `${(minutes / 60).toFixed(1)} hrs`;
}
