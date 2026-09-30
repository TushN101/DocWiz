# DocWiz — Design Choices (UI/UX Research & Specification)

## 1. Design Goals

DocWiz should feel like a **calm, scholarly reading room turned product UI** — the design
language popularized by Claude.ai: warm parchment canvas, ink-brown text, one terracotta brand
accent, generous whitespace, and typography that feels literary rather than "SaaS-generic".
The emotional targets are **approachable, composed, slightly academic** — never neon AI-startup,
never dense dashboard.

Priority order (per project spec): usability → visual polish → accessibility → consistency →
Claude-inspired visual language.

## 2. Visual Direction

- **Parchment stage, near-white cards**: the page background stays warm (`#faf8f1`); content
  surfaces (cards, message wells) lift slightly as near-white (`#fcfcfc`). This two-tone
  layering is the signature of the theme.
- **One warm accent**: terracotta `#cb6441` is reserved for primary actions and brand moments
  (send button, primary links, active states). If everything is clay-filled, nothing is
  emphasized.
- **Borders do the structural work**: warm stone `#d9d8d0`, 1px, visible but gentle. Shadows are
  "secondary whispers" (`0 1px 3px rgba(0,0,0,.05)`) — no glows, no glassmorphism, no gradients.
- **Modest radii**: 8px controls, 10–12px cards/panels, full rounding only for true chips/pills.

## 3. Color Palette (from `design.md`, tweakcn Claude theme)

| Token | Hex | Usage |
|---|---|---|
| background | `#faf8f1` | page stage |
| foreground | `#3d3826` | body text (warm umber ink — never pure black) |
| card | `#fcfcfc` | message wells, cards, panels |
| primary | `#cb6441` | primary buttons, send, links, active nav |
| primary-foreground | `#ffffff` | text on primary |
| secondary | `#e7e4dd` | secondary buttons, quiet wells |
| secondary-foreground | `#525044` | text on secondary |
| muted | `#ede8d9` | skeletons, table headers, hover washes |
| muted-foreground | `#85837d` | secondary text, captions, timestamps |
| accent | `#f4997b` | selected chips, soft highlights, hover wash |
| accent-foreground | `#3c1c11` | text on accent |
| destructive | `#141413` | errors (kept distinct from brand terracotta) |
| border | `#d9d8d0` | 1px structure |
| input | `#b4b1a3` | input borders (placeholder tones use muted-foreground) |
| ring | `#1b7ede` | focus ring — deliberately cool blue against warm palette |
| sidebar | `#f7f5ee` | sidebar shell |
| sidebar-foreground | `#3e3e38` | sidebar text |

Dark mode is **out of scope** for v1 (local college project) but the tokens above keep the door
open; a charcoal stage (`#262626`) with lifted clay (`#d87757`) is the documented direction.

## 4. Typography

Font stack (all bundled locally in `static/fonts/`, OFL-licensed, downloaded from the official
Google Fonts repository):

| Role | Font | Weights | Files |
|---|---|---|---|
| Display / headings / brand | **Poppins** | 500, 600 | `Poppins-Medium.ttf`, `Poppins-SemiBold.ttf` |
| Reading text (answers, documents prose) | **Lora** (variable) | 400–600 + italic | `Lora-Variable.ttf`, `Lora-Italic-Variable.ttf` |
| UI chrome (nav, labels, buttons, meta) | **Lato** | 400, 700 | `Lato-Regular.ttf`, `Lato-Bold.ttf` |
| Code / file names | system mono | — | `ui-monospace, SFMono-Regular, Menlo, Consolas` |

Rules:
- Lora at 16–17px / line-height 1.65 for answer text — this is the "reading texture".
- Lato for everything chrome: buttons, labels, sidebar, badges, timestamps. Sentence case;
  never all-caps walls.
- Poppins SemiBold, tight tracking (`-0.015em`), for the wordmark, headings, and empty-state
  titles only.
- Avoid Inter/Roboto/system-sans as the identity face — it strips the scholarly voice.
- Font sources/licensing: Google Fonts official repository (`github.com/google/fonts`), SIL Open
  Font License 1.1 — free for commercial and non-commercial use, bundling permitted.

## 5. Spacing System

8px base scale: `--space-1: 4px · --space-2: 8px · --space-3: 16px · --space-4: 24px ·
--space-5: 32px · --space-6: 48px`. Density medium-low: chat and forms breathe.

## 6. Layout Structure

```
┌───────────────────────────────────────────────────────────────────────┐
│ app shell (max 1400px, centered, full viewport height)                │
│ ┌──────────────┐  ┌────────────────────────────────────────────────┐ │
│ │ sidebar 280px│  │ main chat column (max 760px, centered)         │ │
│ │  brand       │  │  header (thin, border-bottom)                  │ │
│ │  upload card │  │  thread (scroll)                               │ │
│ │  documents   │  │   ├ empty state (Poppins headline + hints)     │ │
│ │    list      │  │   ├ user message (right-aligned well)          │ │
│ │    (✓/📄+⨯) │  │   ├ assistant message (card + sources)         │ │
│ │  footer meta │  │  composer (rounded-xl input + send button)     │ │
│ └──────────────┘  └────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

- **Sidebar** (`#f7f5ee`, right border `#d9d8d0`): quiet chrome. Brand = small wordmark in
  Poppins with a tiny terracotta mark (SVG inline, not a giant logo). Upload zone is a dashed
  warm-stone card that highlights on drag-over. Document list rows show a PDF glyph, name
  (ellipsis), chunk count in muted-foreground, and a subtle remove (⨯) button on hover.
- **Main column**: reading measure ~65–75ch (max 760px) centered in the remaining space.
- **Header**: minimal — conversation title left, document count chip right, `border-bottom`.

## 7. Chat Design

- **User message**: right-aligned card, `#e7e4dd` background, umber text, radius 12px with one
  tighter corner (bottom-right 4px), max-width 85%.
- **Assistant message**: left-aligned near-white card `#fcfcfc` with border, answer set in
  Lora 16.5px/1.65. Multi-paragraph answers keep blank-line separation.
- **Sources block** under each assistant answer: label "Sources" in Lato 12px uppercase-ish
  muted, then source rows — each a bordered pill-card with a PDF glyph, filename (mono, 13px),
  page badge (`Page 142` in terracotta-tinted chip), and a short verbatim excerpt in Lora
  italic, muted-foreground. Rows are grounded 1:1 in retrieved chunks (never invented).
- **No avatars, no bubbles-with-tails, no letter-logo circles.** Calm document-like layout.

## 8. Input Design (Composer)

- Rounded-xl (12px) card container on `#fcfcfc`, 1px `#d9d8d0` border; focus: border
  `#b4b1a3` + 3px soft blue ring `rgba(27,126,222,.25)` (accessibility — cool ring on warm
  stage).
- Auto-growing textarea (Lato 15px), 1–5 lines. `Enter` sends; `Shift+Enter` newline.
- Send button: terracotta circle-arrow (32px) bottom-right of composer; disabled (sand) when
  input empty or a request is in flight.
- Hint row under composer: "Answers are grounded in your uploaded PDFs." in muted-foreground 12px.

## 9. Buttons

| Kind | Look |
|---|---|
| Primary | terracotta fill, white Lato Medium label, radius 8px, padding 10px 16px; hover `#b2572f` |
| Secondary | warm sand `#e7e4dd`, umber text |
| Ghost/outline | transparent, umber text, border on hover |
| Icon (⨯ remove doc) | 28px hit area, muted-foreground → destructive on hover |

One primary CTA per view (the send button); upload area's "Browse files" is a secondary.

## 10. Upload UI & Document Indicators

- Drag-and-drop over the whole sidebar card **or** click to browse (hidden
  `<input type="file" multiple accept=".application/pdf">`).
- While processing: skeleton rows with muted shimmer; status line ("Extracting text… Embedding…").
- Result states: ✓ added (row appears with chunk count) · error rows in destructive tone with
  the reason (wrong type / no text / too large / corrupt).
- Document count chip in the header uses accent-wash background with accent-foreground text.

## 11. Loading / Empty / Error States

- **Thinking**: assistant card with three soft terracotta dots pulsing (opacity keyframes,
  1.2s, no movement — "no flashy animations").
- **Empty state**: Poppins headline ("What do your documents say?"), one supporting line, and
  3–4 example question chips (secondary wells) that fill the composer when clicked.
- **Errors**: inline banner inside the thread (destructive-tinted left border, calm copy,
  e.g. "Groq API key missing — add it to your .env file and restart") or a toast for upload
  issues. Never raw JSON, never traceback.
- **No relevant context**: honest assistant message: "I couldn't find anything about that in
  your uploaded documents."

## 12. Responsive Behavior

- ≥ 960px: sidebar 280px + main column.
- < 960px: sidebar becomes an off-canvas drawer toggled by a hamburger button; composer sticky
  bottom; message max-width 100%.
- Touch targets ≥ 40px on mobile.

## 13. Accessibility

- Focus ring always visible (blue `#1b7ede`, never removed).
- Color contrast: umber `#3d3826` on parchment `#faf8f1` ≈ 9.9:1; white on terracotta ≈ 4.6:1
  (AA for large/UI text); muted-foreground reserved for ≥ 12px meta text.
- Semantic landmarks: `aside`, `main`, `header`; `role="log"` + `aria-live="polite"` on the
  thread; labels on inputs; `aria-label` on icon buttons; skip link hidden.
- Reduced-motion media query disables pulsing/shimmer animations.

## 14. CSS Architecture

- Single `style.css` with **custom properties** mirroring the token table (§3) at `:root`.
- Layers: tokens → reset → base → layout → components (btn, card, chip, source-row, composer…)
  → states → responsive. BEM-ish class naming (`.msg`, `.msg--user`, `.source-row`).
- No CSS framework, no preprocessor — vanilla, commented, ~600 lines.

## 15. Research Sources

- Claude.ai public interface (layout grammar, message treatment, warm neutral palette).
- `design.md` (tweakcn Claude shadcn theme) — authoritative token source for this project.
- shadcn/ui token semantics (semantic naming: bg-primary, text-muted-foreground).
- Material/Apple HIG guidance on touch targets, focus visibility, reduced motion.
- Google Fonts official repository for Poppins/Lora/Lato files and OFL licensing.
