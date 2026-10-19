---
name: design-system
description: Visual design system of video-notes-app (colours, type, spacing, components, motion). Read before any change to the web UI in src/video_notes/web/.
---

# video-notes-app design system

A personal commonplace book: fast vertical videos turned into slow, sourced notes and ideas. One reader, on a laptop, in GNOME, offline.

Read the files here before touching `src/video_notes/web/`:

- `colors.md` — the six colours, light and dark, and where each may be used
- `typography.md` — three installed faces and the type scale
- `spacing.md` — spacing scale, radii, layout widths and breakpoints
- `components.md` — recipes for every component, including the signature source strip
- `animations.md` — the two things that move

Rules: every value in CSS comes from these tokens (as custom properties in `style.css`). The highlighter is a marker, never a button fill. No shadows except dialogs. No web fonts or CDNs.
