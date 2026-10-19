# Motion

Two things move; nothing else.

1. **Dialogs**: on open, opacity 0 → 1 and scale 0.98 → 1, 120ms `ease-out` (`@starting-style` on `dialog[open]`). Backdrop fades with it. No exit animation.
2. **Running dot**: the highlighter dot in the live run widget and on running status marks pulses opacity 1 → 0.35 → 1 over 1.4s, infinite.

Hover changes background colour instantly (no transition). No page-load animations, no hover lifts, no skeleton shimmer.

`@media (prefers-reduced-motion: reduce)`: both animations off (`animation: none; transition: none`).
