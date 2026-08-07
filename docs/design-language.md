# Floresu design language

The durable rules behind Floresu's look and feel: how to make a UI change that stays *warm, calm, and accent-forward where it counts* rather than drifting into a generic dashboard. Read this before touching the frontend. It is the "why" and the "when," not the "what."

**Token values are not in this document.** Every color, radius, and font value lives in code as the single source of truth. This guide names *roles* and *rules* and points at the code for the numbers. Naming a hue (coral, espresso, olive) is fine here; hex and oklch values are not. Measured contrast ratios are stated, because they are the evidence a rule rests on and they are not recoverable from a token file.

| Concern | Canonical source (do not duplicate) |
|---------|-------------------------------------|
| Color, radius, and font-stack tokens, and the tag palette | `frontend/src/theme/tokens.css` |
| Font faces (self-hosted, Latin subset) | `frontend/src/theme/fonts.css` |
| Tailwind bridge, base style, display / caption / metadata / layout utilities | `frontend/src/globals.css` |
| The fixed stylesheet import order | `frontend/src/main.tsx` |
| Tag and identity hue assignment (the hash) | `frontend/src/lib/colorForName/` |
| Hue fill and ink mixing | `frontend/src/lib/hueTint/` |
| Field shape and field-label register | `frontend/src/components/FormInputField/constants.ts` |
| Button variants | `frontend/src/components/ui/button.tsx` |
| The one copied color value (a static SVG cannot read a token) | `frontend/public/favicon.svg` |
| Component and view implementations | `frontend/src/components/`, `frontend/src/views/` |

Target stack: React, Tailwind v4, and one vendored shadcn/ui primitive. `globals.css` bridges the tokens onto Tailwind's vocabulary, so a new component looks right with no per-component color work. There is no dark mode; see "Extending this language" below.

---

## 1. Principles

Floresu should feel like a well-kept paper notebook, not a control panel. The record belongs to the user, and the chrome stays out of its way.

1. **Warm over neutral.** Never pure black on pure white, and never pure white as an ink. The ground is bone, the ink is espresso, and every gray leans warm, never blue.
2. **Minimal, but not cold.** Restraint in the *quantity* of elements and chrome; generosity in whitespace, type size, and warmth. When in doubt, remove.
3. **Accent-forward where it counts, calm where you read.** Coral is loud on high-impact surfaces and recedes to punctuation in dense reading areas. This tension is governed by the accent placement map below.
4. **Editorial, human typography.** A humanist grotesque carries the interface; a warm serif appears only for the big human moments.
5. **The record is the interface.** Worklog entries, bullets, and resumes are the product. Nav, borders, and shadows stay quiet so the user's own content carries the color and the weight.

New work is judged against these five. A new hue, a new component variant, or a new token has to justify itself here first. Prefer removing over adding.

## 2. Brand and voice

- **Name and domain:** Floresu, `floresu.com`. The API and the agent endpoint live on their own subdomains of it.
- **Wordmark:** lowercase `floresu` set in the serif family with tight tracking. This is the one place the brand signs its name in serif. It is not a display moment and needs no exemption from that rule, because it takes the plain serif family rather than a display utility. No glyph, and no logo mark yet: the favicon is a neutral placeholder.
- **Voice in UI and marketing copy:** warm, confident, plain, second person. "Every win, worth keeping," not "Log your professional accomplishments." Encourage, never lecture.
- Product positioning is deliberately code, not prose: the public page's copy lives as typed data in `frontend/src/views/LandingView/constants.ts`, so a copy edit is a one-file change that never touches JSX. There is no product document to keep in step with it.

## 3. Color

The palette has a deliberate shape. **One** warm accent does the heavy lifting, a warm-neutral ground and ink carry everything else, **three** semantic hues cover done, destructive, and warning, and a separate muted palette handles tags. There is no cool "info blue": informational emphasis uses ink, neutral, or the accent.

### 3.1 The accent placement map (the governing rule)

This table is what keeps "accent-forward" from fighting "minimal." Before adding anything coral, place it in the right register first.

| Register | Where coral appears | Sites |
|----------|--------------------|-------|
| **Loud** (fills, large type, blocks) | High-impact, low-density surfaces | The landing hero and the showcase band; primary calls to action; focus rings; the active nav item and its single bloom marker; an active filter chip; the live-activity dot; the newest activity row's tint |
| **Calm** (paper and ink; coral only as a link, icon, or hairline) | Dense reading and working areas | Worklog rows, library rows, profile cards, the resume editor form, the sidebar apart from its active item, every form, badges, metadata, and tables |
| **Never** | N/A | An accent or bloom fill behind reading content; a hue on skill chips; more than one serif display moment in a view |

Exactly one nav marker is bloom: the bar on the active primary-nav item, and the app chrome carries no other bloom fill. A **secondary** nav's active item takes a neutral fill instead, not the accent: two competing "active" treatments on one screen read as ambiguity, and an accent-derived hover on a secondary nav lets hover impersonate the active state.

### 3.2 The two-step coral family

Coral exists at two depths, and the split is load-bearing rather than cosmetic.

- The **bright bloom** is a showcase fill. It cannot carry a light label: espresso on bloom measures **5.45:1** and passes AA, while pure white on bloom measures **3.08:1** and the cream ink measures **2.86:1**. Both fail. So a bloom fill carries espresso text, short, and never a reading paragraph.
- The **action coral** is the primary fill and the coral link color. Its own contexts pass AA as text: on the page ground **4.81:1**, on a card **5.08:1**, and its cream label on the fill **4.84:1**.
- The **accent ink** is deliberately one step deeper than the action coral, on the same hue and chroma. The two look identical, and collapsing them is the natural simplification that reintroduces a measured failure: the action coral on the accent tint clears only **4.00:1**, under the 4.5:1 floor, while the deeper step measures **4.64:1**. Keep them separate.

Rule that falls out of this, and it has no exceptions: **anything on an accent fill takes the accent ink.** Muted ink on an accent fill measures **4.49:1** and fails, which is the pairing an implementer reaches for by habit on a timestamp.

### 3.3 Semantic hues

Three hues, each with one fixed meaning. Never repurpose them, and never let the hue alone carry the meaning; see the accessibility rules below.

| Hue | Meaning | Used for |
|-----|---------|----------|
| Olive | done, connected, succeeded | A finalized resume, the default identity variant, a connected agent, a submitted application |
| Crimson | removal | Delete, archive, revoke, erase. Deeper and cooler than coral so it never reads as the accent |
| Ochre | warning and irreversibility short of removal | The stale-revision prompt, the copy-on-write scope warning, the finalize and submit gates |

Crimson is reserved for removal. An irreversible action that keeps its content, such as marking an application submitted, takes ochre: crimson on a positive milestone misreads the action.

A **tinted panel carries full ink, not its own hue as text.** The olive hue on its own tint measures **2.97:1** and fails; full ink on that tint measures **13.73:1**. The crimson tint is the one that also carries its own hue as text, at **4.94:1**, and it does so only on error surfaces that are crimson-bordered as well.

### 3.4 Tags and identity color

Tag color is a **domain truth**, not a styling choice. A tag or agent name is hashed into a fixed ten-hue muted palette, so one label renders in the same hue in every view it appears in. Two rules protect that:

- **The hash is frozen** and lives in one module. Import it; never re-derive it.
- **The palette order is a frozen contract.** The hash selects an entry by position, so reordering the palette repaints every tag and avatar that already exists.

The palette is muted by design, which is why it cannot carry light ink. Both a tag's fill and its ink are mixed from that one hue, through the shared mixing helper: the ink is the same hue, deeper. A surface chooses only how strong its fill is; the ink strength is fixed, so a fill and its ink can never drift apart.

**Skills are never hash-colored.** They render as neutral chips. Coloring them would double the color load and blur two concepts that look alike but are not: a tag is a free label on an entry, a skill is a curated list item.

### 3.5 Contrast posture, measured

These are the measured ratios for the pairings the app actually renders. Publishing them is the point: the rules above are only as good as the arithmetic under them.

| Pairing | Ratio | Verdict |
|---------|-------|---------|
| Ink on the page ground, and on a card | 15.85:1, 16.75:1 | Far past AA |
| Muted ink on the ground, on a card, on the muted fill, on the secondary fill | 5.41:1, 5.72:1, 4.94:1, 4.69:1 | AA for normal text |
| Coral as text on the ground, and on a card | 4.81:1, 5.08:1 | AA |
| The accent ink on the accent fill | 4.64:1 | AA. The action coral there is 4.00:1 and fails |
| Muted ink on the accent fill | 4.49:1 | Fails. Use the accent ink |
| Full ink on the accent fill | 13.17:1 | AA |
| Espresso on the bloom fill | 5.45:1 | AA. White is 3.08:1 and fails |
| Crimson as text on a card, and on its own tint | 6.42:1, 4.94:1 | AA |
| The crimson fill's label | 6.11:1 | AA |
| Full ink on the olive or ochre tint | 13.73:1 | AA. The olive hue as text there is 2.97:1 and fails |
| A filled progress segment against an empty one | 4.31:1 | Past the 3:1 non-text floor |

**The one honest exception: the avatar initial.** The letter inside a hashed avatar measures **3.55:1 to 4.36:1** across the ten palette entries. That clears the 3:1 non-text floor on all ten, where the previous white-on-hue treatment missed it on seven, but it does not reach 4.5:1. Do not claim AA for it. The posture is that the initial is a redundant graphic and the actor's full name is rendered as text beside it at every site, so nothing depends on reading the letter. If a later change wants 4.5:1 there, the lever is the **text mix strength**, not the fill: lowering the fill barely moves the ratio, because both shades lighten together.

## 4. Typography

An editorial-warm pairing: the grotesque carries the interface, the serif is a spice for human moments. Three faces, each with a job. The faces are defined in `fonts.css`; the type steps and display utilities are in `globals.css`.

| Face | Role |
|------|------|
| Display serif | The hero line, empty-state lines, the bloom headline, the wordmark. **Never** body copy or a UI label |
| Humanist grotesque | The workhorse: all UI, body copy, most headings, buttons, nav |
| Monospace | Tags, timestamps, counts, IDs, and other metadata |

Rules:

- **One serif display moment per view, maximum.** A display moment is a use of one of the display utilities, which is what makes the rule countable: serif set through the plain serif family, such as the wordmark or the bloom headline, is not a display moment. It is a spice; overuse makes it generic. Views that have one put it in their **empty state**, which is the convention across the app: an empty list is the moment a warm line helps and a dense list is not. A view with content usually has no display moment at all.
- **One caption treatment, everywhere.** Form labels, helper text, column headers, and metadata labels take the bare caption utility, with no uppercase and no added tracking. It exists as a utility rather than a Tailwind step because the size sits between two steps, so a view that reaches for either drifts off the scale.
- **Tabular numerals** for anything that counts or aligns in a column. The metadata utility already sets them.
- **Reading measure is a fixed column.** A single-column view takes the shared reading measure; the working surfaces are the documented exception, in the layout rules below.

## 5. Shape, spacing, elevation, layout

- **Radius:** soft and round, never bubbly, never sharp. Cards, panels, buttons, and fields use the shared radius scale; pills and the nav marker are fully round.
- **Spacing:** generous, on Tailwind's scale. Whitespace is a feature, not waste. Do not introduce a bespoke pixel value to land between two steps.
- **Elevation: borders first, shadow second.** A card is a hairline border on a raised fill. Exactly one soft elevation is reserved for things that genuinely float: dialogs, the overflow-menu popover, and the expanded preview. Nothing else in the app carries a shadow beyond the buttons' hairline.
- **Dividers:** one treatment. Dense list rows are separated by a fainter mix of the border color, never the full-strength border. The full-strength row divider is extinct; do not reintroduce it. Copy the divide utility from an existing list rather than choosing a strength.
- **Scrims** are the espresso ink at low opacity, never pure black, which reads cold against a warm ground.
- **Width has three cases, not two.** A single-column reading view takes the shared reading measure. A *working* surface that is wider than a reading column takes a wider scale cap and records why in its own doc block, because at the call site a cap is otherwise indistinguishable from drift: the profile hub is a two-column card grid, and the source detail is three columns. The resume editor takes the full width the shell gives it, because the form and the paper it renders to have to sit side by side. The page gutter belongs to the app shell for every view it mounts, never to such a view; the chrome-free views outside the shell own their whole frame.

## 6. Iconography and motion

- **Icons:** lucide, one consistent stroke, never emoji. An icon inherits the adjacent text's color (muted in quiet contexts, ink or coral in active ones) and is `aria-hidden`, so the label beside it carries the meaning.
- **No icon rail.** The sidebar is labels only. There are no per-item icons and no collapsed icon rail, and none should be added without deciding the whole nav's register at once.
- **Motion:** minimal and quick. Short entrance and hover transitions, no bounce, no parallax. Always honor `prefers-reduced-motion`: the base stylesheet neutralizes animation and transition when it is requested, so a component needs no media query of its own.

## 7. Components (intent)

This section is the intent, not the markup. Only one primitive is vendored shadcn/ui, the button. Everything else is a hand-rolled Floresu component on the same tokens, so each new component needs individual attention: there is no component library that styles itself. Match the nearest existing sibling.

- **Buttons.** Default is the coral fill with a cream label, the accent-forward call to action. Secondary and outline are quiet neutrals. Ghost is transparent, for row-level and toolbar actions. Destructive is the crimson fill. Link is coral text on a real anchor.
- **One primary action per page surface.** The same action may recur, and the public page does exactly that: its one primary action appears in the header, the hero, and the closing band. What the rule forbids is a *second, competing* primary. A dialog's confirm is exempt, because a closed dialog renders nothing at all.
- **Dialog secondaries follow one three-shape taxonomy**, applied without exception across every dialog in the app: a lone dismissing action with no primary beside it takes outline; a dismiss that itself discards the user's work takes outline, because discarding is a consequence; a consequence-free cancel sitting beside a consequential primary takes ghost.
- **Destructive controls have three shapes.** In a list, a row-level destructive action is the crimson **ghost**: ink and a hover tint, never a fill, because a filled crimson block on every row would put the loudest treatment in the app in its densest list. Within that list's flow, only the **committing** step takes the crimson fill. The third shape is a panel whose whole subject *is* the destructive action, such as the account-delete panel: its single button takes the fill even though it opens the gate rather than committing, because there is no other action on that surface for it to shout over. The ghost is not an accessibility concession: it measures 6.42:1 against the fill's 6.11:1. Every destructive control carries a glyph and a word as well as the hue, and every one is gated.
- **Gates scale with reversibility.** A modal gate is reserved for **irreversible** actions, and an irreversible confirm is an alert dialog with an explicit gate (a typed phrase or a checked acknowledgement) and no dismiss-on-backdrop. A **reversible** destructive action, such as a soft archive that the user can restore, takes a lighter in-place gate where the control lives. Do not put a "cannot be undone" dialog in front of something that can.
- **Cards and panels.** A raised fill, a hairline border, generous padding, and a title in ink. One shared panel frame per family rather than a copied class string.
- **Fields.** One field shape and one label register, defined once and imported. See `docs/frontend.md` for why the shape is an exported constant.
- **Tags and chips.** A tag is a hued pill that always renders its label text. Skill chips are neutral. An active filter chip takes the accent tint with the accent ink, which is the loud register used as punctuation; an inactive one is a bordered paper pill with muted ink.
- **Badges.** Status and visibility read by shape and word, with the hue as reinforcement.
- **Progress.** Ink, not coral. Progress is orientation rather than an action, so the accent is spent on the step's own primary control instead of the indicator, and the position is always stated in words as well as by the fill.
- **Empty states.** The one place serif and warmth belong: one display line, a quiet sub-line, and at most one primary action. Do not repeat a header's action in the empty state beneath it.

## 8. Accessibility

- **Never encode meaning by color alone.** Every hue in the app is paired, per feature: a connected agent pairs the olive dot with the word "Connected"; a finalized resume and a submitted application pair the olive tint with the word; the default identity variant pairs a star glyph with the word "Default"; a warning prompt pairs the ochre tint with the sentence that explains it; a destructive control pairs crimson with a glyph and a label; an error pairs crimson with `role="alert"` and the message text; the live feed pairs the bloom dot with the word "live"; the active nav item pairs the accent fill and the bloom marker with `aria-current`; the wizard's progress pairs the segment fill with "Step X of N"; a tag always renders its label; and an avatar always has the actor's name beside it.
- **Contrast.** The measured posture is the contrast table above. Two rules carry most of it: anything on an accent fill takes the accent ink, and a tinted panel carries full ink rather than its own hue.
- **Focus.** An always-visible focus ring in the bloom coral, with an offset, supplied by the base stylesheet for anything a component does not style itself. Never remove an outline without replacing it with a visible ring.
- **Motion.** Honor `prefers-reduced-motion`, as the motion rule above requires.
- **Landmarks and headings.** Headings nest: a view's title is its top-level heading and its section titles sit beneath it. Do not add a named landmark per panel; six named regions on one screen is noise, not structure.

## 9. Extending this language

This language is deliberately small; that is the point. Before adding a token, a hue, or a component variant:

1. Justify it against the five principles above, and prefer removing over adding.
2. Add token *values* to `frontend/src/theme/tokens.css` only. Document the new *rule* here, without restating the value. `globals.css` maps tokens onto Tailwind and never defines one.
3. The tag palette order and the hash are a frozen contract. Extend deliberately, never reorder.
4. If a value must be duplicated because a consumer cannot read a CSS custom property, signpost it in both directions so neither copy can move alone. The favicon placeholder is the only such copy today.

**Dark mode is deliberately absent.** There is no toggle, no `prefers-color-scheme` query, and no dark scope anywhere in the emitted stylesheet. When dark mode is added later, it redefines the same token variables under a dark scope: a warm charcoal ground, cream ink, the coral held roughly constant, and the tag hues lifted in lightness. Do not introduce dark-mode tokens before then, and do not add a `dark:` variant to a component in the meantime.

## Cross-references

- Frontend architecture, the theme file layout, and the view conventions: `docs/frontend.md`.
- Component and view source: `frontend/src/components/`, `frontend/src/views/`.
- Test layers and the coverage floors: `docs/testing.md`.
