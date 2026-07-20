// Edge-case chat inputs. Each entry is a { label, text } pair so specs can
// iterate them as annotated steps without inventing their own strings.

export type EdgePrompt = { label: string; text: string };

export const EDGE_PROMPTS: EdgePrompt[] = [
  {
    label: "unicode and accents",
    text: "Résumé for André — savings of £12,000 held in São Paulo… ¿verdad? 中文测试",
  },
  {
    label: "emoji",
    text: "Which clients 🎂 have birthdays this month? 🎉 Any deadlines 📅 too?",
  },
  {
    label: "right-to-left text",
    text: "ما هي فجوات الحماية لدى هذا العميل؟",
  },
  {
    label: "special characters",
    text: `Quotes "double" & 'single' <tags> {braces} [brackets] \\slashes\\ %percent% $9,999`,
  },
];

/** ~9.5k characters — well beyond any realistic typed question. Pre-trimmed
 * because the composer trims input before sending. */
export const VERY_LONG_PROMPT = (
  "Summarise everything we know about pension planning. " +
  "Include contribution history, projections, and open follow-ups. ".repeat(150)
).trim();

/** ~60k characters of pasted meeting transcript. */
export const LARGE_TRANSCRIPT =
  "Adviser: Discussed pension contribution increase and protection cover.\n" +
  "Client: Agreed to review the ISA allowance before the tax year ends.\n".repeat(850);
