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
        // Brand palette (single source of truth for the primary colour).
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
        "display": ["2rem", { lineHeight: "2.25rem", letterSpacing: "-0.025em" }],
        "kpi": ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.02em" }],
      },
      boxShadow: {
        "card": "0 1px 3px 0 rgb(0 0 0 / 0.04), 0 1px 2px -1px rgb(0 0 0 / 0.04)",
        "card-hover": "0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)",
      },
      keyframes: {
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "fade-in-slide": { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "jarvis-bounce": {
          "0%, 80%, 100%": { transform: "scale(0.6)", opacity: "0.5" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
        "jarvis-glow": {
          "0%, 100%": { opacity: "0.85", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.05)" },
        },
        "jarvis-float": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-4px)" },
        },
        "jarvis-step": {
          "0%": { width: "0%", opacity: "0.8" },
          "33%": { width: "33%", opacity: "1" },
          "66%": { width: "66%", opacity: "1" },
          "100%": { width: "100%", opacity: "1" },
        },
        "ingest-shimmer": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "ingest-doc-float": {
          "0%, 100%": { transform: "translateY(0) rotate(-2deg)" },
          "50%": { transform: "translateY(-6px) rotate(1deg)" },
        },
        "ingest-ring": {
          "0%": { transform: "scale(0.8)", opacity: "0.6" },
          "50%": { transform: "scale(1.1)", opacity: "0.2" },
          "100%": { transform: "scale(0.8)", opacity: "0.6" },
        },
        "ingest-step-dot": {
          "0%, 100%": { transform: "scale(1)", opacity: "1" },
          "50%": { transform: "scale(1.3)", opacity: "0.8" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out forwards",
        "fade-in-slide": "fade-in-slide 0.3s ease-out forwards",
        "jarvis-bounce": "jarvis-bounce 1.2s ease-in-out infinite",
        "jarvis-bounce-delay-1": "jarvis-bounce 1.2s ease-in-out 0.15s infinite",
        "jarvis-bounce-delay-2": "jarvis-bounce 1.2s ease-in-out 0.3s infinite",
        "jarvis-glow": "jarvis-glow 2s ease-in-out infinite",
        "jarvis-float": "jarvis-float 2.5s ease-in-out infinite",
        "jarvis-step": "jarvis-step 2.4s ease-in-out infinite",
        "ingest-shimmer": "ingest-shimmer 2s ease-in-out infinite",
        "ingest-doc-float": "ingest-doc-float 2.2s ease-in-out infinite",
        "ingest-ring": "ingest-ring 1.5s ease-in-out infinite",
        "ingest-step-dot": "ingest-step-dot 1.2s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
