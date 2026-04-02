# Book Run Configs

These run configs target the shared `module-chapter` workflow template.

Each `.toml` file defines:

- which Commonware crate to analyze
- where to write the chapter artifacts
- module-specific teaching focus
- extra context files such as blog posts when available

Useful commands:

```bash
fabro run fabro/runs/book/runtime.toml --preflight
fabro run fabro/runs/book/consensus.toml --preflight
fabro run fabro/runs/book/p2p.toml --preflight
```

Use the launcher script to preview or dispatch a batch:

```bash
fabro/scripts/dispatch-book-batch.sh
fabro/scripts/dispatch-book-batch.sh --preflight
fabro/scripts/dispatch-book-batch.sh --execute runtime consensus
```
