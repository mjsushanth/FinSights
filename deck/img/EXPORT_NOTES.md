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

## 4. A diagram that is valid alone can still overflow its slide

The biggest gap of the four, because it is invisible to every check that
matters for the other three: `slidev build` succeeds, every SVG parses as
strict XML, the dev server serves without error, and the GitHub Actions
workflow goes green. None of that proves a single slide renders inside its
own canvas. This deck shipped with every diagram slide overflowing its
980x551 canvas (no height rule existed in `style.css` at all) and, on the
three staged slides, the second `v-click` figure landing entirely off-screen
below a first figure that was hidden by opacity but still occupying ~340px
of layout -- neither fault surfaced until someone loaded the deployed page.

Two contributing traps worth naming on their own:

- **`v-click` hides by opacity, not `display`.** A hidden element still
  reserves its layout space. This is true of any v-click'd element, not just
  images -- plain paragraphs do it too. On slide 4, three click-stages of
  not-yet-shown text reserved space even at the first click, pushing that
  slide's diagram down before staging was even a factor. Fix:
  `.slidev-vclick-hidden { display: none; }`, scoped as narrowly as the
  layout allows.
- **A height cap that fits most diagrams can still overflow one.** A global
  `max-height` on diagram images has to satisfy the slide with the most
  accumulated text above its image, not the average slide. Voice-pass edits
  that grow a slide's prose by even one line, made after the cap was tuned,
  can silently push a previously-fine diagram past the edge again.

Lesson: build, XML validity, and a green workflow verify the diagram and the
markup. None of them verify the *slide*. A deck is not checked until someone
has walked every diagram slide at every click state in an actual browser
viewport and confirmed nothing crosses the canvas edge -- and that check has
to be redone after any prose edit, not just after a diagram edit. Hit
building this deck (2026-09-11) and caught only by loading the page Joel had
just enabled Pages for, not by any tool in the pipeline.

## 5. A dollar amount can silently become LaTeX in a presenter note

Not a diagram bug, but the same failure mode: invisible everywhere except
the one view that actually renders it. This deck's `<!-- -->` presenter
notes go through a markdown pipeline with math support enabled, and a `$`
opens inline math the same way it does in LaTeX. Two unpaired-looking `$`
signs anywhere in the same note -- even across paragraph breaks, even many
sentences apart -- get treated as one matching pair, and everything between
them renders as a garbled string of italic single-letter variables instead
of the prose that was written.

Concretely: a note contained `$17/month` early on and, in a verbatim Joel
quote, `17$` (his own phrasing, dollar sign after the number) much later.
Slidev paired those two `$` across roughly 40 lines and several paragraphs
into one "equation," and the entire span rendered as nonsense in Slide
Overview / Presenter Mode. `slidev build`, the plain slide view, and the
GitHub Actions workflow never touch this rendering path, so none of them
caught it.

Fix: escape every literal `$` in a presenter note as `\$`. Cheap insurance
-- do it for any dollar figure in a note, not just ones that happen to
pair up, since a later edit elsewhere in the same note can create a pairing
that does not exist yet. Hit in slide 2's presenter note during the
2026-09-11 reframe, caught only by opening Slide Overview, not by any build
or validation step.
