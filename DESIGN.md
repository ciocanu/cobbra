---
name: Cobbra
description: Cycling analytics for athletes who measure everything. No social layer, no noise.
colors:
  # Brand layer (landing page) — exact hex
  venom: "#39FF14"
  void: "#050505"
  brand-bg: "#080808"
  brand-surface-0: "#0C0C0C"
  brand-surface-1: "#111111"
  brand-surface-2: "#181818"
  brand-surface-3: "#202020"
  brand-border: "#1E1E1E"
  brand-border-bright: "#2A2A2A"
  brand-text: "#EFEFEF"
  brand-text-dim: "#7A7A7A"
  brand-text-ghost: "#3A3A3A"
  # App layer — OKLCH canonical (note: Stitch linter will flag these as non-hex; OKLCH is the canonical format for this layer)
  app-bg: "oklch(8% 0.005 142)"
  app-surface: "oklch(11% 0.007 142)"
  app-card: "oklch(14% 0.009 142)"
  app-hover: "oklch(17% 0.011 142)"
  app-border: "oklch(21% 0.014 142)"
  app-border-bright: "oklch(27% 0.018 142)"
  app-text: "#F0F0FF"
  app-text-dim: "#8888AA"
  app-text-muted: "#3A3A5A"
  # Data visualization — chart contexts only
  data-speed: "#4DA6FF"
  data-heart: "#FF4D6D"
  data-cadence: "#FFD93D"
  data-elevation: "#6DFFB8"
  data-power: "#B57BEE"
typography:
  display:
    fontFamily: "'Barlow Condensed', sans-serif"
    fontSize: "clamp(80px, 11vw, 152px)"
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "'Barlow Condensed', sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.5px"
  title:
    fontFamily: "'Barlow Condensed', sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.3px"
  body:
    fontFamily: "'Barlow', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontFamily: "'JetBrains Mono', 'Courier New', monospace"
    fontSize: "10px"
    fontWeight: 400
    letterSpacing: "0.12em"
rounded:
  none: "0px"
  precision: "2px"
  sm: "6px"
  md: "10px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
  3xl: "80px"
components:
  button-primary:
    backgroundColor: "{colors.venom}"
    textColor: "{colors.void}"
    rounded: "{rounded.precision}"
    padding: "13px 26px"
  button-primary-hover:
    backgroundColor: "{colors.venom}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.brand-text-dim}"
    rounded: "{rounded.precision}"
    padding: "13px 26px"
  button-app-primary:
    backgroundColor: "{colors.venom}"
    textColor: "{colors.void}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-app-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.app-text-dim}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  card:
    backgroundColor: "{colors.app-card}"
    rounded: "{rounded.md}"
    padding: "20px"
  nav-item-active:
    textColor: "{colors.venom}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
---

# Design System: Cobbra

## 1. Overview

**Creative North Star: "The Black Jersey"**

The leading rider in a peloton wears nothing loud. Their record proves authority; their kit is unremarkable. Cobbra operates on the same principle: the data is the achievement, the interface is the jersey. Nothing announces itself. Every element exists because it carries information. What does not carry information does not exist.

This is a dual-register system built on one shared commitment. The brand register (landing page) uses radical void black and one venom green moment — compressed headline typography at race-board scale, every pixel structural. The product register (analytics app) runs slightly warmer OKLCH-tinted darks with purple-shifted text hierarchies, optimized for scanning dense numbers after a hard ride, at a desk, in ambient light. Both registers share one constraint: a single venom green accent, used at no more than 10% of any screen's surface. Its scarcity is its weight.

The system explicitly refuses the vocabulary of consumer fitness apps (Strava's activity feed, Garmin's metric-overflow clutter) and the visual clichés of "dark tool" software (neon-blue gradients, purple glassmorphism, card grids with identical icon-heading-text rows). If a new element can be identified as either of those by category reflex alone, it does not belong here.

**Key Characteristics:**
- Void-native dark theme — athlete reviewing data at home after a ride, room at ambient, not a backlit office
- Single accent color (venom green `#39FF14`) used once per screen, never decorative
- Two-font structural system: Barlow Condensed for identity and hierarchy, Barlow for reading copy
- Monospace readout layer (JetBrains Mono) for all numeric and metric contexts — timing board precision
- Tonal elevation only — depth through four OKLCH surface steps, no box-shadows at rest
- GPU-composited transitions only: opacity and transform, nothing layout-affecting
- `@media (prefers-reduced-motion: reduce)` zeros all transitions and animations system-wide

## 2. Colors: The Void and the Signal

One intentional color. Everything else is controlled absence.

### Primary

- **Venom Green** (`#39FF14` / `oklch(87% 0.29 142)`): The only non-neutral color in the system's UI chrome. Used on: CTA buttons (primary action surface), the active navigation item, PR callout values, the "No mercy." headline signature on the landing page, and accent marks in AI-generated training plan headings. Never applied as ambient decoration — always the one signal that matters on the screen.

### Neutral — Brand Layer (landing page)

- **Void** (`#050505`): Reserved for the absolute deepest surface when pure darkness is required.
- **Near-Void** (`#080808`): Default page background on the landing page.
- **Surface 1** (`#111111`): Secondary surface in brand register.
- **Surface 3** (`#202020`): Elevated surface, hover states in brand register.
- **Border** (`#1E1E1E`): Structural dividers and section edges.
- **Border Highlight** (`#2A2A2A`): Ghost button outlines, focus containers, elevated edges.
- **Text** (`#EFEFEF`): Primary reading text in the brand register.
- **Text Dim** (`#7A7A7A`): Supporting copy, secondary descriptions.
- **Text Ghost** (`#3A3A3A`): Labels, metadata, timestamps — barely visible, present only to answer questions.

### Neutral — App Layer (analytics product)

The app layer uses OKLCH at 142° hue (green-tinted) for all surfaces, which subtly distinguishes the product from the pure-hex brand layer while maintaining visual continuity. Text colors are purple-tinted, which separates hierarchy clearly at small sizes without adding additional accent colors.

- **App Background** (`oklch(8% 0.005 142)`): The base dark surface — seated, post-ride data review.
- **App Secondary** (`oklch(11% 0.007 142)`): Sidebar, table header backgrounds.
- **App Card** (`oklch(14% 0.009 142)`): Primary content surfaces — cards, chart panels, login box.
- **App Hover** (`oklch(17% 0.011 142)`): Row and item hover surfaces; pressed/active backgrounds.
- **App Border** (`oklch(21% 0.014 142)`): Structural cell dividers, card edges at rest.
- **App Border Bright** (`oklch(27% 0.018 142)`): Elevated borders — ghost button outlines, filter input edges, sidebar highlight.
- **App Text** (`#F0F0FF`): Primary text — slightly blue-shifted from brand text for extended desktop reading.
- **App Text Dim** (`#8888AA`): Secondary text — distinctly purple-tinted; readable at body size, recedes at label size.
- **App Text Muted** (`#3A3A5A`): Table column headers, card labels, metadata — minimum readable.

### Data Visualization

Five semantic colors used strictly within chart and zone-bar contexts. They are never repurposed as UI chrome accents or status indicators. Within charts, they identify data streams; outside charts, they do not appear.

- **Speed / Power** (`#4DA6FF`): Speed lines, power overlay, GPX badge tint.
- **Heart Rate** (`#FF4D6D`): HR chart lines, heart rate readouts.
- **Cadence** (`#FFD93D`): Cadence channel.
- **Elevation** (`#6DFFB8`): Elevation profile.
- **Power Curve** (`#B57BEE`): Normalized power, FTP curve display.

### Named Rules

**The One Voice Rule.** Venom green (`#39FF14`) appears on ≤10% of any given screen surface. Its rarity is what gives it weight. Adding it to a second element on the same screen splits the signal — at that point nothing is the signal. One accent, total commitment.

**The No Glow Rule.** Venom glow tokens (`--cb-venom-glow`, `--cb-venom-text`) exist in the system but are reserved for maximum-emphasis moments: a PR notification, a first-ever personal best, a goal achieved. They are not applied as ambient decoration on static elements. One screen, one glow event maximum.

**The Chart Boundary Rule.** The data visualization palette (speed, heart, cadence, elevation, power) is chart-only. It never leaks into navigation, button states, alert borders, or section headings. If it appears outside a chart, it is a mistake.

## 3. Typography

**Display Font:** Barlow Condensed (with sans-serif fallback)
**Body Font:** Barlow (with sans-serif fallback)
**Label/Mono Font:** JetBrains Mono (with 'Courier New', monospace fallback)

**Character:** Barlow Condensed at 800 weight creates a race timing board — compressed, vertical, relentless. Each letter does maximum work in minimum horizontal space. Paired with Barlow for body text, the system reads as a purpose-built tool, not a lifestyle brand. JetBrains Mono anchors all numeric readouts with tabular figures and consistent widths: zero ambiguity in the numbers you trained for.

### Hierarchy

- **Display** (800, clamp(80px–152px), line-height 0.9, -0.015em tracking): Landing hero headline only. Set to negative line-height — multi-line headlines compress like a leaderboard column. Avoid on any screen inside the app; the scale belongs to the brand register.
- **Headline** (700, 28px, 1.2 line-height, 0.5px tracking): Page titles within the product app. Condensed weight establishes section authority without taking height.
- **Title** (700, 16px, 1.3, 0.3px tracking): Component headings, chart section titles, sidebar logo lockup. Used when a label needs more than label weight but less than page-title authority.
- **Body** (400, 15px base / 17px landing, 1.75 line-height): Reading copy. Cap paragraph text at 65–75ch. Landing body max-width 440px. AI coaching output max-width unrestricted (whitespace preserved).
- **Label** (JetBrains Mono, 9–11px, 0.08–0.14em tracking, uppercase): Used for every metric label, zone tag, badge text, table header, and section eyebrow above data. Never Barlow at label size — the monospace distinction is structural. Tabular-nums feature enabled (`font-variant-numeric: tabular-nums`).

### Named Rules

**The Mono Boundary Rule.** JetBrains Mono is for numeric and metric contexts only: readouts, table column headers, badge labels, section eyebrows above data panels, timing values. It is never used for navigation, body copy, or hero copy. The boundary is the meaning — mono signals "you are reading a number's context."

**The Size Floor Rule.** No text below 9px. The minimum label size (9px) appears only in tight metric readouts (zone bar labels, metric row identifiers). 10px is the practical floor for everything else.

## 4. Elevation

Cobbra is flat by design. No box-shadows on surfaces at rest. No backdrop-blur on content cards. Depth is expressed exclusively through tonal layering: each OKLCH lightness step adds approximately 3%, creating a visible but unadorned stack. The app layer defines four surface levels — background (8%), secondary (11%), card (14%), hover (17%) — plus two border gradations (21%, 27%). You read depth from which surface something sits on, not from whether it casts a shadow.

Two structural exceptions exist. The keyboard focus ring uses `box-shadow: inset 0 0 0 2px var(--accent)` on interactive elements — this is a structural signal (not an elevation signal) that a surface is focused. The mobile sidebar drawer uses a near-void directional shadow (`8px 0 32px oklch(4% 0.006 142 / 0.5)`) when it overlays the content layer — this is a functional overlay indicator, not decoration.

### Named Rules

**The Flat-By-Default Rule.** If a surface appears to "hover" or needs visual separation: move it to the next tonal step (e.g., app-hover at oklch 17%), not a shadow. If something genuinely overlays content (mobile drawer, modal), use a 1px border at app-border-bright plus the appropriate tonal background — reach for box-shadow only as the overlay-depth signal of last resort.

**The Tonal Stack Rule.** The four surface steps are ordered and non-skippable. A card surface (14%) sits on a page background (8%); a hover state (17%) sits on a card surface (14%). Jumping steps (placing a 17% hover surface directly on the 8% page background) creates false depth readings. Follow the stack.

## 5. Components

### Buttons

Two button contexts share the same venom color but differ in radius and scale, reflecting their register.

**Brand Primary Button** (`.cb-btn-primary`): Venom green background, near-void text (`#060606`), 13–14px Barlow 700, 2px radius (precision instrument feel), 13px vertical / 20–26px horizontal padding. Hover: `filter: brightness(0.88)`, gated behind `@media (hover: hover) and (pointer: fine)`. Active: `filter: brightness(0.78)`. No translateY on hover — this is a structural CTA, not a playful control. Focus visible: 1.5px venom outline, 3px offset.

**Brand Ghost Button** (`.cb-btn-ghost`): Transparent background, brand-border-bright border (1px), text-dim color, identical size to primary. Hover: text lifts to brand-text, border to brand-text-ghost. Active: `color-mix(in srgb, var(--cb-border-hi) 60%, transparent)` background. Always paired alongside a primary — never used alone.

**App Primary Button** (`.btn-primary`): Venom background, near-void text, 6px radius, 8px / 16px padding, 13px Barlow 600. Hover: `oklch(96% 0.24 138)` (slightly brighter, same hue). Active: `filter: brightness(0.82)`. Disabled: `opacity: 0.38`, cursor removed.

**App Ghost Button** (`.btn-ghost`): Transparent, app-border-bright border. Hover: text-primary, app-hover background. Active: `color-mix(in srgb, var(--border-bright) 80%, transparent)`.

**App Danger Button** (`.btn-danger`): Transparent, heart-red text (`#FF4D6D`), 25% heart-color border. Hover: 10% heart background tint, 40% heart border. Destructive actions only — delete segment, remove goal. Never used alongside a primary CTA.

### Cards and Panels

**Standard Card** (`.card`): App-card background (oklch 14%), 1px app-border edge, 10px radius, 20px padding. No shadow. When the card is interactive (clickable), hover transitions to app-hover background over 150ms expo-out. Focus: inset venom box-shadow.

**Last Ride Strip** (`.last-ride-strip`): Full-column-width horizontal panel, same card background. Horizontally structured — ride identity at left (210px fixed), 1px vertical divider, then metric slots at flex. On hover: app-hover background, 150ms expo-out. On active: `opacity: 0.88`. Focus: inset venom box-shadow. This pattern applies to any clickable panel spanning full column width.

**Pricing Card** (`.lp-pricing-card`): Same card background and border, but the highlighted tier adds a venom-green border and a `linear-gradient(160deg, color-mix(in srgb, var(--accent) 5%, transparent) 0%, var(--bg-card) 50%)` background tint. This is the one sanctioned use of a gradient — and it is structural (marks the recommended tier), not decorative.

### Navigation (Sidebar)

220px fixed sidebar, app-surface background (oklch 11%), 1px app-border right edge. Logo lockup in the top 20px / 28px padding zone.

**Nav Items** (`.nav-item`): 10px/12px padding, 6px radius, 14px Barlow 500, text-dim default. Hover: app-hover background, text-primary color. Active: `color-mix(in srgb, var(--accent) 10%, transparent)` background, venom text, `1px solid color-mix(in srgb, var(--accent) 15%, transparent)` border — a fine venom edge that marks the selected route. On mobile (<768px): sidebar slides in from left as a drawer (`transform: translateX(-100%)` → `translateX(0)`), with a semi-transparent overlay behind it.

### Inputs and Text Fields

**Filter Input** (`.filter-input`): App-card background, app-border-bright border (1px), 6px radius, 13px Barlow body. Focus: border-color and outline-color shift to venom. Placeholder: text-muted. Dark color-scheme applied to date inputs for consistent rendering.

**Notes Textarea** (`.notes-textarea`): Same treatment, app-hover background (slightly elevated from card), resize vertical, 1.6 line-height. Focus: venom border. Placeholder: text-muted. Auto-save on blur — no explicit save button.

**Login Inputs**: app-card background, app-border-bright border, 6px radius, 10px/14px padding, 14px Barlow. Focus: venom border and venom outline. Labels above inputs are 12px Barlow 600, uppercase, 0.5px tracking, text-dim color.

### Data Visualization Bars (Signature Component)

HR zone bars, goal progress bars, PR speed bars, and landing zone readout bars all use the same pattern:

1. **Track div**: app-hover (or app-border) background, fixed height (2px–10px by context), `overflow: hidden`, matching border-radius.
2. **Fill div**: `position: absolute; inset: 0`, data-specific color (zone bars use semantic OKLCH colors; PR bars use a venom-to-venom-50% gradient; goal bars use venom). `transform-origin: left center`. `transform: scaleX(fraction)`. Transitions with 400–600ms expo-out after data loads.

This pattern is GPU-composited. Never use `width:` animation on fill divs — it triggers layout and paint. The fill element's width is always 100% of the track; scale controls the visible extent.

Zone bar semantic colors (landing readout): Z1 recovery `oklch(54% 0.12 264)`, Z2 aerobic `oklch(58% 0.15 142)`, Z3 threshold `oklch(68% 0.14 88)`, Z4 VO2 max `oklch(60% 0.15 38)`, Z5 neuro `oklch(52% 0.14 20)`.

### Badges

**File Type Badges** (`.badge-gpx`, `.badge-fit`): 11px Barlow 600, 4px radius, 2px/8px padding. GPX: speed-blue 12% background tint, speed-blue 20% border, speed-blue text. FIT: venom 12% tint, venom 20% border, venom text. Always uppercase, 0.5px tracking.

**Weather Badge** (`.weather-badge`): Pill (20px radius), speed-blue 8% tint background, speed-blue 18% border. 12px text, text-dim color. Informational only — never interactive.

**Segment Creator Badge**: Same pill radius, app-hover background, app-border edge, text-muted color. Denotes ownership metadata.

### Upload Zone

Dashed border (2px dashed app-border-bright), 10px radius, 60px/40px padding, app-card background. On hover or drag-over: border-color becomes venom, background becomes venom-dim (10% venom tint). 200ms transition. This is the one UI surface where a venom background tint is earned by the drag-target state — it is not applied at rest.

## 6. Do's and Don'ts

### Do:

- **Do** use venom green (`#39FF14`) for the single most important interactive or data element per screen: the CTA button, the active nav route, the personal record value, the plan section heading that demands attention.
- **Do** express depth through the OKLCH surface stack (8% → 11% → 14% → 17%). Each step is a tonal layer, not a shadow.
- **Do** use `filter: brightness()` for button hover and active states — it maintains the exact hue of venom without requiring a second color value. Hover at 0.88, active at 0.78–0.82.
- **Do** gate hover styles with `@media (hover: hover) and (pointer: fine)` to prevent sticky hover on touch interfaces.
- **Do** use `transform: scaleX()` with `transform-origin: left center` on an `overflow: hidden` track div for all progress bars and zone fills. GPU-composited, no layout cost.
- **Do** use tabular-nums on all metric readouts (`font-variant-numeric: tabular-nums`). Numbers that shift width while reading destroy scanning.
- **Do** animate only `opacity` and `transform`. Never transition `width`, `height`, `padding`, `margin`, `top`, or `left`.
- **Do** use JetBrains Mono for every numeric label, zone identifier, badge text, and section eyebrow above data panels.
- **Do** apply `@media (prefers-reduced-motion: reduce)` globally, zeroing all transitions and animations to 0.01ms.
- **Do** use the inset `box-shadow: inset 0 0 0 2px var(--accent)` pattern for keyboard focus rings on interactive elements — not outlines that clip to border-radius unexpectedly.

### Don't:

- **Don't** use Strava's social framing: activity feeds, kudos counts, engagement counters, streak mechanics borrowed from consumer apps. Every design choice is made for the athlete, not the algorithm.
- **Don't** produce Garmin Connect visual density: every metric competing for attention, nested cards, feature-overflow layouts where the dashboard is a list of everything the tool can do.
- **Don't** use generic SaaS dashboard patterns: hero-metric templates (big number, small label, gradient accent), identical card grids repeating icon + heading + text, section intros that restate the heading.
- **Don't** reach for gaming / esports visual language: neon for neon's sake, aggressive glow on passive surfaces, venom used as ambient decoration.
- **Don't** produce the Dark Mode Cliché: blue or purple gradient hero overlays, glassmorphism as default card treatment, blurs used decoratively, purple-on-black as "dark mode."
- **Don't** use `border-left` or `border-right` greater than 1px as a colored accent stripe on cards, list items, or callouts. Rewrite with a full border, a background tint, a leading number, or nothing.
- **Don't** use gradient text (`background-clip: text` + `background: linear-gradient(...)`). Use a single solid color. Emphasize through weight or scale.
- **Don't** add a second accent color to the UI chrome. The data visualization palette (speed, heart, cadence, elevation, power) is chart-only and never appears in navigation, buttons, alert borders, or section headings.
- **Don't** animate layout properties. Width, height, padding, top, left: never. The GPU path is opacity + transform only.
- **Don't** set text below 9px. The absolute minimum label size is 9px in tight metric readouts; 10px is the practical minimum for everything else.
- **Don't** add a shadow to any surface at rest. Shadows are structural signals for genuine overlays (mobile drawer, modals) only — not a default for "making a card feel elevated."
- **Don't** use the hero-metric template: large number, small label below, supporting stats, gradient accent. This is the SaaS data-display cliché. Cobbra presents data as a table, a chart, or a strip — never as a metrics hero block.
