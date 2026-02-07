"use client";

import React, { useState, useRef, useEffect } from "react";

type DateSimulatorProps = {
  value: string; // YYYY-MM-DD
  onChange: (date: string) => void;
};

/** Format date as YYYY-MM-DD in local time (avoids UTC off-by-one when timezone offset pushes calendar day). */
function toISO(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatDisplay(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function DateSimulator({ value, onChange }: DateSimulatorProps) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => {
    const d = value ? new Date(value + "T12:00:00") : new Date();
    return { year: d.getFullYear(), month: d.getMonth() };
  });
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const d = value ? new Date(value + "T12:00:00") : new Date();
    setView({ year: d.getFullYear(), month: d.getMonth() });
  }, [open, value]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleEscape);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("keydown", handleEscape);
      };
    }
  }, [open]);

  const viewDate = new Date(view.year, view.month, 1);
  const firstDay = viewDate.getDay();
  const daysInMonth = new Date(view.year, view.month + 1, 0).getDate();
  const days: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) days.push(d);

  const monthLabel = viewDate.toLocaleDateString("en-GB", { month: "long", year: "numeric" });

  const handleSelect = (day: number) => {
    const iso = toISO(new Date(view.year, view.month, day));
    onChange(iso);
    setOpen(false);
  };

  const handleClear = () => {
    onChange("");
    setOpen(false);
  };

  const handleToday = () => {
    onChange(toISO(new Date()));
    setOpen(false);
  };

  const prevMonth = () => {
    if (view.month === 0) setView({ year: view.year - 1, month: 11 });
    else setView({ year: view.year, month: view.month - 1 });
  };

  const nextMonth = () => {
    if (view.month === 11) setView({ year: view.year + 1, month: 0 });
    else setView({ year: view.year, month: view.month + 1 });
  };

  const selectedDate = value ? new Date(value + "T12:00:00") : null;
  const today = toISO(new Date()); // local date as YYYY-MM-DD

  return (
    <div className="relative flex flex-col gap-1.5" ref={ref}>
      <label className="text-xs font-semibold uppercase tracking-wider text-gray-500">
        Simulate date
      </label>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 max-w-[240px] items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 text-left text-sm font-medium text-gray-900 shadow-sm transition-colors hover:border-gray-300 hover:bg-gray-50 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
        aria-label="Choose date"
        aria-expanded={open}
      >
        <span className="min-w-0 flex-1 truncate">{value ? formatDisplay(value) : "Select date"}</span>
        <svg className="h-4 w-4 flex-shrink-0 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-2 w-[300px] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg ring-1 ring-black/5"
          role="dialog"
          aria-modal="true"
          aria-label="Choose date"
        >
          <div className="border-b border-gray-100 bg-gray-50/80 px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={prevMonth}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-white hover:text-gray-900 hover:shadow-sm"
                aria-label="Previous month"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <span className="min-w-0 flex-1 text-center text-sm font-semibold text-gray-900">{monthLabel}</span>
              <button
                type="button"
                onClick={nextMonth}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-white hover:text-gray-900 hover:shadow-sm"
                aria-label="Next month"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          <div className="p-4">
            <div className="grid grid-cols-7 gap-px text-center text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <div key={d} className="py-1.5">{d}</div>
              ))}
            </div>
            <div className="mt-1 grid grid-cols-7 gap-1 text-center text-sm">
              {days.map((day, i) => {
                if (day === null) return <div key={`e-${i}`} className="aspect-square" />;
                const iso = toISO(new Date(view.year, view.month, day));
                const isSelected = selectedDate && value === iso;
                const isToday = iso === today;
                return (
                  <button
                    key={iso}
                    type="button"
                    onClick={() => handleSelect(day)}
                    className={`aspect-square min-w-[36px] rounded-lg text-[13px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-1 ${
                      isSelected
                        ? "bg-sky-600 text-white shadow-sm hover:bg-sky-700"
                        : isToday
                          ? "bg-sky-50 text-sky-700 hover:bg-sky-100"
                          : "text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-gray-100 bg-gray-50/50 px-4 py-2.5">
            <button
              type="button"
              onClick={handleClear}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-white hover:text-gray-900"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={handleToday}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-sky-600 hover:bg-sky-50 hover:text-sky-700"
            >
              Today
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
