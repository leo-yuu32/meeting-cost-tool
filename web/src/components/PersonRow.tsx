import {
  costFor,
  isBusy,
  minutesLabel,
  meetingsFor,
  clipToWindow,
  gridMinutes,
  slotLabel,
  type Lookup,
  type PersonId,
  type Axis,
} from "../types";

interface PersonRowProps {
  lookup: Lookup;
  axis: Axis;
  personId: PersonId;
  displayName: string;
  selected: boolean;
  selectedCount: number;
  slot: number;
  duration: number;
  onToggle: (personId: PersonId) => void;
}

function PersonRow({
  lookup,
  axis,
  personId,
  displayName,
  selected,
  selectedCount,
  slot,
  duration,
  onToggle,
}: PersonRowProps) {
  const busy = isBusy(lookup, personId, slot, duration);
  const meetings = meetingsFor(lookup, personId);
  const bandLeft = axis.percent(slot);
  const bandWidth = axis.percent(slot + duration) - bandLeft;
  const lastOneStanding = selected && selectedCount === 1;

  return (
    <div className="teams-row teams-person-row">
      <button
        type="button"
        className={selected ? "teams-name teams-name-selected" : "teams-name"}
        aria-pressed={selected}
        disabled={lastOneStanding}
        title={
          lastOneStanding
            ? "At least one attendee must stay selected"
            : undefined
        }
        onClick={() => onToggle(personId)}
      >
        {displayName}
      </button>

      <div className={selected ? "teams-track" : "teams-track teams-track-dim"}>
        {gridMinutes(axis, 30).map((t) => (
          <div
            key={t}
            className="teams-gridline"
            style={{ left: `${axis.percent(t)}%` }}
          />
        ))}

        {meetings.map((m) => {
          // The engine clips meetings to the working window before pricing
          // them (model.py's _clip_to_window); drawing must match, so a
          // meeting is never shown extending into time the model didn't
          // charge for.
          const clipped = clipToWindow(lookup, m);
          if (!clipped) return null;
          return (
            <div
              key={m.id}
              className="teams-meeting-block"
              style={{
                left: `${axis.percent(clipped.start)}%`,
                width: `${axis.percent(clipped.end) - axis.percent(clipped.start)}%`,
              }}
              title={`${slotLabel(clipped.start)}-${slotLabel(clipped.end)}`}
            />
          );
        })}
        <div
          className={
            busy
              ? "teams-candidate-band teams-candidate-band-busy"
              : "teams-candidate-band"
          }
          style={{ left: `${bandLeft}%`, width: `${bandWidth}%` }}
        />
      </div>

      <span className={busy ? "teams-cost teams-cost-busy" : "teams-cost"}>
        {busy ? "busy" : minutesLabel(costFor(lookup, personId, slot, duration))}
      </span>
    </div>
  );
}

export default PersonRow;
