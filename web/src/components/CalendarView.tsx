import {
  meetingsFor,
  attributionFor,
  dayPenaltyFor,
  clipToWindow,
  createVerticalAxis,
  gridMinutes,
  slotLabel,
  minutesLabel,
  type Lookup,
} from "../types";

interface CalendarViewProps {
  lookup: Lookup;
}

function CalendarView({ lookup }: CalendarViewProps) {
  const axis = createVerticalAxis(lookup);
  const columns = `72px repeat(${lookup.people.length}, 1fr)`;

  const hours = gridMinutes(axis, 60);
  // Structural background, not decorative: every 30 minutes, so blocks
  // read against a grid rather than floating. Same weight/colour as the
  // divider between person columns (calendar-track's border-left).
  const halfHourMarks = gridMinutes(axis, 30);

  return (
    <div className="calendar-view">
      <div className="calendar-row calendar-header" style={{ gridTemplateColumns: columns }}>
        <div />
        {lookup.people.map((person) => (
          <div key={person.id} className="calendar-name">
            {person.display_name}
          </div>
        ))}
      </div>

      <div className="calendar-row calendar-body" style={{ gridTemplateColumns: columns }}>
        <div className="calendar-hours">
          {hours.map((h) => (
            <span
              key={h}
              className="calendar-hour-tick"
              style={{ top: `${axis.percent(h)}%` }}
            >
              {slotLabel(h)}
            </span>
          ))}
        </div>

        {lookup.people.map((person) => (
          <div key={person.id} className="calendar-track">
            {halfHourMarks.map((t) => (
              <div
                key={t}
                className="calendar-gridline"
                style={{ top: `${axis.percent(t)}%` }}
              />
            ))}

            {meetingsFor(lookup, person.id).map((m) => {
              // Same principle as the scheduler view: the engine clips
              // meetings to the working window before pricing them, so
              // drawing must match (model.py's _clip_to_window).
              const clipped = clipToWindow(lookup, m);
              if (!clipped) return null;
              const top = axis.percent(clipped.start);
              const height = axis.percent(clipped.end) - top;

              return (
                <div
                  key={m.id}
                  className="calendar-block"
                  style={{ top: `${top}%`, height: `${height}%` }}
                  title={`${slotLabel(clipped.start)}-${slotLabel(clipped.end)}`}
                >
                  <span className="calendar-block-time">
                    {slotLabel(clipped.start)}-{slotLabel(clipped.end)}
                  </span>
                  <span className="calendar-block-badge">
                    {minutesLabel(attributionFor(lookup, person.id, m.id))}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="calendar-row calendar-footer" style={{ gridTemplateColumns: columns }}>
        <div className="calendar-footer-label">Day penalty</div>
        {lookup.people.map((person) => (
          <div key={person.id} className="calendar-day-penalty">
            {minutesLabel(dayPenaltyFor(lookup, person.id))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default CalendarView;
