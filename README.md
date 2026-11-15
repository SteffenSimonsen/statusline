# statusline

A status line for [Claude Code](https://claude.com/claude-code) that shows the model name and how much of the context window is in use, with a hint when it is time to compact.

```
Fable 5.2  ████▊                 95.0K / 1M  10%  │  5h ▄ 44%  7d ▁ 6%
Fable 5.2  ██████████▋           214.0K / 1M  21%  consider /compact  │  5h ▄ 44% out ~15:26  7d ▂ 30%
Fable 5.2  ████▊                 95.0K / 1M  10%  cache cold · next message re-sends 95.0K  │  5h ▇ 83% →14:55  7d ▁ 12%
```

## What it shows

- **Model name**, in cyan.
- **A bar** that fills toward the "compact now" threshold, so a full bar means it is time to act. It fills in eighths of a cell and is coloured with a green to yellow to red gradient.
- **Tokens used** out of the context window size, and the percentage of the whole window.
- **A hint** once usage passes a threshold.
- **A prompt cache warning**. Each request re-sends the whole context, which is cheap while the prompt cache is warm. In the last ten minutes before the cache expires the line shows `cache expires in 4m`; once it has expired it shows `cache cold · next message re-sends 95.0K`, because the next message pays for the whole context uncached.
- **Rate limits**, judged by pace. Each of the five-hour and seven-day subscription limits gets a one-cell gauge that fills from the bottom (`▁▂▃▄▅▆▇█`) and a percentage for how much is used. The colour comes from projecting your usage so far to the end of the window: green if it lasts until the reset, yellow if it is getting close, red if it will not last. When it will not last, the line shows when you run out, e.g. `5h ▄ 44% out ~15:26`. From 70% used it shows the reset time instead, e.g. `→14:55`. This section is omitted when Claude Code doesn't report rate limits.

## Thresholds

A tier applies once usage passes either its share of the window or its absolute token count, whichever comes first.

| Tier | Triggers at | Hint |
|---|---|---|
| Soft (yellow) | 200K tokens or 50% of the window | `consider /compact` |
| Hard (red) | 400K tokens or 75% of the window | `/compact now or start a new session` |

These are rules of thumb, not official limits. Change the `SOFT` and `HARD` constants at the top of `statusline.py` to move them.

## Install

Requires Python 3; there are no other dependencies.

Clone the repository, then add this to `~/.claude/settings.json`, with the path to your clone:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 -S -E /path/to/statusline/statusline.py",
    "refreshInterval": 60
  }
}
```

The status line appears after the next message in Claude Code. `refreshInterval` re-runs the script every 60 seconds so the cache warning can appear while the session is idle; without it the line only updates when the conversation does.

## Notes

- The gradient needs a terminal with 24-bit colour (`COLORTERM=truecolor`). Without it the bar falls back to a single colour per tier.
- The script prints a blank second row to leave a gap above Claude Code's mode indicator. Remove the last `print` in `statusline.py` if you don't want it.
