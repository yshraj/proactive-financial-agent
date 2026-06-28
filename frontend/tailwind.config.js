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
        brand: {
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
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
