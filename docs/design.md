# Design system

Colour, type, spacing and the component vocabulary.

[&larr; Back to the README](../README.md)

---

## Design system

Tailwind v4 with CSS custom properties in `frontend/src/index.css`. Light is the
default; a `.dark` class on `<html>` flips the tokens, set before paint by an
inline script to avoid a flash. No component library — `src/components/ui/*` holds
small primitives (Button, Card, Table, Modal, Input, Badge) and
`src/components/Icon.tsx` is a dependency-free stroke icon set.

**Colour.** A muted teal brand on warm-sand neutrals in light mode, and a
desaturated teal on soft charcoal in dark - calm enough to sit in front of all
day. Nothing fluorescent, and no coloured glows: the primary button carries an
ordinary elevation shadow, cards have plain surfaces, and table rows highlight
with a neutral wash rather than a tint of the brand.

The teal is readable as text (about 5.6:1 on white), so `--link` and `--primary`
can be the same colour, which the previous neon palette could not manage. Status
colours are muted to match: a warning should read as a warning, not as an
alarm.

The chart tokens are a separate palette, validated for the OKLCH lightness band,
a chroma floor, adjacent-pair separation under colour-vision deficiency, and
contrast against the chart surface. `--chart-1` is a *more saturated* teal than
the UI brand for a reason: at the brand's chroma a thin chart line falls below
the floor and reads as grey. A calm UI colour and a legible data colour are not
the same requirement.

The sign-in and sign-up pages share `src/components/AuthLayout.tsx`: a lime brand
panel beside the form. The panel keeps its colour in both themes — it *is* the
brand — while the form panel follows the app surface, and below `lg` it collapses
to a banner above the form rather than disappearing.

The sidebar is resizable by dragging the handle on its edge and collapses to an
icon-only rail when that handle is clicked; both the width and collapsed state
persist.

Data loading uses two small hooks in `src/lib/api.ts` (`useApi` for reads,
`useMutation` for writes) rather than a data-fetching library — the app is almost
entirely "load a page, mutate, reload".

---

