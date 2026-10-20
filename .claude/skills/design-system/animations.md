# Motion

Three things move; nothing else.

1. **Running dot:** the gold dot (live widget, "running" pill, current run stage) pulses opacity 1 → 0.35 → 1 over 1.4s, infinite.
2. **Dialogs:** on open, opacity 0 → 1 and scale 0.98 → 1 over 180ms (`--dur-base`, `--ease-out`). The backdrop fades in with it and blurs the page 6px. No exit animation.
3. **Gold button:** the primary button gains its soft gold glow on hover (180ms). Buttons nudge down 1px while pressed.

Also allowed: background tints on hover (120ms), and the fold chevron's turn.
Not allowed: page-load animations, hover lifts or scaling, skeleton shimmer.

`@media (prefers-reduced-motion: reduce)` turns every animation and transition off.
