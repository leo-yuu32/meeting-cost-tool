import {
  totalCost,
  cheapestBookable,
  attendeesBelowThreshold,
  hoursLabel,
  type Lookup,
  type PersonId,
} from "../types";

interface SummaryRowProps {
  lookup: Lookup;
  people: PersonId[];
  duration: number;
  selectedSlot: number;
}

function SummaryRow({ lookup, people, duration, selectedSlot }: SummaryRowProps) {
  const cheapest = cheapestBookable(lookup, people, duration);

  if (!cheapest) {
    return (
      <div className="summary-row summary-row-empty">
        <p>No bookable slot for this selection.</p>
      </div>
    );
  }

  const selectedMinutes = totalCost(lookup, people, selectedSlot, duration);
  const below = attendeesBelowThreshold(lookup, people, selectedSlot, duration);

  return (
    <div className="summary-row">
      <div className="summary-figures">
        <div className="summary-figure">
          <span className="summary-label">Selected slot cost</span>
          <span className="summary-value">{hoursLabel(selectedMinutes)}</span>
        </div>
        <div className="summary-figure">
          <span className="summary-label">Suggested (cheapest bookable) cost</span>
          <span className="summary-value">{hoursLabel(cheapest.totalMinutes)}</span>
        </div>
      </div>
      <p className="summary-threshold">
        After this booking, {below} of {people.length} attendees have no
        remaining block over 90 minutes.
      </p>
    </div>
  );
}

export default SummaryRow;
