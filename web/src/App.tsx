import { useEffect, useState } from "react";
import {
  loadLookup,
  cheapestBookable,
  busyCount,
  type Lookup,
  type PersonId,
} from "./types";
import DurationPills from "./components/DurationPills";
import AttendeeChips from "./components/AttendeeChips";
import SlotStrip from "./components/SlotStrip";
import ComparisonRow from "./components/ComparisonRow";
import "./App.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; lookup: Lookup };

function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  // The three pieces of selection state the whole view is driven from.
  const [selectedPeopleIds, setSelectedPeopleIds] = useState<PersonId[]>([]);
  const [duration, setDuration] = useState<number>(60);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadLookup()
      .then((lookup) => {
        if (cancelled) return;
        const allIds = lookup.people.map((p) => p.id);
        const best = cheapestBookable(lookup, allIds, 60);
        setSelectedPeopleIds(allIds);
        setSelectedSlot(best ? best.slot : (lookup.slots[0] ?? null));
        setState({ status: "ready", lookup });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // If the currently selected slot stops being bookable for the current
  // attendees/duration, reassign to the new cheapest bookable slot. Leave
  // it alone if it's still bookable (even if no longer the cheapest one -
  // that was the user's explicit choice) or if nothing is bookable.
  useEffect(() => {
    if (state.status !== "ready") return;
    if (selectedSlot === null) return;

    const { lookup } = state;
    const stillBookable =
      busyCount(lookup, selectedPeopleIds, selectedSlot, duration) === 0;
    if (stillBookable) return;

    const best = cheapestBookable(lookup, selectedPeopleIds, duration);
    if (best) setSelectedSlot(best.slot);
  }, [state, selectedPeopleIds, duration, selectedSlot]);

  if (state.status === "loading") {
    return <p className="status-message">Loading lookup data...</p>;
  }

  if (state.status === "error") {
    return (
      <p className="status-message">
        Failed to load lookup data: {state.message}
      </p>
    );
  }

  const { lookup } = state;

  function toggleAttendee(personId: PersonId) {
    setSelectedPeopleIds((current) => {
      if (current.includes(personId)) {
        if (current.length === 1) return current; // at least one must stay selected
        return current.filter((id) => id !== personId);
      }
      return [...current, personId];
    });
  }

  return (
    <div className="booking-view">
      <header className="booking-header">
        <h1>Meeting cost check</h1>
        <p className="booking-meta">
          Day {lookup.day} - scenario seed {lookup.seed}
        </p>
      </header>

      <section>
        <h2>Meeting length</h2>
        <DurationPills
          durations={lookup.durations}
          selected={duration}
          onSelect={setDuration}
        />
      </section>

      <section>
        <h2>Attendees</h2>
        <p className="section-hint">
          Focus-time cost per attendee at the selected slot, in hours. Click
          to include or exclude.
        </p>
        <AttendeeChips
          lookup={lookup}
          selectedPeopleIds={selectedPeopleIds}
          slot={selectedSlot ?? lookup.slots[0]}
          duration={duration}
          onToggle={toggleAttendee}
        />
      </section>

      <section>
        <h2>Pick a slot</h2>
        <p className="section-hint">
          Bar height is focus-time destroyed, not meeting length. Grey bars
          overlap an existing meeting and can't be booked.
        </p>
        <SlotStrip
          lookup={lookup}
          people={selectedPeopleIds}
          duration={duration}
          selectedSlot={selectedSlot}
          onSelect={setSelectedSlot}
        />
      </section>

      <section>
        {selectedSlot !== null ? (
          <ComparisonRow
            lookup={lookup}
            people={selectedPeopleIds}
            duration={duration}
            selectedSlot={selectedSlot}
          />
        ) : (
          <p>No bookable slot for this selection.</p>
        )}
      </section>
    </div>
  );
}

export default App;
