# Claude MiniMax Probe

This workflow verifies that Fabro can drive Claude Code in CLI backend mode
while pointing Claude at MiniMax's Anthropic-compatible endpoint.

It uses:

- `provider = "anthropic"`
- `backend = "cli"`
- `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`
- `ANTHROPIC_AUTH_TOKEN=${env.MINIMAX_API_KEY}`
- `MiniMax-M2.7-highspeed` for all Claude model slots

Run it with:

```bash
fabro run claude-minimax-probe
```
