import { useEffect, useState } from "react";
import {
  loadLookup,
  cheapestBookable,
  nearestBookableToMidpoint,
  busyCount,
  createAxis,
  type Lookup,
  type PersonId,
} from "./types";
import DurationPills from "./components/DurationPills";
import SummaryRow from "./components/SummaryRow";
import PersonRow from "./components/PersonRow";
import AxisTicks from "./components/AxisTicks";
import CostLane from "./components/CostLane";
import CalendarView from "./components/CalendarView";
import "./App.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; lookup: Lookup };

type View = "scheduler" | "calendar";
type Theme = "light" | "dark";

function getInitialTheme(): Theme {
  const prefersDark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  // The three pieces of selection state the scheduler view is driven from.
  const [selectedPeopleIds, setSelectedPeopleIds] = useState<PersonId[]>([]);
  const [duration, setDuration] = useState<number>(60);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);

  // Which top-level view is showing. Independent of the scheduler's
  // selection state above - the calendar view is retrospective (actual
  // booked meetings and their Shapley attribution) and doesn't use it.
  const [view, setView] = useState<View>("calendar");

  // Starts matching the OS preference, then is an explicit override from
  // here on - set as a data attribute on <html> so index.css's
  // :root[data-theme=...] rules (higher specificity than the plain
  // prefers-color-scheme media query) take over.
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    let cancelled = false;

    loadLookup()
      .then((lookup) => {
        if (cancelled) return;
        const allIds = lookup.people.map((p) => p.id);
        // Deliberately not the cheapest slot: starting selected and
        // suggested on the same slot would hide the comparison the summary
        // row exists to show. The midpoint slot is a neutral, deterministic
        // starting point instead.
        const midpoint = nearestBookableToMidpoint(lookup, allIds, 60);
        setSelectedPeopleIds(allIds);
        setSelectedSlot(midpoint ? midpoint.slot : (lookup.slots[0] ?? null));
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

  const axis = state.status === "ready" ? createAxis(state.lookup) : null;

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

  if (!axis) {
    return null; // unreachable: axis is only null while not "ready"
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
        <div>
          <h1>Meeting Cost Engine</h1>
          <p className="booking-meta">
            Day {lookup.day} - scenario seed {lookup.seed}
          </p>
        </div>

        <div className="control-group">
          <span className="control-label">Theme</span>
          <div className="theme-toggle" role="group" aria-label="Theme">
            <button
              type="button"
              className={theme === "light" ? "pill pill-selected" : "pill"}
              aria-pressed={theme === "light"}
              onClick={() => setTheme("light")}
            >
              Light
            </button>
            <button
              type="button"
              className={theme === "dark" ? "pill pill-selected" : "pill"}
              aria-pressed={theme === "dark"}
              onClick={() => setTheme("dark")}
            >
              Dark
            </button>
          </div>
        </div>
      </header>

      <div className="control-group">
        <span className="control-label">View</span>
        <div className="view-toggle" role="group" aria-label="View">
          <button
            type="button"
            className={view === "scheduler" ? "pill pill-selected" : "pill"}
            aria-pressed={view === "scheduler"}
            onClick={() => setView("scheduler")}
          >
            Scheduler
          </button>
          <button
            type="button"
            className={view === "calendar" ? "pill pill-selected" : "pill"}
            aria-pressed={view === "calendar"}
            onClick={() => setView("calendar")}
          >
            Calendar
          </button>
        </div>
      </div>

      {view === "scheduler" ? (
        <>
          <div className="control-group">
            <span className="control-label">Meeting length</span>
            <DurationPills
              durations={lookup.durations}
              selected={duration}
              onSelect={setDuration}
            />
          </div>

          {selectedSlot !== null ? (
            <SummaryRow
              lookup={lookup}
              people={selectedPeopleIds}
              duration={duration}
              selectedSlot={selectedSlot}
            />
          ) : (
            <p>No bookable slot for this selection.</p>
          )}

          <div className="teams-grid">
            <div className="teams-row teams-header-row">
              <span className="teams-header-label">Attendee</span>
              <span className="teams-header-label">Schedule</span>
              <span className="teams-header-label teams-header-label-right">
                Focus-time cost (min)
              </span>
            </div>

            <AxisTicks axis={axis} />

            {lookup.people.map((person) => (
              <PersonRow
                key={person.id}
                lookup={lookup}
                axis={axis}
                personId={person.id}
                displayName={person.display_name}
                selected={selectedPeopleIds.includes(person.id)}
                selectedCount={selectedPeopleIds.length}
                slot={selectedSlot ?? lookup.slots[0]}
                duration={duration}
                onToggle={toggleAttendee}
              />
            ))}

            <CostLane
              lookup={lookup}
              axis={axis}
              people={selectedPeopleIds}
              duration={duration}
              selectedSlot={selectedSlot}
              onSelect={setSelectedSlot}
            />
          </div>
        </>
      ) : (
        <CalendarView lookup={lookup} />
      )}
    </div>
  );
}

export default App;
