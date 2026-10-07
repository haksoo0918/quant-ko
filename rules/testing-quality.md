# Testing & Code Quality Standards

This document establishes the testing strategy, static analysis requirements, and quality benchmarks for this project.

## 1. Testing Strategy & Pyramid

1. **Unit Tests (Fast & Isolated)**:
   - Focus on pure functions, utility modules, domain logic, and state transitions.
   - Mock network and external I/O dependencies.
2. **Integration Tests (Component & API)**:
   - Verify interactions between controllers, databases, services, or UI components.
   - Use test databases or isolated mock servers.
3. **End-to-End (E2E) Tests (Critical User Flows)**:
   - Cover high-value workflows (e.g. sign-up, payment, key product journey).

---

## 2. Test Structure & Principles

1. **Apply TDD (Test-Driven Development) Cycle**:
   - **Red (Failing Test)**: Write a failing unit or integration test defining the expected behavior before implementing code.
   - **Green (Minimal Implementation)**: Write the minimum amount of code necessary to make the test pass.
   - **Refactor (Clean & Optimize)**: Refactor code and tests for readability, modularity, and deduplication while keeping tests green.
2. **AAA Pattern**: Structure tests with **Arrange**, **Act**, and **Assert** phases clearly separated:
   ```typescript
   it('should calculate total order amount including tax', () => {
     // Arrange
     const cart = [{ price: 100, qty: 2 }];
     // Act
     const total = calculateTotal(cart, 0.1);
     // Assert
     expect(total).toBe(220);
   });
   ```
3. **Deterministic & Isolated**: Tests must not rely on execution order or shared mutable global state.
4. **Descriptive Test Names**: Name tests clearly describing the scenario and expected outcome (`should <expected behavior> when <condition>`).

---

## 3. Static Analysis & Build Verification

1. **Idiomatic Language Standards**: Strictly follow official language style guides and conventions (TS: camelCase/PascalCase, Python: PEP 8/snake_case, Go: Effective Go, etc.) and write idiomatic code.
2. **Mandatory Linter & Formatter Setup**: Configure standard linters/formatters (Biome, Ruff, etc.) at project init; enforce 'Format on Save' and pre-commit checks.
3. **Strict Type Checking**: Maintain zero compiler/type-checker warnings (e.g. `tsc --noEmit`, `mypy`).
4. **Dead Code Elimination**: Remove unused imports, debugging console logs, and obsolete code.

---

## 4. Definition of Done (DoD)

Before any feature or bug fix is marked as complete:
- [ ] Unit/Integration tests covering the changes have been written and pass.
- [ ] Linter and static type-checker report zero errors.
- [ ] Full application build executes successfully without warnings.
- [ ] Relevant documentation and `PRD.md` have been updated.
