# Frontend & Mobile Development Standards

This document establishes UI/UX development principles, design consistency, and client-side implementation standards.

## 1. Screen-First & Mock-First Workflow

1. **Visual Validation Before Backend**:
   - For UI-driven tasks, validate layouts, user interactions, and visual states with mock data before connecting to backend endpoints.
   - Verify empty, loading, error, and partial data states upfront.
2. **Interactive Prototypes**:
   - Prefer lightweight mock servers, fixture data, or in-memory state during rapid UI iteration.
   - Confirm screen layout alignment with the user before finalizing complex data fetching logic.

---

## 2. Component Architecture & Design System

1. **Single Responsibility**: Keep components modular, focused, and decoupled from global business logic where possible.
2. **Presentational vs Container Components**: Separate visual presentation (pure UI props) from data fetching/side-effect logic.
3. **Active Adoption of Headless UI Primitives**:
   - Strongly prefer accessible Headless UI primitives (e.g. Radix UI, Reka UI) that have built-in accessibility (a11y), keyboard navigation, and focus management.
   - Delegate behavior and ARIA semantics to primitives while controlling visual styles completely with native modern CSS.
4. **Native Modern CSS Standards**:
   - Build layouts and themes exclusively with native modern CSS standards (`@layer`, `@container`, CSS variables) without external utility-class dependencies.
5. **Design Tokens & Theme Consistency**:
   - Utilize predefined design tokens (colors, typography, spacing, shadows) declared via CSS custom properties.
   - Avoid ad-hoc inline styles or magic values.

---

## 3. Mobile-First Responsive Design & Accessibility (a11y)

1. **Mobile-First Workflow**:
   - Design and build targeting mobile viewports (<640px) as baseline, scaling up via `min-width` breakpoints (no reverse desktop overrides).
   - Ensure interactive touch targets (at least 44×44px) and prevent horizontal viewport overflow.
2. **Semantic Markup & Keyboard Navigation**:
   - Use semantic HTML tags (`<header>`, `<nav>`, `<main>`, `<button>`) and provide `aria-label` for icon-only controls.
   - Maintain WCAG AA color contrast and visible keyboard focus states.
3. **Color Blindness Accessibility**:
   - Never convey status (success, warning, error) or information via color alone; combine with text labels, icons, or borders.
   - Use contrast, patterns (hatching/dots), and direct legends in charts; avoid isolated red/green contrasts (prefer blue/orange safe palettes).

---

## 4. Modern CSS Standards

1. **Container Queries (@container)**: Prioritize `@container` queries over viewport media queries for component-level adaptability.
2. **Cascade Layers (@layer)**: Structure styles within `@layer reset, base, components, utilities` to manage specificity.
3. **Naming Conventions (kebab-case)**:
   - Class names: Lowercase `kebab-case` (e.g. `.card-header`, `.btn-primary`).
   - CSS variables (tokens): Hierarchical `kebab-case` formatted as `--category-property-state` (e.g. `--color-bg-primary`, `--space-md`).
4. **Design Tokens & CSS Variables**: Define global tokens in `:root` and utilize component-scoped CSS variables.
5. **Modern CSS Native Features**: Actively use native nesting (`&`), relational selectors (`:has()`), Subgrid, and math functions (`clamp()`, `min()`, `max()`).

---

## 5. Performance & Core Web Vitals (CWV)

1. **Asset Optimization**: Use modern formats (WebP/AVIF) and specify explicit dimensions to eliminate CLS.
2. **Code Splitting & Lazy Loading**: Split routes and defer non-critical code to safeguard LCP and INP.
