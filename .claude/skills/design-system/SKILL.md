---
name: design-system
description: Visual design system of Rot2Gold (colours, type, spacing, components, motion). Read before any change to the web UI in src/rot2gold/web/.
---

# Rot2Gold design system

Rot2Gold turns saved TikTok videos into sourced notes, ideas, learnings and events. Tagline: **Turn brain rot into bright ideas.** One reader, on a laptop, in GNOME, offline.

The look: a single gold light rising out of black, the "horizon" on the brand board (`references/brand-showcase.png`). Minimal, nocturnal, calm. **Always dark** (Marco's choice, 2026-10-20): there is no light theme.

Read the files here before touching `src/rot2gold/web/`:

- `colors.md`: the blacks, greys, cream and the one gold, and where each may be used
- `typography.md`: three bundled faces and the type scale
- `spacing.md`: spacing scale, radii, layout widths and breakpoints
- `components.md`: recipes for every component, including the signature source strip
- `animations.md`: the three things that move
- `references/`: the brand board and the app icon

Rules:
- Every value in CSS comes from these tokens (custom properties in `style.css`).
- Gold is light, not paint: marks, underlines, the primary button, "new" pills. Never large gold areas.
- No shadows except overlays (dialogs, menus); elsewhere elevation is a soft gold glow on gold marks.
- Fonts are bundled in `static/fonts/` (OFL). No web fonts from other hosts, no CDNs.
- No emoji, and no Unicode glyphs as icons.

Source: designed in Claude Design (project "Rot2Gold Design System", exported 2026-10-20). It replaced the earlier paper-and-highlighter system.
