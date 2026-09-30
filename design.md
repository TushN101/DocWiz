---
version: alpha
name: Claude
description: A warm parchment shadcn/ui theme — terracotta primary, cream canvas, and calm scholarly product chrome by tweakcn.
colors:
  background: "#faf8f1"
  foreground: "#3d3826"
  card: "#fcfcfc"
  primary: "#cb6441"
  primary-foreground: "#ffffff"
  secondary: "#e7e4dd"
  secondary-foreground: "#525044"
  muted: "#ede8d9"
  muted-foreground: "#85837d"
  accent: "#f4997b"
  accent-foreground: "#3c1c11"
  destructive: "#141414"
  border: "#d9d8d0"
  input: "#b4b1a3"
  ring: "#1b7ede"
  sidebar: "#f7f5ee"
  sidebar-foreground: "#3e3e38"
  sidebar-primary: "#cb6441"
  sidebar-accent: "#e7e4dd"
  chart-1: "#b2572f"
  chart-2: "#9c87f6"
  chart-3: "#ded7c2"
  chart-4: "#dad2ef"
  chart-5: "#b25630"
  dark-background: "#262626"
  dark-foreground: "#c3c1ba"
  dark-card: "#262626"
  dark-primary: "#d87757"
  dark-secondary: "#faf8f1"
  dark-muted: "#1b1b1b"
  dark-muted-foreground: "#b7b5a6"
  dark-accent: "#1a1813"
  dark-border: "#3e3e38"
  dark-sidebar: "#1f1f1f"
  dark-destructive: "#f14444"
typography:
  display:
    fontFamily: Poppins
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Poppins
    fontSize: 36px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Poppins
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
  body-lg:
    fontFamily: Lora
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.65
  body-md:
    fontFamily: Lora
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
  body-sm:
    fontFamily: Lato
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  label-md:
    fontFamily: Lato
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
  sans-ui:
    fontFamily: Lato
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  mono:
    fontFamily: ui-monospace
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  "2xl": 48px
  section: 64px
  gutter: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.md}"
    padding: 12px
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.secondary-foreground}"
    rounded: "{rounded.md}"
    padding: 12px
  button-outline:
    backgroundColor: transparent
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 12px
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 24px
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 12px
  sidebar:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.sidebar-foreground}"
---

# Claude

A premade shadcn/ui theme by [tweakcn](https://tweakcn.com). Install tokens with `npx shadcn@latest add @shadcnblocks/theme/claude`, then keep this DESIGN.md in the project root (or `.agents/`) so coding agents stay on-brand.

## Overview

Claude feels like a well-lit reading room turned product UI: a warm parchment canvas (`#faf8f1`), ink-brown body text, and a terracotta primary that reads as thoughtful heat rather than startup neon. The system is **calm, scholarly, and conversational** — built for AI assistants, knowledge tools, writing surfaces, and products that want warmth without playfulness.

Typography pairs **Poppins** for display, **Lato** for UI chrome, and **Lora** for reading text. The stack should feel literary and human, never cold terminal or generic Inter-on-white SaaS.

Emotional targets: approachable, composed, slightly academic — never clinical zinc, never loud neon AI.

## Colors

The palette is a **terracotta-on-parchment** story. Warm neutrals carry almost all of the chrome; the primary orange-brown is the brand pulse.

- **Primary (`#cb6441`):** Terracotta — primary buttons, key links, brand moments. In dark mode, lift to a softer clay (`#d87757`) so actions stay warm on charcoal stages.
- **Accent (`#f4997b`):** Light coral clay — selected chips, soft highlights, hover washes. Prefer for atmosphere over high-stakes CTAs.
- **Secondary (`#e7e4dd`):** Warm sand — secondary buttons, quiet wells, sidebar accents. Structure without shouting.
- **Foreground (`#3d3826`):** Warm umber ink — body text. Anchors the “reading room” feel; do not swap for pure black.
- **Background (`#faf8f1`):** Parchment canvas — page stage. Prefer this over pure white for full-bleed layouts.
- **Card (`#fcfcfc`):** Near-white content surfaces that float lightly above the parchment.
- **Muted (`#ede8d9`):** Soft parchment gray for quiet chrome (table headers, skeletons, secondary wells).
- **Border (`#d9d8d0`):** Warm stone borders — visible but gentle.
- **Destructive (light `#141414` / dark `#f14444`):** In light mode, high-contrast near-black for rare danger; in dark mode, a clear red. Do not tint errors with terracotta — keep brand and danger distinct.
- **Ring (`#1b7ede`):** Cool blue focus ring — deliberate contrast against the warm palette so focus states stay accessible.

Dark mode keeps the same story: charcoal stages (`#262626`), parchment-tinted foreground, terracotta that still glows. Do not flatten into generic zinc-on-black.

## Typography

**Poppins** leads marketing display. **Lato** is the UI workhorse (nav, forms, labels). **Lora** is the reading face for body copy and long-form. System monospace covers code.

- **Display / headlines:** Poppins SemiBold, tight tracking. Friendly geometric — not harsh condensed display.
- **Body / reading:** Lora Regular at 16–18px with comfortable line-height (~1.65). This is Claude’s signature reading texture.
- **UI chrome / labels:** Lato Medium or Regular. Sentence case; avoid shouty all-caps.
- **Mono:** System monospace for code blocks, tokens, and IDs — keep technical fragments quiet.

Avoid Inter, Roboto, or swapping Lora out of body copy for a “cleaner” sans — that strips the scholarly voice. Do not set dense dashboards entirely in Lora; use Lato for tables, nav, and dense controls.

## Layout

Use a **calm product rhythm**: 8px base scale, generous reading measure, clear containment.

- Prefer a readable content column for prose (~65–75ch) and a wider shell (~1200px) for app chrome.
- Group related content on near-white cards against the parchment canvas; avoid dense bordered grids.
- Marketing pages: one composition per viewport — brand as a hero-level signal, one headline, one supporting line, one CTA group.
- App shells: light sidebar + parchment content stage is on-brand. Keep navigation quiet; put terracotta accents in the content pane, not on every nav item.
- Density: medium-low. Claude is a conversation and reading theme — give forms, chats, and articles breathing room.

## Elevation & Depth

Depth is **short and soft** — Claude uses tight drop shadows (`0 1px 3px` family at low opacity), not dramatic multi-layer glow stacks.

- Prefer tonal layering: parchment background → near-white card → terracotta actions.
- Borders do most of the structural work; shadows are secondary whispers.
- Avoid neon glows, purple ambient blooms, or glassmorphism — they fight the warm clay/parchment story.
- Dark mode: elevate with slightly lifted charcoal cards and warm foreground text, not bright white borders.

## Shapes

Corner radius is **modest** — base `--radius` is `0.5rem` (8px).

- Buttons, inputs, and controls: ~8px (`rounded-md`).
- Cards and large panels: ~10–12px (`rounded-lg` / `rounded-xl`).
- Pills/avatars: full rounding only for truly circular or chip-like elements.
- Do not mix sharp 0px corners with Claude’s soft radius language on the same screen — and do not balloon everything into marketing “pill slabs.”

## Components

Built for the shadcn/ui token contract. Prefer semantic tokens (`bg-primary`, `text-muted-foreground`) over raw hex in component code.

- **Primary button:** Terracotta fill, white label. One primary CTA per view whenever possible.
- **Secondary button:** Warm sand fill with umber text — quiet alternate actions.
- **Outline / ghost:** Umber text on transparent; borders use `border`, not primary.
- **Cards:** Near-white surface, soft warm border, modest radius, airy padding (24px).
- **Inputs:** Parchment or near-white fields, stone borders, blue focus ring. Keep error states distinct from brand terracotta.
- **Sidebar:** Light parchment shell with umber labels; active item may use terracotta or a sand lift — avoid painting the whole nav in primary.
- **Charts:** Series order clay → soft violet → sand → lavender → deep clay. Keep grids quiet (`muted` / `border`).
- **Badges:** Terracotta or accent clay for highlights; muted sand for neutral status.
- **Navbars:** Treat as chrome — `background`/`card` bar, `foreground` links, one terracotta CTA. Do not fill the entire navbar with primary.

## Do's and Don'ts

**Do**

- Do keep the parchment canvas + near-white card layering — it is Claude’s signature stage.
- Do use terracotta for brand heat and warm neutrals for almost everything else.
- Do pair Poppins (display) + Lato (UI) + Lora (reading) as specified.
- Do preserve soft short shadows and ~8px control radii.
- Do support light and dark with the same clay/parchment narrative.

**Don't**

- Don’t replace the parchment background with pure `#ffffff` full-bleed (cards can be near-white; the page stage should stay warm).
- Don’t introduce purple-on-white “AI product” gradients or neon glows.
- Don’t overuse terracotta — if every control is clay-filled, nothing is emphasized.
- Don’t set dense tables, nav, or form chrome entirely in Lora.
- Don’t harden the radius to sharp Material corners or inflate everything into full pills.
- Don’t invent one-off hex colors when a shadcn semantic token already exists.
""""""""""""""""