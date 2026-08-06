interface DurationPillsProps {
  durations: number[];
  selected: number;
  onSelect: (duration: number) => void;
}

function DurationPills({ durations, selected, onSelect }: DurationPillsProps) {
  return (
    <div className="duration-pills" role="group" aria-label="Meeting length">
      {durations.map((d) => (
        <button
          key={d}
          type="button"
          className={d === selected ? "pill pill-selected" : "pill"}
          aria-pressed={d === selected}
          onClick={() => onSelect(d)}
        >
          {d} min
        </button>
      ))}
    </div>
  );
}

export default DurationPills;
