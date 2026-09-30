# FinAI Web Reference — Responsive Sidebar & AI Overlay

## Baseline
Use the existing FinAI dashboard visual design and data as the baseline. Do not redesign or replace the dashboard content.

## 1. Global state
- AI Assistant must be CLOSED on initial page load on both desktop and mobile.
- Sidebar must be expanded on desktop by default.
- Mobile sidebar must be closed by default.
- AI open/close and desktop sidebar collapse/expand must be client-side UI state changes; they must not require a Streamlit rerun or page refresh.
- Do not introduce a blank-page/loading state when toggling either panel.

## 2. Desktop layout
Desktop breakpoint: > 800px.

Architecture:
- App layout consists of LEFT SIDEBAR + MAIN CONTENT.
- AI Assistant is NOT a third grid/flex column.
- AI Assistant is a fixed right-side overlay above the dashboard.
- Main dashboard width must remain unchanged when AI opens or closes.
- Sidebar collapse may increase the available main-content width, but AI state must never reduce it.

Desktop states:
A. Sidebar expanded + AI closed
B. Sidebar collapsed + AI closed
C. Sidebar expanded + AI open
D. Sidebar collapsed + AI open

All four states must render correctly.

## 3. Desktop AI Assistant
- Default state: CLOSED.
- Show trigger: AI sparkle icon in the application header.
- The trigger must be part of the header and must never float over KPI cards, tables, or dashboard content.
- Open action: show the AI panel as a fixed right overlay.
- Close action: X button in the AI panel header.
- Remove all `>>` and `<<` AI controls.
- Opening/closing must not change dashboard width, scale, card size, table width, or typography.
- AI panel should slide/fade smoothly from the right.
- AI panel must have a sufficiently high z-index and a subtle shadow/border to distinguish it from the dashboard.
- Closing the AI panel must leave the underlying dashboard visually identical to the closed state.

Recommended desktop AI geometry:
- width: min(390px, 42vw)
- height: 100dvh
- position: fixed
- top: 0
- right: 0

## 4. Desktop left sidebar
- Expanded width approximately 240–260px.
- Collapsed width approximately 64–76px.
- Expanded state: icon + label.
- Collapsed state: icon only.
- Sidebar must remain visible when collapsed; do not use display:none.
- Use a hamburger/menu icon for collapse/expand.
- Do not use `>>`, `<<`, `◀`, or `▶` as the primary sidebar control.
- The toggle must remain easy to locate in both expanded and collapsed states.
- Sidebar collapse must not distort the dashboard content.
- Preserve the existing green/lime FinAI visual language.

## 5. Mobile layout
Mobile breakpoint: <= 800px.

- Keep the existing mobile experience and visual style.
- Mobile sidebar is a drawer from the left, not an icon-only rail.
- Mobile sidebar closed by default.
- Mobile hamburger opens the drawer.
- Tapping the outside overlay closes the drawer.
- AI Assistant is full-screen/near-full-screen overlay.
- AI Assistant is closed by default.
- Mobile header contains the AI sparkle button.
- Tapping the AI sparkle opens AI.
- AI header contains X to close.
- Do not show `>>` / `<<` AI controls.

## 6. Responsive behavior
- Resizing between desktop and mobile must not leave stale open/closed classes that break the layout.
- Desktop sidebar collapse state must not be reused as the mobile drawer state.
- Mobile drawer state must not force the desktop collapsed state.
- AI state can remain logically consistent across resize, but its geometry must adapt to the active breakpoint.
- No horizontal page overflow caused by the sidebar or AI panel.

## 7. Dashboard preservation
Do not change:
- KPI values
- table values
- AI conversation content
- menu labels
- financial terminology
- existing colors/typography unless required for layout correctness
- business logic
- data processing

The current dashboard is considered the visual baseline.

## 8. Functional acceptance tests
1. Fresh desktop load -> AI closed.
2. Fresh mobile load -> AI closed.
3. Desktop click AI header icon -> AI opens as overlay.
4. While AI is open -> dashboard does not shrink.
5. Click X -> AI closes.
6. Desktop collapse sidebar -> labels disappear, icons remain.
7. Desktop expand sidebar -> labels return.
8. Sidebar collapse/expand does not refresh the page.
9. AI open/close does not refresh the page.
10. Mobile hamburger -> drawer opens.
11. Mobile drawer overlay click -> drawer closes.
12. Mobile AI icon -> AI opens.
13. Mobile AI X -> AI closes.
14. Resize desktop/mobile repeatedly -> no blank page and no broken controls.
15. AI trigger never overlaps dashboard content.
16. No `>>` / `<<` controls remain.
17. No unintended horizontal overflow.
18. Underlying dashboard looks identical before and after closing AI.

## 9. Implementation constraint
Prefer one stable DOM/layout structure with CSS classes and client-side JavaScript state toggles. Avoid rebuilding the Streamlit layout to represent AI open/closed states. Avoid making AI a Streamlit column. Avoid relying on Streamlit reruns for UI-only state.

## 10. Regression protection
Before deployment, test at minimum:
- Mobile portrait
- Desktop/laptop width
- Desktop with sidebar expanded
- Desktop with sidebar collapsed
- Desktop with AI open
- Desktop with AI open + sidebar collapsed
- Mobile with drawer open
- Mobile with AI open

The page must never become blank because of a sidebar/AI state change.
