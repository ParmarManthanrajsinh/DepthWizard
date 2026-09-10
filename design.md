# Design — DepthWizard

A locked design system for DepthWizard (ISRO SAC SIH26175). Every page redesign reads this file before emitting code. Do not regenerate per page — extend or amend this file when the system needs to grow.

## Genre
editorial (manifesto / constructivist polemical declaration register)

## Macrostructure family
- Marketing / Workspace pages: Workbench (manifesto declaration input console + live telemetry deck)
- Telemetry / App pages: Stark Monolithic Viewport with Sharp Rectangular HUD
- Content pages: Poster-Type Specimen

## Theme: Manifesto
- `--color-paper`:       #0c0c0e (Stark matte carbon)
- `--color-paper-2`:     #16161a (Industrial slab deck)
- `--color-paper-3`:     #222228 (Elevated contrast slab)
- `--color-paper-subtle`: #111114 (Deep contrast well)
- `--color-ink`:         #f4f4f5 (High-contrast chalk white)
- `--color-ink-2`:       #a1a1aa (Slate body copy)
- `--color-ink-dim`:     #71717a (Muted technical annotations)
- `--color-rule`:        #27272a (Stark hairline border)
- `--color-rule-subtle`: rgba(255, 255, 255, 0.08)
- `--color-accent`:      #ff3333 (Manifesto signal red, high-voltage declaration)
- `--color-accent-ink`:  #0c0c0e (Stark ink on accent)
- `--color-accent-amber`: #f59e0b (Calibration warn)
- `--color-accent-green`: #22c55e (Telemetry pass)
- `--color-focus`:       rgba(255, 51, 51, 0.4)

## Typography
- Display: 'Space Grotesk', -apple-system, sans-serif, weight 700, uppercase, style normal (no italic headers)
- Body: 'Inter', -apple-system, sans-serif, weight 400–500
- Mono: 'JetBrains Mono', monospace, weight 500–700
- Display tracking: -0.035em
- Type scale:
  - `--text-xs`: 0.75rem
  - `--text-sm`: 0.85rem
  - `--text-base`: 0.95rem
  - `--text-md`: 1.15rem
  - `--text-lg`: 1.45rem
  - `--text-xl`: 2.1rem
  - `--text-2xl`: 2.85rem

## Geometry & Radii
- All radii: **0px** (Sharp brutalist / constructivist geometry throughout)
- No rounded pills, no soft corners.

## Spacing
4-point scale:
- `--space-3xs`: 0.25rem (4px)
- `--space-2xs`: 0.5rem (8px)
- `--space-xs`:  0.75rem (12px)
- `--space-sm`:  1rem (16px)
- `--space-md`:  1.5rem (24px)
- `--space-lg`:  2rem (32px)
- `--space-xl`:  3rem (48px)
- `--space-2xl`: 4.5rem (72px)

## Motion
- Easings: cubic-bezier(0.16, 1, 0.3, 1)
- Transitions: 120ms–200ms crisp snaps; zero float or hover bobbing
- Reduced-motion: instantaneous state swaps

## CTA Voice
- Primary CTA: Oversized high-contrast rectangular block, bold uppercase, signal red `#ff3333` or pure chalk `#f4f4f5` invert, 0px radius.
- Secondary CTA: Sharp 1px border on `#16161a`, bold uppercase text `#f4f4f5`.

## What pages MUST share
- Header wordmark: ISRO SAC SIH26175 badge + `DEPTHWIZARD` in all-caps bold geometric sans
- Manifesto palette (`#0c0c0e` carbon, `#ff3333` signal red, `#f4f4f5` chalk)
- Typography pair (`Space Grotesk` uppercase display + `Inter` body + `JetBrains Mono` telemetry)
- Sharp 0px geometry across all cards, buttons, badges, tables, and HUD overlays
