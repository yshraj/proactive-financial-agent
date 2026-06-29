"use client";

import React, { useState, useRef, useEffect } from "react";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import { dateToISO, formatDate, todayISO } from "../lib/format";

type DateSimulatorProps = {
  value: string; // YYYY-MM-DD
  onChange: (date: string) => void;
};

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
    const iso = dateToISO(new Date(view.year, view.month, day));
    onChange(iso);
    setOpen(false);
  };

  const handleClear = () => {
    onChange("");
    setOpen(false);
  };

  const handleToday = () => {
    onChange(todayISO());
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
  const today = todayISO();

  return (
    <div className="relative flex items-center gap-2" ref={ref}>
      <span id="simulate-date-description" className="sr-only">
        Simulate the dashboard date
      </span>
      <button
        id="simulate-date-trigger"
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 max-w-[240px] items-center gap-2.5 rounded-lg border border-gray-200 bg-white px-3.5 text-left text-sm font-medium text-gray-900 shadow-xs transition-colors hover:border-gray-300 hover:bg-gray-50"
        aria-label="Choose date"
        aria-describedby="simulate-date-description"
        aria-expanded={open}
      >
        <Calendar className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden />
        <span className="min-w-0 flex-1 truncate">{value ? formatDate(value) : "Select date"}</span>
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-2 w-[300px] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-overlay animate-scale-in"
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
                <ChevronLeft className="h-5 w-5" aria-hidden />
              </button>
              <span className="min-w-0 flex-1 text-center text-sm font-semibold text-gray-900">{monthLabel}</span>
              <button
                type="button"
                onClick={nextMonth}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-white hover:text-gray-900 hover:shadow-sm"
                aria-label="Next month"
              >
                <ChevronRight className="h-5 w-5" aria-hidden />
              </button>
            </div>
          </div>

          <div className="p-4">
            <div className="grid grid-cols-7 gap-px text-center text-xs font-medium text-gray-400">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <div key={d} className="py-1.5">{d}</div>
              ))}
            </div>
            <div className="mt-1 grid grid-cols-7 gap-1 text-center text-sm">
              {days.map((day, i) => {
                if (day === null) return <div key={`e-${i}`} className="aspect-square" />;
                const iso = dateToISO(new Date(view.year, view.month, day));
                const isSelected = selectedDate && value === iso;
                const isToday = iso === today;
                return (
                  <button
                    key={iso}
                    type="button"
                    onClick={() => handleSelect(day)}
                    className={`aspect-square min-w-[36px] rounded-lg text-[13px] font-medium transition-colors ${
                      isSelected
                        ? "bg-brand-600 text-white shadow-xs hover:bg-brand-700"
                        : isToday
                          ? "bg-brand-50 text-brand-700 hover:bg-brand-100"
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
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-brand-600 hover:bg-brand-50 hover:text-brand-700"
            >
              Today
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
