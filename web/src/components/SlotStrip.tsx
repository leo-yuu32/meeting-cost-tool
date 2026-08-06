import {
  rankSlots,
  cheapestBookable,
  slotLabel,
  hoursLabel,
  type Lookup,
  type PersonId,
} from "../types";

interface SlotStripProps {
  lookup: Lookup;
  people: PersonId[];
  duration: number;
  selectedSlot: number | null;
  onSelect: (slot: number) => void;
}

function SlotStrip({
  lookup,
  people,
  duration,
  selectedSlot,
  onSelect,
}: SlotStripProps) {
  // rankSlots/cheapestBookable do all the cost, bookability and ranking
  // math; the only thing done here is re-sorting the already-computed
  // results back into chronological order for the x-axis.
  const ranked = rankSlots(lookup, people, duration);
  const bySlot = [...ranked].sort((a, b) => a.slot - b.slot);
  const cheapest = cheapestBookable(lookup, people, duration);
  const maxMinutes = Math.max(1, ...bySlot.map((r) => r.totalMinutes));

  return (
    <div className="slot-strip">
      <div className="slot-strip-bars">
        {bySlot.map((r) => {
          const heightPct = Math.max(2, (r.totalMinutes / maxMinutes) * 100);
          const classes = [
            "slot-bar",
            r.bookable ? "" : "slot-bar-unbookable",
            selectedSlot === r.slot ? "slot-bar-selected" : "",
            cheapest && cheapest.slot === r.slot ? "slot-bar-cheapest" : "",
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <button
              key={r.slot}
              type="button"
              className={classes}
              style={{ height: `${heightPct}%` }}
              disabled={!r.bookable}
              aria-pressed={selectedSlot === r.slot}
              title={`${slotLabel(r.slot)} - ${hoursLabel(r.totalMinutes)}${
                r.bookable ? "" : " - unbookable"
              }`}
              onClick={() => onSelect(r.slot)}
            />
          );
        })}
      </div>
      <div className="slot-strip-axis">
        {bySlot.map((r) => (
          <span key={r.slot} className="slot-strip-tick">
            {r.slot % 60 === 0 ? slotLabel(r.slot).slice(0, 2) : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

export default SlotStrip;
