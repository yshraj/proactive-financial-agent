# Design system – Proactive Financial Agent

Modern SaaS analytics style (Peec AI / Linear / Stripe). **Inter** font, **Tailwind CSS** utility classes, clear hierarchy and premium cards.

## Font

- **Primary:** Inter (via `next/font/google`), applied as `font-sans`.
- **Hierarchy:** Page title large and bold; section titles medium and semibold; card labels small and muted; KPI numbers very large and bold (`text-kpi`).
- **Muted text:** `text-gray-500` for descriptions and helper text. Improved line height (`leading-relaxed`) and spacing for readability.

## Tailwind

- Layout, typography, spacing, and colors use Tailwind utility classes.
- Custom theme in `tailwind.config.js`: `fontSize.kpi`, `boxShadow.card` / `card-hover`, `fontFamily.sans` (Inter).
- No custom component CSS in `globals.css`; only `@tailwind` directives and base body styles.

## UI polish

- **Cards:** `rounded-xl`, `border border-gray-200`, `shadow-card`, `p-6` (KPI) or `px-6 py-5` (section headers). Hover: `shadow-card-hover`.
- **Spacing:** `mb-8` for intro, `mb-10` between sections, `gap-6` in KPI grid.
- **Table:** Rounded card, clear thead (uppercase, `text-gray-500`), row hover, badges for type/risk.
- **Badges:** Type (DEADLINE/OPPORTUNITY/COMPLIANCE) and Risk (HIGH/MEDIUM/LOW) with distinct background colors.

## Layout

- **AppLayout:** Sidebar + header + main content; all styled with Tailwind.
- **Dashboard:** Intro → KPI grid → Chart card → Recent alerts table.
- **Ingestion:** Intro → Dropzone → File list with progress.

Consistent use of Tailwind and Inter keeps the UI aligned with a production analytics product.
