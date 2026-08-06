import { costFor, isBusy, hoursLabel, type Lookup, type PersonId } from "../types";

interface AttendeeChipsProps {
  lookup: Lookup;
  selectedPeopleIds: PersonId[];
  slot: number;
  duration: number;
  onToggle: (personId: PersonId) => void;
}

function AttendeeChips({
  lookup,
  selectedPeopleIds,
  slot,
  duration,
  onToggle,
}: AttendeeChipsProps) {
  return (
    <div className="attendee-chips" role="group" aria-label="Attendees">
      {lookup.people.map((person) => {
        const selected = selectedPeopleIds.includes(person.id);
        const lastOneStanding = selected && selectedPeopleIds.length === 1;
        const busy = isBusy(lookup, person.id, slot, duration);
        const value = busy
          ? "busy"
          : hoursLabel(costFor(lookup, person.id, slot, duration));

        return (
          <button
            key={person.id}
            type="button"
            className={[
              "chip",
              selected ? "chip-selected" : "",
              busy ? "chip-busy" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-pressed={selected}
            disabled={lastOneStanding}
            title={
              lastOneStanding
                ? "At least one attendee must stay selected"
                : undefined
            }
            onClick={() => onToggle(person.id)}
          >
            <span className="chip-name">{person.display_name}</span>
            <span className="chip-value">{value}</span>
          </button>
        );
      })}
    </div>
  );
}

export default AttendeeChips;
