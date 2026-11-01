# Design

## What the page is for

Someone with a flexible load (a heat pump, an EV, a washing machine) wants to know when power
is cheap. The page answers that before they type anything, then lets them ask about their own
situation.

## The one bold thing: the chart is the page

The page opens on the day's price columns with the answer as a plain sentence above them. The
cheapest and priciest windows are computed in code, so it loads instantly, costs nothing and
cannot be wrong in the way a model can. Everything else is quiet type on a plain surface.

A first version put a text box in the middle of an empty page and hid the answer behind a model
call. It worked and it was generic. The chart is what makes this subject distinct.

## Colour is meaning

- **Blue is cheap, orange is expensive.** Nothing else in the interface uses either. Buttons,
  links and focus rings are ink only, so a colour on screen always means a price.
- Everything outside the two windows is a quiet grey, so the eye goes to the two answers.
- Palette checked with a colour-vision validator in both modes. The worst separation between
  blue and orange is a ΔE of 24.7 under colour-blind simulation, against a target of 8.
- Surfaces are `#fcfcfb` and `#1a1a19`. Dark mode is a warm dark grey, not black.
- Muted text is never used for anything that has to be read. Secondary ink is `#52514e`.

## Type

One family, Bricolage Grotesque, self-hosted under the SIL Open Font License (`static/fonts/`).
Its optical-size axis makes it expressive at headline size and sturdy in running text, so no
second face is needed. Axis numbers use tabular figures; large numbers do not.

## The chart

- Columns, at most 24px wide, 4px rounded at the data end, square at the baseline, growing from
  a hairline zero line. Negative prices hang below it.
- A 2px surface gap between neighbours, instead of borders.
- Hairline solid gridlines. A tick label sits on every nice value, and the top of the scale
  stops just above the tallest column.
- The two windows are direct-labelled with a bracket and also named in a legend. On a phone the
  labels shorten to "Cheapest" and "Priciest", and one is dropped if they still collide.
- Hover or tap shows a tooltip with the value first, then the time in UTC and in the viewer's
  own time zone. Arrow keys, Home and End do the same from the keyboard, and announce it.
- A table view carries every value for anyone who prefers it or cannot use the chart.
- One moment of motion: the columns rise once, left to right, on load. It is off when the
  viewer asks for reduced motion.

## Rejected on purpose

- A rounded card around the question box, the usual look for this kind of tool.
- A blue button, because blue means cheap here.
- Tracked-out capital labels above headings, numbered sections, and arrows on links.
- A framework and a build step. See [ADR 004](adr/004-plain-html-ui.md).

## Checked

`scripts/ui_check.mjs` drives the page in headless Chromium: the headline, the columns, hover,
keyboard, the table, light and dark, a phone width with no horizontal scroll, whether the whole
chart is above the fold on a 1280 by 900 screen, errors and rate limits, and a hostile server
response (injected `<img onerror>` and `<script>`) that must render as inert text. It caught two
real layout bugs while the page was being built.

## Not done yet

- Only one zone has data, and it is synthetic. The chart code handles days of 23 or 25 hours
  and 15-minute prices, but that has only been exercised with the synthetic day.
- Only checked in Chromium. Firefox and Safari are untested.
- The brackets' label placement is a heuristic for a single pair of windows.
