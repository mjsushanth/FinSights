# Diagram export gotchas

Three XML-validity/layout classes hit while building this deck's diagrams, none
caught by `diagram-design`'s `self_check.py` (it validates structure, not these).
Recorded here so the next export doesn't rediscover them by trial and error.

## 1. HTML named entities are not valid standalone XML

`&middot;`, `&nbsp;`, and similar HTML5 named entities parse fine in a browser
but are undefined in plain XML without a DTD declaring them. `self_check.py`
passes; `xml.dom.minidom.parse()` on the exported `.svg` fails with
`xml.parsers.expat.ExpatError: undefined entity`.

Fix: use the literal Unicode character instead (`&middot;` -> `·`) before export.
Hit in `boilerplate-treemap.html`, `fargate-deployment.html`,
`wrongyear-sankey.html`, `architecture.html`.

## 2. A literal `--` inside an XML comment is invalid

`<!-- ... -- ... -->` is illegal XML: a comment body may not contain `--`
anywhere except as the closing delimiter. HTML tolerates it; strict XML parsers
(`xml.dom.minidom`, most SVG consumers) reject it the same way as gotcha #1.
Easy to introduce by habit, since this deck's own prose style uses `--` as a
dash constantly.

Fix: use `;` or `,` inside dev-comment prose, or drop the comment. Doesn't
affect visible `<text>` content -- only `<!-- -->` comment bodies are
restricted this way.

Hit in `rerank-radar-won.html` / `rerank-radar-full.html` dev comments during
the rev-6 radar rework (2026-09-11).

## 3. Long labels clip past the viewBox edge -- not caught by any validator

Not an XML-validity bug -- `self_check.py` and strict XML parsing both pass --
but a `text-anchor="end"` label combined with a long string can run past
`x=0` (or any edge) and clip silently. Neither `self_check.py` nor XML
well-formedness checks catch this; only a rendered screenshot does.

Concretely: a fishbone incident-callout tick at the type's default fraction
(`m=3`, i.e. the label's anchor point at the bone's midpoint) put a 63-character
label's left edge at a negative x-coordinate. Fix was to move the tick closer
to the spine (`m=1`, fraction 1/6 instead of 1/2) to buy horizontal room, not
to shorten the text.

Lesson: always screenshot-verify an SVG that carries a long `text-anchor="end"`
or `text-anchor="start"` label near a canvas edge -- don't trust "the validator
passed" as proof the diagram renders correctly. Hit in `measurement-fishbone.html`
during the rev-6 5-bone rebuild (2026-09-11).
