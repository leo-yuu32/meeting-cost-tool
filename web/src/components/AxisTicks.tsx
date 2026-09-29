import { slotLabel, gridMinutes, type Axis } from "../types";

interface AxisTicksProps {
  axis: Axis;
}

function AxisTicks({ axis }: AxisTicksProps) {
  const hours = gridMinutes(axis, 60);

  return (
    <div className="teams-row teams-ticks-row">
      <div />
      <div className="teams-track teams-ticks">
        {gridMinutes(axis, 30).map((t) => (
          <div
            key={t}
            className="teams-gridline"
            style={{ left: `${axis.percent(t)}%` }}
          />
        ))}

        {hours.map((h) => (
          <span key={h} className="teams-tick" style={{ left: `${axis.percent(h)}%` }}>
            {slotLabel(h).slice(0, 2)}
          </span>
        ))}
      </div>
      <div />
    </div>
  );
}

export default AxisTicks;
