---
name: ui-ux-pro-max
description: >-
  Use for frontend UI/UX design, redesign, polish, product console
  implementation, SaaS/operator interfaces, React/Tailwind implementation,
  visual review, and when the user asks for UI UMAX, UI/UX Pro Max, AI Studio
  visual migration, or non-document-style product UI. For this repo, use before
  editing Owner Console or Trading Console screens, especially Action Entry,
  ActionCandidate review, budget/authorization, FinalGate, blocker/warning,
  position/protection, and Review Ledger flows. Follow the BRC product
  principles: the console is an Owner bounded-live operations surface, not a
  read-only dashboard, documentation page, code explanation, raw JSON viewer, or
  passive report unless the specific artifact is explicitly scoped read-only.
---
# ui-ux-pro-max

## Codex Project Path

This skill is installed at `.codex/skills/ui-ux-pro-max/` in this repository. Run bundled scripts with that path from the repository root:

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system -p "<Project Name>"
```

## BRC Owner Console Project Adaptation

The Owner Console and Trading Console are the Owner's bounded-live operating surfaces. They are not merely read-only dashboards, documentation pages, debug pages, code explanations, PG/read-model browsers, enum displays, or raw API field viewers.

Project authority for this repository:
1. Owner explicit correction, `AGENTS.md`, current tracked code, and current `docs/ops/knowledge-pack/*`.
2. This BRC project adaptation.
3. Existing product UI and Gemini/front-end design baseline.
4. Generic design-system search output from this skill.

Generic design recommendations are supporting input only. They must not override project product semantics, safety boundaries, or the current Owner correction that the console is not a read-only product.

Primary UX goal:
Help the Owner quickly understand:
- current environment and safety state;
- active StrategyFamily / Carrier;
- available next action or why no action is currently available;
- ActionCandidate records and candidate actionability;
- budget availability and authorization state;
- FinalGate preview, required inputs, and gate result;
- hard blockers vs acknowledgeable strategy warnings;
- evidence behind the decision;
- active position / TP/SL protection state when relevant;
- pause, revoke, or recovery controls when relevant;
- post-action evidence and Review Ledger outcomes;
- what will happen after authorization and what remains disabled.

Core rules:
- Use product UI, not Markdown-like report layouts.
- Treat Owner Console and Trading Console as bounded-live operations consoles: when backend action state is wired, expose controlled Operation Layer flows with preflight, confirmation, result, and disabled reasons.
- Do not reduce frontend work to read-only documentation, code explanation, raw JSON display, or passive status reporting unless the specific endpoint/report is explicitly scoped as read-only.
- Do not generalize a GET/read-model namespace into "the console product is read-only"; the UI should still show the official action path, readiness, disabled reasons, and handoff points.
- Do not make source-code explanations, API schemas, markdown reports, or documentation copy the primary screen unless the user explicitly asks for documentation.
- Keep current state and next action visible above technical detail.
- Every candidate/action surface should answer: what can the Owner do now, why is it enabled or disabled, what risk is being accepted, which gate applies, and what evidence/result will be recorded.
- Separate hard blockers from strategy warnings.
- Collapse technical/debug details by default.
- Never hide live/testnet/observe mode.
- Never imply live readiness without explicit Owner live authorization.
- Never bypass or visually imply bypass of ActionCandidate -> Owner/BudgetEnvelope authorization -> ActionSpec -> FinalGate -> Operation Layer -> protection -> Review Ledger.
- Never auto-fill confirmation phrases, fake live execution, or add controls that imply real-funds action without the official backend path and explicit Owner authorization.
- Do not present BNB as the whole architecture; BNB is only the first Carrier.

Domain vocabulary:
- StrategyFamily = strategy logic, no order authority.
- Carrier = StrategyFamily + symbol + side + risk cap.
- ActionCandidate = reviewable proposed action, not direct order authority.
- ActionSpec = official execution intent evaluated by FinalGate.
- FinalGate = final safety gate for the exact action.
- BoundedLiveTrialAuthorization = one-time Owner-confirmed live trial authorization.
- Warning = strategy/evidence/regime risk; Owner may acknowledge.
- Hard Blocker = execution safety issue; cannot be bypassed.

Codex frontend boundary:
Codex may wire API data, types, tests, and small UI components.
Codex must preserve product layout, hierarchy, and Owner decision flow.
Large UI redesign should follow this project adaptation and the existing Gemini/front-end design baseline. If generic design guidance conflicts with project principles, keep the project principles.

Comprehensive design guide for web and mobile applications. Contains 67 styles, 96 color palettes, 57 font pairings, 99 UX guidelines, and 25 chart types across 13 technology stacks. Searchable database with priority-based recommendations.

## Prerequisites

Check if Python is installed:

```bash
python3 --version || python --version
```

If Python is not installed, install it based on user's OS:

**macOS:**
```bash
brew install python3
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install python3
```

**Windows:**
```powershell
winget install Python.Python.3.12
```

---

## How to Use This Skill

When user requests UI/UX work (design, build, create, implement, review, fix, improve), follow this workflow:

### Step 1: Analyze User Requirements

Extract key information from user request:
- **Product type**: SaaS, e-commerce, portfolio, dashboard, landing page, etc.
- **Style keywords**: minimal, playful, professional, elegant, dark mode, etc.
- **Industry**: healthcare, fintech, gaming, education, etc.
- **Stack**: React, Vue, Next.js, or default to `html-tailwind`

For this repository, also identify whether the screen is:
- an Owner/Trading Console action surface;
- a read-model endpoint view supporting an action surface;
- a genuinely read-only evidence/report artifact;
- a debug/developer-only surface.

If it is Owner Console or Trading Console work, map the UI to the product chain before choosing layout details:

```text
StrategyFamily / Carrier
-> ActionCandidate
-> Owner risk understanding
-> Owner authorization or BudgetEnvelope authorization
-> ActionSpec
-> FinalGate
-> Operation Layer
-> official bounded live action
-> active position / TP/SL protection monitoring
-> close / TP / SL
-> Review Ledger
-> promote / revise / park
```

### Step 2: Establish Design Authority

For general projects, use `--design-system` to get comprehensive recommendations with reasoning.

For this repository, first inspect the existing screen patterns and project product rules. Use design-system search only as supplemental guidance for visual polish, chart selection, typography, responsiveness, and accessibility.

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "<product_type> <industry> <keywords>" --design-system [-p "Project Name"]
```

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "bounded live trading operations console fintech risk" --design-system -p "BRC Owner Console"
```

This command:
1. Searches 5 domains in parallel (product, style, color, landing, typography)
2. Applies reasoning rules from `ui-reasoning.csv` to select best matches
3. Returns complete design system: pattern, style, colors, typography, effects
4. Includes anti-patterns to avoid

**Example:**
```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "beauty spa wellness service" --design-system -p "Serenity Spa"
```

### Step 2b: Persist Design System (Master + Overrides Pattern)

To save the design system for hierarchical retrieval across sessions, add `--persist`:

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system --persist -p "Project Name"
```

This creates:
- `design-system/MASTER.md` — Global Source of Truth with all design rules
- `design-system/pages/` — Folder for page-specific overrides

**With page-specific override:**
```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system --persist -p "Project Name" --page "dashboard"
```

This also creates:
- `design-system/pages/dashboard.md` — Page-specific deviations from Master

**How hierarchical retrieval works:**
1. When building a specific page (e.g., "Checkout"), first check `design-system/pages/checkout.md`
2. If the page file exists, its rules **override** the Master file
3. If not, use `design-system/MASTER.md` exclusively

### Step 3: Supplement with Detailed Searches (as needed)

After getting the design system, use domain searches to get additional details:

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "<keyword>" --domain <domain> [-n <max_results>]
```

**When to use detailed searches:**

| Need | Domain | Example |
|------|--------|---------|
| More style options | `style` | `--domain style "glassmorphism dark"` |
| Chart recommendations | `chart` | `--domain chart "real-time dashboard"` |
| UX best practices | `ux` | `--domain ux "animation accessibility"` |
| Alternative fonts | `typography` | `--domain typography "elegant luxury"` |
| Landing structure | `landing` | `--domain landing "hero social-proof"` |

### Step 4: Stack Guidelines (Default: html-tailwind)

Get implementation-specific best practices. If user doesn't specify a stack, **default to `html-tailwind`**.

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "<keyword>" --stack html-tailwind
```

Available stacks: `html-tailwind`, `react`, `nextjs`, `vue`, `svelte`, `swiftui`, `react-native`, `flutter`, `shadcn`, `jetpack-compose`

---

## Search Reference

### Available Domains

| Domain | Use For | Example Keywords |
|--------|---------|------------------|
| `product` | Product type recommendations | SaaS, e-commerce, portfolio, healthcare, beauty, service |
| `style` | UI styles, colors, effects | glassmorphism, minimalism, dark mode, brutalism |
| `typography` | Font pairings, Google Fonts | elegant, playful, professional, modern |
| `color` | Color palettes by product type | saas, ecommerce, healthcare, beauty, fintech, service |
| `landing` | Page structure, CTA strategies | hero, hero-centric, testimonial, pricing, social-proof |
| `chart` | Chart types, library recommendations | trend, comparison, timeline, funnel, pie |
| `ux` | Best practices, anti-patterns | animation, accessibility, z-index, loading |
| `react` | React/Next.js performance | waterfall, bundle, suspense, memo, rerender, cache |
| `web` | Web interface guidelines | aria, focus, keyboard, semantic, virtualize |
| `prompt` | AI prompts, CSS keywords | (style name) |

### Available Stacks

| Stack | Focus |
|-------|-------|
| `html-tailwind` | Tailwind utilities, responsive, a11y (DEFAULT) |
| `react` | State, hooks, performance, patterns |
| `nextjs` | SSR, routing, images, API routes |
| `vue` | Composition API, Pinia, Vue Router |
| `svelte` | Runes, stores, SvelteKit |
| `swiftui` | Views, State, Navigation, Animation |
| `react-native` | Components, Navigation, Lists |
| `flutter` | Widgets, State, Layout, Theming |
| `shadcn` | shadcn/ui components, theming, forms, patterns |
| `jetpack-compose` | Composables, Modifiers, State Hoisting, Recomposition |

---

## Example Workflow

**User request:** "Làm landing page cho dịch vụ chăm sóc da chuyên nghiệp"

### Step 1: Analyze Requirements
- Product type: Beauty/Spa service
- Style keywords: elegant, professional, soft
- Industry: Beauty/Wellness
- Stack: html-tailwind (default)

### Step 2: Establish Design Authority

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "beauty spa wellness service elegant" --design-system -p "Serenity Spa"
```

**Output:** Complete design system with pattern, style, colors, typography, effects, and anti-patterns.

### Step 3: Supplement with Detailed Searches (as needed)

```bash
# Get UX guidelines for animation and accessibility
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "animation accessibility" --domain ux

# Get alternative typography options if needed
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "elegant luxury serif" --domain typography
```

### Step 4: Stack Guidelines

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "layout responsive form" --stack html-tailwind
```

**Then:** Synthesize design system + detailed searches and implement the design.

---

## Output Formats

The `--design-system` flag supports two output formats:

```bash
# ASCII box (default) - best for terminal display
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "fintech crypto" --design-system

# Markdown - best for external documentation, not as the primary app screen
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "fintech crypto" --design-system -f markdown
```

---

## Tips for Better Results

1. **Be specific with keywords** - "healthcare SaaS dashboard" > "app"
2. **Search multiple times** - Different keywords reveal different insights
3. **Combine domains** - Style + Typography + Color = Complete design system
4. **Always check UX** - Search "animation", "z-index", "accessibility" for common issues
5. **Use stack flag** - Get implementation-specific best practices
6. **Iterate** - If first search doesn't match, try different keywords

---

## Common Rules for Professional UI

These are frequently overlooked issues that make UI look unprofessional:

### Icons & Visual Elements

| Rule | Do | Don't |
|------|----|----- |
| **No emoji icons** | Use SVG icons (Heroicons, Lucide, Simple Icons) | Use emojis like 🎨 🚀 ⚙️ as UI icons |
| **Stable hover states** | Use color/opacity transitions on hover | Use scale transforms that shift layout |
| **Correct brand logos** | Research official SVG from Simple Icons | Guess or use incorrect logo paths |
| **Consistent icon sizing** | Use fixed viewBox (24x24) with w-6 h-6 | Mix different icon sizes randomly |

### Interaction & Cursor

| Rule | Do | Don't |
|------|----|----- |
| **Cursor pointer** | Add `cursor-pointer` to all clickable/hoverable cards | Leave default cursor on interactive elements |
| **Hover feedback** | Provide visual feedback (color, shadow, border) | No indication element is interactive |
| **Smooth transitions** | Use `transition-colors duration-200` | Instant state changes or too slow (>500ms) |

### Light/Dark Mode Contrast

| Rule | Do | Don't |
|------|----|----- |
| **Glass card light mode** | Use `bg-white/80` or higher opacity | Use `bg-white/10` (too transparent) |
| **Text contrast light** | Use `#0F172A` (slate-900) for text | Use `#94A3B8` (slate-400) for body text |
| **Muted text light** | Use `#475569` (slate-600) minimum | Use gray-400 or lighter |
| **Border visibility** | Use `border-gray-200` in light mode | Use `border-white/10` (invisible) |

### Layout & Spacing

| Rule | Do | Don't |
|------|----|----- |
| **Floating navbar** | Add `top-4 left-4 right-4` spacing | Stick navbar to `top-0 left-0 right-0` |
| **Content padding** | Account for fixed navbar height | Let content hide behind fixed elements |
| **Consistent max-width** | Use same `max-w-6xl` or `max-w-7xl` | Mix different container widths |

---

## Pre-Delivery Checklist

Before delivering UI code, verify these items:

### BRC Product Semantics
- [ ] Owner Console / Trading Console screens are operating surfaces, not documentation or code-explanation pages.
- [ ] Read-only endpoints remain read-only, but their UI still supports action understanding, disabled reasons, and official handoff points when part of an action flow.
- [ ] Candidate/action screens show ActionCandidate status, risk, budget/authorization state, FinalGate preview/result, hard blockers, warnings, and evidence.
- [ ] Live/testnet/observe mode is visible, and no UI implies live readiness or real-funds action without exact Owner authorization.
- [ ] Confirmation controls are never auto-filled, and no UI suggests bypassing the official ActionSpec -> FinalGate -> Operation Layer path.

### Visual Quality
- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] Brand logos are correct (verified from Simple Icons)
- [ ] Hover states don't cause layout shift
- [ ] Use theme colors directly (bg-primary) not var() wrapper

### Interaction
- [ ] All clickable elements have `cursor-pointer`
- [ ] Hover states provide clear visual feedback
- [ ] Transitions are smooth (150-300ms)
- [ ] Focus states visible for keyboard navigation

### Light/Dark Mode
- [ ] Light mode text has sufficient contrast (4.5:1 minimum)
- [ ] Glass/transparent elements visible in light mode
- [ ] Borders visible in both modes
- [ ] Test both modes before delivery

### Layout
- [ ] Floating elements have proper spacing from edges
- [ ] No content hidden behind fixed navbars
- [ ] Responsive at 375px, 768px, 1024px, 1440px
- [ ] No horizontal scroll on mobile

### Accessibility
- [ ] All images have alt text
- [ ] Form inputs have labels
- [ ] Color is not the only indicator
- [ ] `prefers-reduced-motion` respected
