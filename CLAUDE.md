<!-- rtk-instructions v2 -->
# Command output

Command output here is condensed to save tokens, keeping every signal and
dropping costly noise. Treat it as the complete result: run commands
normally, and batch related commands into one call to avoid extra turns.
Truncated results state their recovery path in their own output. Re-run a
command as `rtk bypass <cmd>` only when its result is unusable: empty when
output was clearly expected, contradicting its exit code, or garbled.
<!-- /rtk-instructions -->

# Project Guidelines

Refer to [AGENTS.md](./AGENTS.md) for full project development guidelines:
- **Ponytail Mode**: Minimalist, pragmatic development, YAGNI, smallest complete change.
- **Superpowers**: Structured brainstorming, step-by-step planning, TDD (RED-GREEN-REFACTOR), and systematic debugging.
- **RTK**: Token-optimized shell execution and filtering.
