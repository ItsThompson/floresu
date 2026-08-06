# Frontend

The Floresu frontend is a React single-page app built with Vite. It serves human users and talks to the backend's external app over a generated, typed REST client. This guide describes the theme layer, the route shape and its guards, the tag-color contract, and the view and component conventions. It documents the current implemented state.

See `docs/design-language.md` for the look-and-feel rules and the measured contrast posture, `docs/api.md` for the REST surface and the error contract, `docs/auth.md` for the session model, and `docs/development.md` for commands and the environment-variable groups.

Canonical sources:

- Entry point and the fixed stylesheet import order: `frontend/src/main.tsx`
- Provider composition: `frontend/src/App.tsx`
- Route tree and guards: `frontend/src/routes.tsx`, `frontend/src/components/RequireAuth.tsx`, `frontend/src/components/RequireOnboarded.tsx`, `frontend/src/components/AppShell.tsx`
- Theme: `frontend/src/theme/tokens.css`, `frontend/src/theme/fonts.css`, `frontend/src/globals.css`
- Tag color: `frontend/src/lib/colorForName/`, `frontend/src/lib/hueTint/`
- Shared components: `frontend/src/components/`
- Views: `frontend/src/views/`
- Session and typed clients: `frontend/src/auth/`, `frontend/src/api/`
- Dev mocks and the test harness: `frontend/src/mocks/`, `frontend/src/test/`

## The theme layer

Three files, and the split is a division of ownership rather than a preference.

| File | Owns | Must never |
|------|------|-----------|
| `theme/tokens.css` | Every design *value*, oklch canonical. The only file in the repo where a color, radius, or font stack is defined | Import Tailwind or use `@theme`, `@layer`, or any framework syntax |
| `theme/fonts.css` | The three self-hosted variable `@font-face` rules, Latin subset | Reach a font CDN |
| `globals.css` | The Tailwind bridge, the base style, and the display, caption, metadata, and layout utilities | Define a value. It maps tokens; it never declares one |

`tokens.css` stays framework-neutral so the bridge can stay a pure mapping. Two naming details in it exist for the bridge's sake and look arbitrary otherwise: the font stacks and the reserved elevation sit in their own `--font-*-stack` and `--elevation-*` namespace, outside Tailwind's own `--font-*` and `--shadow-*` theme namespaces, because the bridge aliases them (`--font-sans: var(--font-sans-stack)`) and an alias to an identically named variable would be a self-reference cycle.

Fonts are self-hosted, not loaded from a CDN. Self-hosting keeps a career tracker free of a third-party request, keeps the app correct offline, and lets the preview server that the end-to-end suite boots work with no network access. The font packages are direct dependencies of `frontend/package.json`, and the bare package specifiers in the `url()` rules resolve through Vite's asset pipeline.

### The fixed import order

`main.tsx` imports the three stylesheets in one fixed order: fonts, then tokens, then the bridge. Keep it.

The reason is worth writing down because **it is not derivable from the CSS**. Today the order is not load-bearing: `globals.css` uses `@theme inline`, which inlines its `var()` references, so token resolution happens at computed-value time and does not depend on cascade position. Drop the `inline` keyword and the order becomes load-bearing immediately, because the bridge would then need the tokens to be already declared when it is processed. A contributor who "simplifies" `@theme inline` to `@theme` and reorders the imports in the same change would produce a silently unstyled app. `main.tsx` is also the only module in the tree that imports CSS, so nothing else can pull a stylesheet ahead of these three.

### Utilities the bridge owns

`globals.css` defines the type and layout utilities so no view hardcodes a size: three display steps for serif moments, a caption step, a metadata step, a tag step, and the shared reading measure. Use these names rather than a Tailwind `text-*` step where one exists, and never inline an arbitrary bracket size to land between two steps. The caption step in particular exists as a utility precisely because it sits between two Tailwind steps.

### The one duplicated value

`frontend/public/favicon.svg` spells out the bright coral literally. A static SVG cannot read a CSS custom property, so this is the only copy of a token value in the repo. Both sides signpost each other: the token carries a note naming the SVG, and the SVG carries a note explaining why it holds a literal. An edit to either must be applied to the other.

### No dark mode

There is no toggle, no `prefers-color-scheme` query, and no dark scope in the emitted stylesheet. Do not add a `dark:` variant to a component. The forward path is recorded in `docs/design-language.md`: dark mode redefines the same token variables under a dark scope, and no dark-mode token should be introduced before then.

## Tag color: a frozen contract

Tag and identity color is a domain truth, not a per-view choice, so it lives in one module and is never re-derived.

- `lib/colorForName/` hashes a label into a palette **position**. The hash is frozen: it is stable and order-sensitive over the string's code points. Do not change it.
- The ten hues themselves live in `theme/tokens.css` as the tag palette. The module returns a variable reference, so no color value lives in TypeScript.
- **The palette order is a frozen cross-view contract.** Entry *N* in the module maps to tag token *N*, and the hash picks by position, so reordering the palette repaints every tag and avatar that already exists.
- A hashed hue is a ten-way bucket, so two different labels can collide on one entry. A test that asserts two labels render in *different* colors is resting on that, and must be re-checked whenever either label changes. The end-to-end tag spec records this at its label constants.
- `lib/hueTint/` centralizes the mixing. It returns the fill and the ink for one hue, both mixed from that single hue, so they cannot drift apart. A caller declares only its **fill strength**, which varies by surface; the **ink strength is fixed** inside the helper, along with the two mix bases and the mixing space.
- Skills are never hash-colored. `SkillsView` and the profile hub import neither the hash nor the tint helper, by rule; see `docs/design-language.md` for why.

One known soft edge: the tint helper's hue parameter is typed as `string`, so a hex literal could enter TypeScript at that one boundary and quietly defeat the values-live-in-tokens rule. Typing the parameter and the hash's return with the palette tuple's element type would make the constraint checkable by `tsc`.

## Route shape and guards

`routes.tsx` holds the route tree and is deliberately separate from `App.tsx`, which composes providers only, so a routing test can assert the structural invariants without rendering a view. `App.tsx` reads the API base once at the root and hands it to the provider in `frontend/src/api/ApiClientContext.tsx`, which owns the binding: one credentialed client and one credential-free client per base, memoized on it, so a single token refresh coalesces concurrent 401s across every consumer. See `docs/auth.md` for the session model.

| Path | View | Gating |
|------|------|--------|
| `/` | `LandingView` | **Public, outside every guard.** Served to signed-in visitors too; its header carries them back into the app |
| `/signin`, `/signup` | `AuthView` | Public, chrome-free |
| `/onboarding` | `OnboardingView` | Inside `RequireAuth`, outside the app shell (chrome-free wizard) |
| `/authorize` | `ConsentView` | Inside `RequireAuth`, outside `RequireOnboarded`, so a connect-time consent is never bounced into the wizard |
| `/home`, `/worklog`, `/library`, `/resumes`, `/resumes/:resumeId`, `/applications`, `/profile` and its children, `/settings` and its children | the in-app views | Inside `RequireAuth`, then `RequireOnboarded`, then `AppShell` |

Two invariants a contributor can silently break:

**The app shell is a pathless layout route.** It claims no path of its own and declares no index route. This matters: a shell that kept `path: "/"` alongside the public route would contribute a *second* branch matching the root. The two score identically, and the tie falls through to array order, so which one renders would be decided by list position rather than by intent, and the loser would linger as a live branch that can never win a URL. Keeping the shell pathless removes the branch entirely, and the child paths resolve the same either way.

**The app's Home is `/home`, and nothing may assume the root is Home.** Any in-app fallback destination points at `/home`. The subtle case is a fallback that only asserts "this route exists": the root still exists, so such a test keeps passing while a signed-in user is ejected to the marketing page. Assert the *guards a destination sits behind*, not merely that it resolves; `frontend/src/test/routeComponents.ts` exists for that.

The public page's primary action resolves its destination from the session, and Floresu has **three** states rather than two: anonymous goes to signup, signed in but not onboarded goes back to the wizard, and signed in and onboarded goes to the app. The resolver takes a session type in which "still loading" is unrepresentable, and the hook gates it, so the control renders disabled rather than briefly pointing a returning visitor at signup.

## View conventions

A view is one route target and a **thin orchestrator**: it reads route params and session, calls one data hook, and routes the phase states (loading, error, empty, loaded). Presentation lives in its `components/`.

The per-view file layout, which every view follows:

| Path | Holds |
|------|-------|
| `<View>.tsx` | The orchestrator, and nothing else |
| `components/` | One presentational component per file |
| `hooks/` | The data hooks: one per read-and-write surface |
| `constants.ts` | Copy, labels, and shared class strings for the view |
| `types.ts` | The view's own shapes |
| `test-support/` | Fixtures and API stubs shared by the view's tests |

Standing rules:

- **One component per `.tsx` file**, and source files stay under 300 lines. Decompose rather than grow a file.
- **Match the nearest existing sibling.** A new view, component, or hook should look like the closest one that already exists, down to the file layout and the prop-interface placement.
- **Copy is data, not JSX.** The public page keeps every visitor-facing string in its `constants.ts` behind a type, so a copy edit never touches a component. In-app views keep their labels and messages in `constants.ts` for the same reason.
- **The app shell owns the page gutter** for every view it mounts. Such a view adds no page padding of its own; it declares only its measure. A chrome-free view outside the shell owns its whole frame, padding included, because no shell mounts it: the public page, auth, the onboarding wizard, and consent are the four. Width has three cases: a single-column reading view takes the shared reading measure; a wider *working* surface takes a wider scale cap and states its reason in its own doc block; the resume editor runs full width. `AppShell`'s own doc block currently enumerates two of the three.
- **Environment is read at a root, never in a leaf.** A presentational component reads no `import.meta.env`; the value is resolved once and threaded down as a prop.

### The shared field shape

Every field in the app takes one shape, so the class list is defined once in `components/FormInputField/constants.ts` and **exported** rather than kept private. The export exists because no labeled-field component can wrap every control that needs the shape: a native `<select>`, and a dense field whose accessible name comes from `aria-label` rather than a visible label, both need the shape without the wrapper.

Two wrappers consume it as their whole shape: `FormInputField` for a single-line value and `FormTextareaField` for a multi-line one. Beyond those, a view-level control that neither wrapper can wrap imports the constant directly, which is the point of exporting it; `views/ResumeEditorView/components/TemplateSelect.tsx` is the `<select>` case. The constant carries no height, width, or padding, so every caller sets its own density.

Import the constant; never restate it. The part a restatement loses first is the invalid-border pairing, and a field that quietly stops marking itself invalid is not something the build can catch. **Seventeen sites still restate the shape** rather than importing it, and all seventeen are missing that pairing. That is a standing sweep, not a pattern to copy: `grep -rn "border-input" frontend/src` enumerates them, less the constant itself and four controls that are not fields (a read-only display field, two filter chips, and a toggle).

### Shared versus view-local components

`frontend/src/components/` holds what more than one view needs, or what is one domain concept rendered in more than one place: the app shell and sidebar, the route guards, the avatars, the tag pill, the ranked search results, the shared modal, the field components, and the MCP URL field are all there for one of those two reasons. Everything else lives in the owning view's `components/`.

The test that decides where something goes is domain, not reuse count. A tag pill and a search result list are one concept each, so two divergent copies of either are a defect even while both work: promote it and style it once. A card frame copied across one view's own panels is the opposite case, and belongs to that view.

`components/ui/` is the one vendored directory. It holds a single shadcn/ui primitive, the button, and it is excluded from coverage. Do not hand-edit it; wrap it, or set the token it reads.

## Environment variables

The frontend reads three build-time variables. `frontend/src/vite-env.d.ts` types them and `docs/development.md` documents the group, its defaults, and how a deployment supplies them. What matters here is where each is read and what an unset value does:

| Variable | Read at | Unset |
|----------|---------|-------|
| `VITE_API_BASE_URL` | the `App` root, once | Same-origin, which the dev proxy and the mock worker both rely on |
| `VITE_MCP_URL` | `frontend/src/lib/mcpUrl.ts` | **Falls back to the production endpoint.** A local dev box therefore shows a production URL on the connect-agent step. That is the default, not a defect |
| `VITE_MOCK_API` | `main.tsx` | The mock worker does not start |

Vite reads env files from `frontend/`, not from the repo root, so the root `.env` does not feed these. A container build passes them as build arguments.

## Dev mocks and testing

`frontend/src/mocks/` holds a Mock Service Worker harness that serves the app with no backend; `main.tsx` starts it only when the mock flag is set. `frontend/src/test/` holds the shared render harness, which mounts the full provider stack, and the route-resolution helper described above. vitest enforces the frontend coverage floor. See `docs/testing.md` for the layers and the floors.

## Cross-references

- Look-and-feel rules, the accent placement map, and the contrast posture: `docs/design-language.md`.
- The REST surface, the generated client, and the error contract: `docs/api.md`.
- The session model and the OAuth consent flow: `docs/auth.md`.
- Commands, environment groups, and codegen: `docs/development.md`.
- Test layers and coverage floors: `docs/testing.md`.
