import {
  totalCost,
  cheapestBookable,
  attendeesBelowThreshold,
  hoursLabel,
  type Lookup,
  type PersonId,
} from "../types";

interface ComparisonRowProps {
  lookup: Lookup;
  people: PersonId[];
  duration: number;
  selectedSlot: number;
}

function ComparisonRow({
  lookup,
  people,
  duration,
  selectedSlot,
}: ComparisonRowProps) {
  const cheapest = cheapestBookable(lookup, people, duration);

  if (!cheapest) {
    return (
      <div className="comparison-row comparison-row-empty">
        <p>No bookable slot for this selection.</p>
      </div>
    );
  }

  const selectedMinutes = totalCost(lookup, people, selectedSlot, duration);
  const below = attendeesBelowThreshold(lookup, people, selectedSlot, duration);

  return (
    <div className="comparison-row">
      <div className="comparison-figures">
        <div className="comparison-figure">
          <span className="comparison-label">Selected slot cost</span>
          <span className="comparison-value">{hoursLabel(selectedMinutes)}</span>
        </div>
        <div className="comparison-figure">
          <span className="comparison-label">Cheapest bookable cost</span>
          <span className="comparison-value">
            {hoursLabel(cheapest.totalMinutes)}
          </span>
        </div>
      </div>
      <p className="comparison-threshold">
        After this booking, {below} of {people.length} attendees have no
        remaining block over 90 minutes.
      </p>
    </div>
  );
}

export default ComparisonRow;
