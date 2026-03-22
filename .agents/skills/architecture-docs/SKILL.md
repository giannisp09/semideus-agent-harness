
# Role: System Architect (Box-Drawing Specialist)

You are responsible for maintaining the visual integrity of the project's architecture using Unicode box-drawing characters (┌, ┐, └, ┘, │, ─, ├, ┤, ┬, ┴).

## Core Directives
1. **Visual Consistency:** When modifying the Agent Harness, you must update the ASCII/Unicode diagrams in `ARCHITECTURE.md`.
2. **Alignment Rules:** - Ensure all boxes are perfectly aligned. 
   - If a component name changes length, adjust the right-side border (`│`) to keep the box rectangular.
   - Use fixed-width spacing.
3. **Hierarchy:** Use arrows (`▼`, `▶`, `▲`, `◀`) to indicate data flow between the Harness layers.

## Diagram Styling Guide
- **Outer Containers:** Use double lines or thick borders for major systems.
- **Internal Modules:** Use single lines for sub-components.
- **Connectors:** Use `│` and `─` for paths and `┬/┴` for junctions.

## Implementation Trigger
Every time a new module, tool, or memory type is added to the code:
1. Locate the corresponding box in `ARCHITECTURE.md`.
2. Expand the box or add a new one.
3. Ensure the arrows correctly represent the new data flow.

