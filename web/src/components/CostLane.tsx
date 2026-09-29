import type { MouseEvent } from "react";
import {
  rankSlots,
  cheapestBookable,
  slotLabel,
  hoursLabel,
  gridMinutes,
  type Lookup,
  type PersonId,
  type Axis,
} from "../types";

interface CostLaneProps {
  lookup: Lookup;
  axis: Axis;
  people: PersonId[];
  duration: number;
  selectedSlot: number | null;
  onSelect: (slot: number) => void;
}

function CostLane({
  lookup,
  axis,
  people,
  duration,
  selectedSlot,
  onSelect,
}: CostLaneProps) {
  // rankSlots/cheapestBookable already do all the cost, bookability and
  // ranking math; this only re-sorts the already-computed results back
  // into chronological order so they can be placed on the shared axis.
  const bySlot = [...rankSlots(lookup, people, duration)].sort(
    (a, b) => a.slot - b.slot
  );
  const cheapest = cheapestBookable(lookup, people, duration);
  const maxMinutes = Math.max(1, ...bySlot.map((r) => r.totalMinutes));

  // One bar per candidate start, sized to the gap between consecutive
  // slots (not the selected duration - that footprint is what the
  // candidate band across the person rows already shows). A gutter
  // carved out of that gap keeps bars visually separate instead of
  // touching edge to edge.
  const slotGapMinutes =
    lookup.slots.length > 1 ? lookup.slots[1] - lookup.slots[0] : axis.end - axis.start;
  const slotWidthPct = axis.percent(axis.start + slotGapMinutes) - axis.percent(axis.start);
  const gutterPct = slotWidthPct * 0.2;
  const barWidthPct = Math.max(slotWidthPct - gutterPct, 1);

  function handleLaneClick(event: MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const pct = ((event.clientX - rect.left) / rect.width) * 100;
    const clickedMinutes = axis.start + (pct / 100) * (axis.end - axis.start);

    let nearest: number | null = null;
    let nearestDistance = Infinity;
    for (const r of bySlot) {
      if (!r.bookable) continue;
      const distance = Math.abs(r.slot - clickedMinutes);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = r.slot;
      }
    }
    if (nearest !== null) onSelect(nearest);
  }

  return (
    <div className="teams-row teams-cost-lane-row">
      <div />
      <div
        className="teams-track teams-cost-lane"
        onClick={handleLaneClick}
        title="Click to move the candidate slot"
      >
        {gridMinutes(axis, 30).map((t) => (
          <div
            key={t}
            className="teams-gridline"
            style={{ left: `${axis.percent(t)}%` }}
          />
        ))}

        {bySlot.map((r) => {
          const left = axis.percent(r.slot) + gutterPct / 2;
          const heightPct = Math.max(2, (r.totalMinutes / maxMinutes) * 100);
          const classes = [
            "teams-cost-bar",
            r.bookable ? "" : "teams-cost-bar-unbookable",
            selectedSlot === r.slot ? "teams-cost-bar-selected" : "",
            cheapest && cheapest.slot === r.slot ? "teams-cost-bar-cheapest" : "",
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <div
              key={r.slot}
              className={classes}
              style={{ left: `${left}%`, width: `${barWidthPct}%`, height: `${heightPct}%` }}
              title={`${slotLabel(r.slot)} - ${hoursLabel(r.totalMinutes)}${
                r.bookable ? "" : " - unbookable"
              }`}
            />
          );
        })}
      </div>
      <div />
    </div>
  );
}

export default CostLane;
