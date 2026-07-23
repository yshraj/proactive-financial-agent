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
        // Shared oblivioX studio fonts — the display grotesque and mono are
        // inherited verbatim from the parent design system so KritiFin reads
        // as part of the family even though it wears a light theme.
        display: [
          "var(--font-display)",
          "var(--font-inter)",
          "Inter",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      colors: {
        // Brand blue is anchored on the oblivioX accent glow (#3B6FFF at 500).
        // The single hue is the shared thread across obliviox / refineIQ /
        // KritiFin; 600 is a touch deeper only so white button text clears
        // WCAG AA on this light surface.
        brand: {
          50: "#EEF3FF",
          100: "#DCE6FF",
          200: "#BECDFF",
          300: "#93AEFF",
          400: "#6685FF",
          500: "#3B6FFF",
          600: "#2F5CF0",
          700: "#2348D6",
          800: "#1E3AAD",
          900: "#1B3289",
        },
        ai: {
          50: "#F5F3FF",
          100: "#EDE9FE",
          600: "#7C3AED",
          700: "#6D28D9",
        },
      },
      fontSize: {
        display: ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.02em" }],
        kpi: ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgb(16 24 40 / 0.05)",
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04)",
        "card-hover":
          "0 18px 36px -28px rgb(15 23 42 / 0.35), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
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
