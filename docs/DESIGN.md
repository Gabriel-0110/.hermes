---
name: Hermes Trading Desk
description: >
  Dark-mode command surface for AI-driven cryptocurrency trading.
  Military-grade operations aesthetic meets financial terminal density.
version: alpha

colors:
  primary: "#67c8ff"
  on-primary: "#05070c"
  primary-container: "#8af2c5"
  on-primary-container: "#05070c"
  secondary: "#ffc86e"
  on-secondary: "#05070c"
  tertiary: "#ff6b82"
  on-tertiary: "#ffffff"
  error: "#ff6b82"
  on-error: "#ffffff"
  surface: "#05070c"
  surface-dim: "#05070c"
  surface-bright: "#222a3d"
  surface-container-lowest: "#05070c"
  surface-container-low: "#0c1118"
  surface-container: "#0f141d"
  surface-container-high: "#141a26"
  surface-container-highest: "#1e2433"
  on-surface: "#edf3ff"
  on-surface-variant: "#8f9cb0"
  outline: "rgba(98, 155, 255, 0.32)"
  outline-variant: "rgba(98, 155, 255, 0.16)"
  background: "#05070c"
  on-background: "#edf3ff"
  inverse-surface: "#edf3ff"
  inverse-on-surface: "#05070c"
  desk-bg: "#0b0d11"
  desk-surface: "#131720"
  desk-surface-2: "#161b27"
  desk-border: "#1e2433"
  desk-amber: "#f0b429"
  desk-green: "#22c55e"
  desk-red: "#f43f5e"
  desk-blue: "#38bdf8"
  desk-purple: "#a78bfa"

typography:
  display-lg:
    fontFamily: IBM Plex Sans
    fontSize: clamp(2.5rem, 4vw, 4.7rem)
    fontWeight: "700"
    lineHeight: 0.96
    letterSpacing: -0.03em
  display-md:
    fontFamily: IBM Plex Sans
    fontSize: clamp(2.2rem, 3vw, 3.2rem)
    fontWeight: "700"
    lineHeight: 0.96
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: IBM Plex Sans
    fontSize: 2rem
    fontWeight: "700"
    lineHeight: 1.2
    letterSpacing: -0.03em
  headline-md:
    fontFamily: IBM Plex Sans
    fontSize: 0.95rem
    fontWeight: "600"
    lineHeight: 1.3
    letterSpacing: 0.08em
  body-lg:
    fontFamily: IBM Plex Sans
    fontSize: 1rem
    fontWeight: "400"
    lineHeight: 1.7
  body-md:
    fontFamily: IBM Plex Sans
    fontSize: 0.87rem
    fontWeight: "400"
    lineHeight: 1.55
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 0.78rem
    fontWeight: "600"
    lineHeight: 1.2
    letterSpacing: 0.18em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 0.72rem
    fontWeight: "600"
    lineHeight: 1.2
    letterSpacing: 0.16em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 0.65rem
    fontWeight: "600"
    lineHeight: 1.2
    letterSpacing: 0.14em
  label-xs:
    fontFamily: JetBrains Mono
    fontSize: 0.6rem
    fontWeight: "600"
    lineHeight: 1.2
    letterSpacing: 0.18em
  stat-lg:
    fontFamily: JetBrains Mono
    fontSize: clamp(2.4rem, 4vw, 3.8rem)
    fontWeight: "700"
    lineHeight: 1
    letterSpacing: -0.04em
  stat-md:
    fontFamily: JetBrains Mono
    fontSize: 2rem
    fontWeight: "700"
    lineHeight: 1.2
    letterSpacing: -0.03em
  stat-sm:
    fontFamily: JetBrains Mono
    fontSize: 1rem
    fontWeight: "600"
    lineHeight: 1.2
  code-inline:
    fontFamily: JetBrains Mono
    fontSize: 0.68rem
    fontWeight: "400"
    lineHeight: 1.2
    letterSpacing: 0.18em
  desk-display:
    fontFamily: Space Grotesk
    fontSize: 14px
    fontWeight: "700"
    lineHeight: 1.2
    letterSpacing: 0.22em
  desk-metric:
    fontFamily: Space Mono
    fontSize: 24px
    fontWeight: "700"
    lineHeight: 1.2
  desk-label:
    fontFamily: Space Mono
    fontSize: 11px
    fontWeight: "600"
    lineHeight: 1.3
    letterSpacing: 0.08em

rounded:
  sm: 4px
  DEFAULT: 12px
  md: 14px
  lg: 18px
  full: 999px

spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 18px
  xl: 22px
  2xl: 32px
  3xl: 56px
  card-padding: 20px
  module-padding: 18px
  cell-padding: 12px
  shell-max-width: 1380px
  shell-gutter: 32px

components:
  card-standard:
    backgroundColor: "linear-gradient(180deg, rgba(19, 25, 35, 0.96), rgba(11, 15, 22, 0.98))"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card-padding}"
  card-module:
    backgroundColor: "linear-gradient(180deg, rgba(20, 26, 38, 0.96), rgba(10, 14, 20, 0.98))"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: 0
  topbar:
    backgroundColor: "linear-gradient(180deg, rgba(23, 31, 43, 0.88), rgba(12, 17, 24, 0.94))"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: 18px 20px
  button-action:
    backgroundColor: "rgba(11, 16, 23, 0.92)"
    textColor: "{colors.on-surface}"
    typography: "{typography.label-sm}"
    rounded: 0
    height: 34px
    padding: 0 14px
  button-action-accent:
    backgroundColor: "rgba(103, 200, 255, 0.12)"
    textColor: "{colors.primary}"
  button-action-gain:
    backgroundColor: "rgba(138, 242, 197, 0.12)"
    textColor: "{colors.primary-container}"
  button-action-loss:
    backgroundColor: "rgba(255, 107, 130, 0.12)"
    textColor: "{colors.tertiary}"
  button-mission-cta:
    backgroundColor: "rgba(255, 107, 130, 0.1)"
    textColor: "#ffd3da"
    typography: "{typography.label-sm}"
    rounded: 0
    height: 34px
    padding: 0 14px
  nav-link:
    backgroundColor: transparent
    textColor: "{colors.on-surface-variant}"
    rounded: "{rounded.full}"
    height: 34px
    padding: 0 12px
  nav-link-hover:
    backgroundColor: "rgba(103, 200, 255, 0.06)"
    textColor: "{colors.on-surface}"
  pill-live:
    backgroundColor: "rgba(138, 242, 197, 0.08)"
    textColor: "{colors.primary-container}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    height: 24px
    padding: 0 10px
  pill-partial:
    backgroundColor: "rgba(103, 200, 255, 0.08)"
    textColor: "{colors.primary}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    height: 24px
    padding: 0 10px
  pill-scaffolded:
    backgroundColor: "rgba(255, 200, 110, 0.08)"
    textColor: "{colors.secondary}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    height: 24px
    padding: 0 10px
  pill-missing:
    backgroundColor: "rgba(255, 107, 130, 0.08)"
    textColor: "{colors.tertiary}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    height: 24px
    padding: 0 10px
  status-badge:
    backgroundColor: "rgba(138, 242, 197, 0.08)"
    textColor: "{colors.primary-container}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    height: 28px
    padding: 0 10px
  desk-summary-card:
    backgroundColor: "{colors.desk-surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.DEFAULT}"
    padding: 18px 20px
  desk-position-card:
    backgroundColor: "{colors.desk-surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: 0
  desk-service-pill:
    backgroundColor: "{colors.desk-surface-2}"
    textColor: "{colors.on-surface}"
    typography: "{typography.desk-label}"
    rounded: "{rounded.full}"
    padding: 5px 12px
  desk-link-button:
    backgroundColor: "#1f1a0d"
    textColor: "{colors.desk-amber}"
    typography: "{typography.desk-label}"
    rounded: "{rounded.full}"
    padding: 6px 14px
  desk-link-button-hover:
    backgroundColor: "#2a230f"

---

# Hermes Design System

## Identity & Personality

Hermes is a **military-ops command surface for cryptocurrency trading**. The visual
language communicates one thing: this is a live system managing real capital. Every
pixel serves an operational purpose. Nothing is decorative.

The aesthetic sits between a **fighter-jet HUD** and a **Bloomberg terminal** — dense
with data, immediately scannable, and ruthlessly functional. The dark theme isn't
a style choice; it's a fatigue reduction strategy for 24/7 monitoring. Color exists
only as signal.

## Color Philosophy

The palette is built on a near-black void (`#05070c`) that makes data glow. All
backgrounds use layered transparency over deep blue-black gradients, creating a
sense of depth without visual weight.

**Four semantic colors carry all meaning:**

- **Accent blue** (`#67c8ff`) — informational, navigation, brand identity, active
  state. This is the primary "alive" color. Used for the brand sigil, nav codes,
  eyebrow labels, accent hairlines, and active borders.
- **Green** (`#8af2c5`) — positive outcome. Profits, healthy status, successful
  operations, approved states. The kill-switch-off dot pulses slowly in green.
- **Amber** (`#ffc86e`) — caution, partial state, attention-needed. Scaffolded
  features, paper-mode badges, risk warnings.
- **Danger red** (`#ff6b82`) — negative outcome. Losses, kill switch active,
  rejected proposals, errors, critical alerts.

Colors never appear at full saturation against the background. They always manifest
through semi-transparent borders (`rgba(..., 0.24)`), subtle fills (`rgba(..., 0.08)`),
and thin accent lines. This prevents visual fatigue during extended monitoring sessions.

The **desk surface** (home dashboard) uses a slightly warmer variant palette with amber
(`#f0b429`) as the brand color instead of blue, and `Space Grotesk` as the display
font — intentionally differentiating the operator's live trading view from the
architectural mission-control screens.

## Typography

Two typeface stacks dominate:

**IBM Plex Sans** (body) — Clean humanist sans-serif for readability in long-form
content, descriptions, and navigation labels. Used at 1rem base with generous 1.7
line height for comfort.

**JetBrains Mono** (data) — Every piece of quantitative data, every status label,
every code identifier renders in monospace. This includes prices, percentages,
timestamps, kill-switch state, nav codes (`/00`, `/01`), pill labels, and metric
values. Monospace isn't decorative here — it ensures columns align, numbers scan
vertically, and operational data reads at a glance.

Labels are universally **uppercase** with wide letter-spacing (0.12em–0.22em),
rendered at tiny sizes (0.6rem–0.78rem). This convention creates a stark visual
hierarchy: if text is uppercase-mono-tiny, it's a label. If it's mixed-case-sans,
it's content.

The desk dashboard uses **Space Grotesk** for headings and **Space Mono** for
numeric data — the same structural pattern with a more contemporary feel.

## Layout Patterns

### The Shell

Content sits inside a 1380px max-width shell with 32px gutters, centered
horizontally. On mobile this collapses to screen width minus 20px.

### The Topbar

A full-width glassmorphic bar with a 1px accent hairline at top-center
(gradient from transparent → accent → transparent). Contains three zones:
brand sigil + copy, HUD matrix (4-cell grid showing Exchange/Mode/Surface/Window),
and navigation. The HUD matrix uses monospace for values and uppercase-tiny for labels.

### Cards

Cards are the primary content vessel. They have:

- 1px border in `line` color
- 18px border radius
- Subtle gradient background (light-at-top, dark-at-bottom)
- Heavy drop shadow for depth
- An 82px accent hairline at top-left (same gradient technique as topbar)

Cards never have padding variation — it's always 20px.

### The Module Pattern (Mission Control)

A structured card variant with:

- A header bar (darker gradient bg, 1px bottom border)
- Module heading + optional subtitle + action buttons
- Body area (18px padding)
- Corner brackets: 4 tiny L-shaped accent lines at each corner (7px × 1px),
  rendered via CSS `background` shorthand. These are the signature visual element
  of the command surface — they frame operational modules like targeting brackets.

### Grid Systems

Content uses CSS Grid everywhere. Key patterns:

- `repeat(auto-fit, minmax(230px, 1fr))` — responsive cards
- `1.28fr 0.92fr` — weighted split layout
- `minmax(0, 1.42fr) minmax(300px, 0.78fr)` — mission layout (primary + rail)
- `repeat(4, minmax(0, 1fr))` — HUD cells
- `repeat(5, minmax(0, 1fr))` — status strip

At tablet (900px), multi-column layouts collapse to single-column.

## Component Conventions

### Status Indicators

**Pill badges** — rounded 999px capsules with monospace uppercase text, thin
semantic border, and transparent semantic fill:

- `.pill-implemented` / `.pill-live` → green border + fill
- `.pill-partial` → blue border + fill
- `.pill-scaffolded` → amber border + fill
- `.pill-missing` → red border + fill

**Mode badges** — same capsule shape, used for trading mode (LIVE = red tint,
PAPER = amber tint).

**Kill switch indicator** — large pill with pulsing 7px dot. Green dot pulses
via `pulse-green` keyframe (2.4s ease-in-out) when inactive. Red with no pulse
when active.

### Buttons

Action buttons are monospace uppercase capsules (0.66rem, 0.14em tracking) with
tonal variants:

- `.tone-accent` → blue border + fill
- `.tone-gain` → green border + fill
- `.tone-loss` → red border + fill

Hover lifts 1px (`translateY(-1px)`). Disabled at 0.6 opacity. Transitions at
120ms ease.

### Lists

Vertical lists use a 2px left accent bar (blue at 0.36 opacity) that runs the
full height of each item. Items separated by 1px top border. First item has no
border and the accent bar starts at 0. This creates a "timeline" visual without
explicit timeline chrome.

### Bracket Labels

Inline labels wrapped in `[` `]` at 50% opacity. The text between brackets uses
semantic colors (muted, accent, gain, warn, loss). This is the system's way of
annotating inline data without adding visual weight.

### Sparklines

SVG-based, 100% width, with gradient fill beneath the line stroke. Color matches
position side (green for long, red for short, blue for grid/bot). Built from a
deterministic random walk seeded by PnL value for consistency across renders.

### Position Cards (Desk)

Each position card has:

- A 3px colored accent bar at top (gradient: green→darker-green for long,
  red→darker-red for short, blue for grid, purple for spot)
- Symbol name (18px bold), meta line (10px uppercase muted)
- Side badge (rounded 99px, semantic color, bold)
- 2×3 stat grid (9px labels, 13px mono values)
- PnL progress bar (5px tall, rounded, green or red gradient)
- Footer with "Unrealized PnL" value

### Empty States

Dashed border (1px dashed `desk-border-2`), 14px border radius, centered
content with title (16px bold), description (13px dim), and meta line (11px
mono muted).

## Motion

Motion is extremely restrained. Only three animations exist:

1. **Pulse** — Kill switch dot and live indicators breathe between opacity 1.0
   and 0.35 (2.4s) or scale between 1.0 and 0.7 (1.5s).
2. **Hover lift** — Buttons shift up 1px on hover.
3. **Transitions** — Border color, background, and opacity transitions at 120ms
   ease for interactive elements.

No page transitions. No loading spinners. No slide-ins. The system either has
data or it doesn't.

## Dark-Only

There is no light mode. The system renders in `color-scheme: dark` with a radial
gradient vignette at top center (accent blue at 0.1 opacity, fading to transparent).
This subtle glow gives the background dimensionality without introducing any
lightness that would compromise data readability during extended sessions.

## Responsive Behavior

Three breakpoints:

- **Desktop** (>1120px) — full multi-column layouts, 4-cell HUD, 3-column
  mission command grid.
- **Tablet** (≤1120px, >640px) — HUD collapses to 2-column, mission layout
  goes single-column, position grid to 2-column.
- **Mobile** (≤640px) — everything single-column, border-radius reduced to 14px,
  padding compressed, HUD/metrics strips go full-width single-column.

## Data-First Hierarchy

The visual hierarchy is designed for scan speed:

1. **Numbers** — biggest, boldest, monospace. Always the first thing the eye hits.
2. **Status indicators** — colored pills/dots/badges at the periphery of numbers.
3. **Labels** — tiny uppercase monospace, contextualizing the number above.
4. **Descriptions** — body text in muted color, only read when the operator needs
   context.
5. **Structure** — borders, cards, accent lines. Visible but never competing with
   data.
