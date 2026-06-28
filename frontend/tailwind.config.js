/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./contexts/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
      colors: {
        // Single source of truth for the primary accent. One accent only —
        // everything else is neutral gray or a status colour.
        brand: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          200: "#bae6fd",
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          800: "#075985",
          900: "#0c4a6e",
        },
      },
      fontSize: {
        // Page-level title and the big KPI numbers. Tight tracking reads as
        // more "designed" at large sizes.
        display: ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.02em" }],
        kpi: ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
      },
      boxShadow: {
        // Restrained, cool-gray shadows. Borders do most of the separation;
        // shadows only signal genuine elevation.
        xs: "0 1px 2px 0 rgb(16 24 40 / 0.05)",
        card: "0 1px 2px 0 rgb(16 24 40 / 0.04)",
        "card-hover":
          "0 2px 8px -2px rgb(16 24 40 / 0.08), 0 1px 2px 0 rgb(16 24 40 / 0.04)",
        // For true overlays only: modals, popovers, dropdowns, toasts.
        overlay:
          "0 16px 40px -12px rgb(16 24 40 / 0.18), 0 4px 10px -4px rgb(16 24 40 / 0.08)",
      },
      keyframes: {
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.98)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "fade-in": "fade-in 0.18s ease-out forwards",
        "fade-in-up": "fade-in-up 0.22s ease-out forwards",
        "scale-in": "scale-in 0.16s ease-out forwards",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
