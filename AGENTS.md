# Project Agent Guidelines

This project is configured with **RTK (Rust Token Killer)**, **Ponytail**, and **Superpowers**.

---

## 1. RTK (Token Optimization)

- Command outputs are filtered and condensed via RTK to prevent token waste while preserving errors, diffs, and essential signal.
- Batch related terminal commands together.
- If raw, unfiltered output is required, use `rtk bypass <command>`.
- Check token savings anytime using `rtk gain`.

---

## 2. Ponytail (Lazy Senior Developer Mode)

**Core Principle:** *The best code is the code you never wrote.* Solve the whole problem with the least new code.

### The Smallest Complete Change
1. **Does it need to exist?** Skip features, options, and flexibility nobody asked for.
2. **Already in this codebase?** Reuse existing helpers, patterns, components, or services.
3. **Standard library or platform feature?** Use it rather than adding new abstractions.
4. **Installed dependency?** Reuse existing packages; never add a new dependency for a few lines.
5. **One clear line?** Write a clean, readable one-liner.
6. **Minimum code:** Write only the absolute minimum required to achieve correctness.

### Engineering Rules
- No unnecessary wrappers, abstractions, or speculative "for later" boilerplate.
- The shortest working diff wins once callers, tests, and configurations are handled.
- Comment only the *why* that code cannot show.
- When fixing bugs, grep all callers of the target function and fix root causes at the shared definition.

---

## 3. Superpowers (Disciplined Development Workflow)

Before jumping into code generation, follow structured engineering discipline:

1. **Brainstorming:** Clarify goals, requirements, and constraints before proposing implementations.
2. **Implementation Planning:** Create structured, bite-sized plans (`writing-plans` skill) before editing files.
3. **Test-Driven Development (TDD):**
   - Write a failing test first (RED).
   - Write the simplest code to make the test pass (GREEN).
   - Refactor cleanly without adding bloat (REFACTOR).
4. **Systematic Debugging:** Trace root causes methodically before attempting fixes; avoid guessing.
5. **Verification Before Completion:** Execute tests, linters, and validations before declaring a task complete.
6. **Subagents:** When parallel or isolated tasks arise, delegate cleanly using subagent workflows.

---

## 4. Git & Branching Strategy

- **Target Branch:** Always commit and push changes into the `hajira` branch.
- **Remote:** Origin points to `https://github.com/Hajira-Aiman/cicada.git`.
- Do not push directly to `main` or other branches unless explicitly instructed.

