# Runtime Explainer

This workflow produces the first chapter of the Commonware interactive book for
the `commonware-runtime` module.

It is intentionally small so we can learn Fabro while producing useful output:

1. `Brief` uses Claude Code routed to MiniMax M2.7 HighSpeed to map the module,
   source files, and teaching goals.
2. `Draft Chapter` uses the same backend/model to write the chapter.
3. `Draft Visual Specs` uses the same backend/model to specify interactive
   visualizations.
4. `Review` uses the same backend/model to audit and refine the generated files.

Outputs land in `docs/commonware-book/runtime/`.

This workflow intentionally uses the Claude CLI backend because the direct Fabro
API backend showed stream parsing issues in longer tool-using runs with our
current provider mix. The probe workflow `claude-minimax-probe` verified this
Claude-plus-MiniMax path end to end.

Run it with:

```bash
fabro run runtime-explainer
```

Or by path:

```bash
fabro run fabro/workflows/runtime-explainer/workflow.toml
```
