---
name: 5X49 Cinema OS
version: 1.0.0
status: draft
colorMode: dark-only
colors:
  canvas: '#000000'
  surface: '#0a0a0a'
  surface-raised: '#171717'
  surface-hover: '#262626'
  ink: '#ffffff'
  ink-muted: '#a3a3a3'
  ink-subtle: '#737373'
  ink-disabled: '#525252'
  line: '#171717'
  line-strong: '#404040'
  inverse: '#ffffff'
  inverse-ink: '#000000'
  success: '#34d399'
  warning: '#fcd34d'
  danger: '#f87171'
  scrim: 'rgba(0, 0, 0, 0.75)'
  glass: 'rgba(8, 8, 8, 0.42)'
typography:
  display-ui:
    fontFamily: Inter
    fontSize: 'clamp(40px, 6vw, 72px)'
    fontWeight: '700'
    lineHeight: '0.95'
    letterSpacing: '-0.025em'
    textTransform: uppercase
  display-editorial:
    fontFamily: Playfair Display
    fontSize: 'clamp(60px, 9vw, 128px)'
    fontWeight: '400'
    lineHeight: '0.9'
    letterSpacing: '-0.04em'
  display-film-title:
    fontFamily: Inter
    fontSize: 'clamp(60px, 9vw, 128px)'
    fontWeight: '700'
    lineHeight: '0.9'
    letterSpacing: '-0.04em'
    textTransform: uppercase
  section-title:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: '-0.02em'
    textTransform: uppercase
  card-title:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '800'
    lineHeight: 28px
    letterSpacing: '-0.02em'
  editorial-lead:
    fontFamily: Playfair Display
    fontSize: 'clamp(20px, 2vw, 24px)'
    fontWeight: '400'
    lineHeight: '1.4'
    fontStyle: italic
  body:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: '0'
  label:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: '0.15em'
    textTransform: uppercase
  meta:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: '0.15em'
    textTransform: uppercase
  badge:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '900'
    lineHeight: 10px
    letterSpacing: '0.08em'
    textTransform: uppercase
  mono:
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace'
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: '0.02em'
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
  4xl: 96px
  page-x: 'clamp(24px, 5vw, 64px)'
  page-y: 'clamp(64px, 8vw, 96px)'
  section-gap: 64px
  editorial-gap: 96px
borders:
  hairline: 1px
  emphasis: 2px
  focus-ring: 2px
radii:
  structural: 0px
  small: 2px
  control: 4px
  media: 6px
  pill: 9999px
motion:
  fast: 100ms
  standard: 150ms
  deliberate: 300ms
  inspection-delay: 500ms
  ease-standard: 'cubic-bezier(0.2, 0, 0, 1)'
  ease-enter: 'cubic-bezier(0, 0, 0.2, 1)'
  ease-exit: 'cubic-bezier(0.4, 0, 1, 1)'
layers:
  content: 0
  raised: 10
  sticky: 20
  inspector: 30
  overlay: 40
  navigation: 50
  popover: 60
  modal: 70
  toast: 80
glass:
  surface-blur: 3px
  overlay-blur: 12px
  saturation: '170%'
  contrast: '106%'
  grain-opacity: '0.045'
---

# 5X49 Cinema OS Design System

## 1. Purpose and source of truth

This document defines the human-readable visual and interaction contract for 5X49. It records intent, usage rules, and component behavior. It is not itself a runtime token source.

Runtime values should live in `frontend/src/styles/tokens.css` and be exposed through Tailwind CSS 4 theme variables and a small set of semantic utilities. When this document and the runtime tokens disagree, the discrepancy must be resolved deliberately; neither side should drift silently.

The first token migration must preserve the currently approved appearance. Tokenization is not authorization to redesign existing screens.

## 2. Brand and visual principles

5X49 uses an A24-inspired editorial cinema aesthetic for an archival film knowledge engine. The personality is disciplined, moody, precise, and architectural. Film imagery and typography carry the visual emphasis; application chrome remains restrained.

Core principles:

- **Extreme contrast:** pure white on absolute black for primary hierarchy.
- **Editorial scale:** large titles behave like poster typography, not dashboard headings.
- **Precision:** hairline dividers, aligned baselines, and deliberate grids organize information.
- **Restrained depth:** tonal surfaces and glass are reserved for overlays and inspectors.
- **Content first:** artwork, titles, genealogy, and metadata remain more prominent than controls.
- **Square by default:** structural UI is sharp; rounding communicates a specific component role.

## 3. Token architecture

Tokens are organized in three layers:

1. **Primitive values** — the Tailwind neutral palette and fixed measurements.
2. **Semantic tokens** — roles such as `canvas`, `ink-muted`, `line`, `danger`, and `modal`.
3. **Component rules** — Button, Input, Movie Card, Popover, and other component contracts.

New and migrated UI should consume semantic roles instead of choosing raw greys independently. Component-specific tokens should be introduced only when a component genuinely needs independent control; page-specific aliases are discouraged.

## 4. Color

The palette is monochromatic. Color is functional rather than decorative.

### Surfaces

- `canvas` is the application background and remains absolute black.
- `surface` is the quietest raised plane used for low-contrast content regions.
- `surface-raised` is used for inputs, inspectors, and inactive controls.
- `surface-hover` is reserved for hover and selected-state transitions.
- Glass surfaces use the dedicated treatment in the Elevation section rather than an opaque grey.

### Text

- `ink` is primary text and high-contrast action text.
- `ink-muted` is readable secondary information.
- `ink-subtle` is supporting metadata and descriptions.
- `ink-disabled` is used only for unavailable controls and roadmap content.

Do not use low-contrast text for information required to understand or complete an action.

### Lines and inverse controls

- `line` is the default hairline divider.
- `line-strong` identifies controls and emphasized boundaries.
- `inverse` and `inverse-ink` produce the signature white-on-black inversion for selected navigation and primary actions.

### Functional color

- `success` communicates completed and healthy states.
- `warning` communicates partial, review-required, or confirmation-required states.
- `danger` communicates failed and destructive states.
- Functional colors should not become decorative accents.

Gold is not currently a core brand token. Ratings and favorites remain monochromatic unless a separate product decision introduces a dedicated accent color.

## 5. Typography

Inter carries structural information, navigation, controls, and technical metadata. Playfair Display adds editorial contrast for library titles, chronology, quotations, release years, and narrative moments.

### Display roles

- `display-ui` is used by Settings, Library Management, and other system-level pages.
- `display-editorial` is used by the Library, Activity, and archive-like editorial headings.
- `display-film-title` is used for individual film hero titles.
- Display text must wrap safely on narrow screens. Long words may reduce to the lower bound of the scale or use `overflow-wrap` rather than forcing horizontal page overflow.

### Content roles

- `section-title` introduces a major section.
- `card-title` names a film or substantial content card.
- `editorial-lead` is serif and italic; it is not a replacement for ordinary body text.
- `body` is the default explanatory and form-description style.
- `label`, `meta`, and `badge` are uppercase roles with intentionally wider tracking.
- `mono` uses the system monospace stack for Librarian and diagnostic output. JetBrains Mono is not required unless it is explicitly added to the application font dependencies.

Avoid constructing the same typography role repeatedly from unrelated font-size, weight, line-height, tracking, and uppercase classes. Prefer composite semantic utilities such as `type-display-ui`, `type-section-title`, and `type-label`.

## 6. Spacing and layout

The smallest spacing unit is 4px. The dominant visual rhythm uses multiples of 8px; 24px, 48px, 64px, and 96px create page and editorial separation.

- Page horizontal framing uses `page-x`, fluid from 24px to 64px.
- Standard major sections use a 64px gap.
- Full editorial transitions may use a 96px gap.
- Control internals may continue using the numeric Tailwind spacing scale.
- Do not create semantic names for every 4px increment. Semantic spacing is reserved for page framing and repeated layout relationships.

### Grid behavior

There is no requirement that every page use a global 12-column grid.

- Editorial compositions may use a 12-column layout.
- Film libraries use responsive content grids that grow from 1 column to as many as 5 columns when card width permits.
- Technical and settings views use single-column reading widths, two-column action groups, and divider rows.
- Content grids must be defined by minimum readable component width, not by a fixed desktop screenshot.

## 7. Borders and shapes

Hairline borders are the default structural device. Shadows should not replace dividers in ordinary content.

Shape roles:

- `structural` — page sections, settings rows, danger zones, hero actions, and terminal windows.
- `small` — compact labels and connected surfaces where a minimal edge softening is needed.
- `control` — ordinary inputs and compact controls.
- `media` — movie artwork and media containers.
- `pill` — watched/favorite controls, status chips, and tag-like metadata.

Do not select radii based on visual preference alone. A component role determines its radius.

Keyboard focus uses a visible 2px `ink` outline with sufficient offset from the control. Focus visibility must not rely on a color change alone.

## 8. Elevation and Liquid Glass

Depth is conveyed through tonal layering and glass, not conventional card shadows.

### Standard glass surface

- Background: `rgba(8, 8, 8, 0.42)` with a restrained diagonal light gradient.
- Backdrop blur: 3px.
- Saturation: 170%.
- Contrast: 106%.
- Grain: SVG fractal noise at 0.045 opacity.
- Shadow: `0 18px 60px rgba(0, 0, 0, 0.58)` only when separation from the canvas is required.

Use standard glass for dropdowns, inspector sheets, sidebars, and modal panels.

### Overlay backdrop

The scrim behind a modal or sidebar may use up to 12px blur. The 12px value applies to the backdrop layer, not to every glass panel.

Glass should not be applied to ordinary settings rows, maintenance actions, or static cards. Excessive glass weakens the archival visual hierarchy.

## 9. Interaction states

All interactive components must define the following states where applicable:

- **Default:** neutral surface and readable label.
- **Hover:** raise the text, line, or surface by one semantic level.
- **Focus visible:** show the standard focus outline; keyboard focus must never be hidden.
- **Active/selected:** use inverse treatment or a clearly stronger line.
- **Disabled:** disable interaction and render at approximately 40–50% opacity.
- **Busy:** preserve button dimensions, disable repeated activation, and show a consistent spinner or progress label.
- **Success:** announce through `aria-live` and disappear after approximately 3 seconds for configuration saves.
- **Warning:** remain until the condition has been reviewed or resolved.
- **Error:** remain until the next operation or explicit dismissal.
- **Destructive:** use danger text and borders; avoid a large solid-red surface by default.

Errors, warnings, and successes must not be communicated through color alone. Include text and, when useful, an icon.

## 10. Motion

Motion is functional, restrained, and quick.

- `fast` is used for simple hover and color transitions.
- `standard` is used for switches, tabs, dropdowns, and small transforms.
- `deliberate` is used for sidebars, modals, and page-scale transitions.
- `inspection-delay` is reserved for the desktop movie-card inspector so incidental pointer movement does not open it immediately.

Avoid spring-heavy motion, bouncing, or decorative continuous animation. Loading spinners are exempt while work is running.

When `prefers-reduced-motion: reduce` is active:

- Remove non-essential translation, scale, and parallax effects.
- Remove the movie-card inspection delay.
- Shorten state changes to near-instant transitions.
- Preserve visibility and loading feedback.

## 11. Layering

Use the named layer scale instead of introducing arbitrary `z-index` values:

- `content` — normal document flow.
- `raised` — local media and controls.
- `sticky` — sticky page navigation and local headers.
- `inspector` — movie-card hover inspectors.
- `overlay` — page scrims.
- `navigation` — global sidebar and app chrome.
- `popover` — dropdowns and contextual panels above navigation content.
- `modal` — blocking dialogs and full-screen consoles.
- `toast` — transient feedback above all application surfaces.

A child component must not escalate above `modal` to solve a local clipping problem. Fix the containing block or portal boundary instead.

## 12. Responsive behavior

- Mobile layouts begin with a single readable column.
- Settings navigation becomes a horizontally scrollable tab row without causing document-level horizontal overflow.
- Buttons may become full width on mobile and intrinsic width on larger screens.
- Long paths, model names, errors, and translated labels must wrap or truncate within their containers.
- Hover-only information must remain reachable on coarse pointers and touch devices.
- Display typography must use its responsive lower bound before breaking words.
- A 375px viewport is the minimum acceptance viewport for primary application screens.

## 13. Component contracts

### Buttons

**Primary**

- Inverse background and inverse text.
- Uppercase label with label tracking.
- Structural or control radius according to context.
- Uses `fast` color transitions.

**Secondary**

- Transparent or raised surface.
- 1px `line-strong` border.
- Ink text; border and surface strengthen on hover.

**Danger**

- Transparent or restrained danger surface.
- Danger border and text.
- Requires explicit confirmation for destructive data operations.

All important controls should provide an approximately 44px minimum interaction height.

### Input fields

- Raised dark surface with a 1px strong line.
- Ink text and subtle placeholder.
- Visible focus outline or pure-white focus border.
- Invalid state includes danger text in a persistent feedback region.
- Explicit-save text fields disable Save until the value is valid and changed.

### Movie cards

- Primary landscape media uses a 16:9 ratio.
- Media radius is 6px; technical badges use a 4px role and state controls use pills.
- On fine pointers, media may scale to 1.05 after the 500ms inspection delay.
- The inspector sheet appears below the media using the standard glass treatment.
- On touch and coarse pointers, all essential actions and metadata must remain reachable without hover.

### Metadata badges

- Solid badges identify primary technical specifications such as resolution.
- Ghost badges identify secondary codecs and technical metadata.
- Badge type, contrast, and outline communicate hierarchy; badge colors remain monochromatic unless they represent a functional state.

### Settings rows

- Use title, description, control, and a stable feedback region.
- Separate rows with hairline dividers instead of wrapping each row in a card.
- Immediate controls save on selection; text configuration uses explicit Save.

### Popovers, sidebars, and modals

- Use semantic layers and the standard glass surface.
- Scrims use the overlay backdrop treatment.
- Keyboard focus remains trapped in blocking modals and returns to the trigger on close.
- Escape closes non-destructive overlays when safe.

### Librarian console

- Uses the system monospace role.
- Standard glass belongs to the panel; the stronger blur belongs to the backdrop.
- Logs use ink hierarchy and functional state colors.
- Reasoning paths and long output wrap without forcing page overflow.

## 14. Accessibility requirements

- Primary text and actionable controls must meet WCAG AA contrast.
- Focus-visible treatment is mandatory for keyboard-operated controls.
- Interactive controls require accessible names.
- Status and mutation feedback use an appropriate `aria-live` region.
- Color is never the only error, warning, selected, or success signal.
- Motion respects `prefers-reduced-motion`.
- Text must remain readable at 200% zoom without horizontal document scrolling for primary flows.
- Disabled roadmap content must not appear interactive.

## 15. Tailwind CSS 4 implementation mapping

Use `@theme` for values that should create Tailwind utility classes:

- `--color-*`
- `--font-*`
- `--text-*`
- `--tracking-*`
- `--leading-*`
- `--spacing-*`
- `--radius-*`
- `--shadow-*`
- `--ease-*`
- `--animate-*`

Use ordinary `:root` variables for glass internals, state timing, and application layers when no generated utility is needed. Add a small semantic utility only when repeated composition is necessary, such as `type-display-ui`, `glass-surface`, `z-modal`, or `focus-ring`.

Do not remove Tailwind's default scale during the first migration. Numeric utilities remain appropriate for local component layout; semantic tokens are required for cross-page visual decisions.

## 16. Governance

- New tokens require a demonstrated repeated use case.
- New pages should reuse semantic roles before introducing raw values.
- Existing pages migrate incrementally; broad formatting-only rewrites are avoided.
- Token migration should produce no intentional visual change unless the change is separately reviewed.
- Exceptions are documented near the component and reviewed before becoming new global rules.
- The design-system document and runtime token file are reviewed together when a shared visual rule changes.

