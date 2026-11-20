# statusline

A status line for [Claude Code](https://claude.com/claude-code) that shows the model name and how much of the context window is in use, with a hint when it is time to compact.

```
Fable 5.2  █▉      ▏             95.0K / 1M  10%
Fable 5.2 max  ████▎   ▏             214.0K / 1M  21%  consider /compact
Fable 5.2  █▉      ▏             95.0K / 1M  10%  cache cold · next message re-sends 95.0K  │  5h 83%
```

## What it shows

- **Model name**, in cyan. The effort level follows it when it is `xhigh` or `max`: those use many more tokens, which is easy to forget once one is set.
- **A bar** for the whole context window, so it agrees with the percentage. It fills in eighths of a cell and is coloured with a gradient: green, yellow at the soft threshold and red from the hard one. A thin line on the unfilled part marks the hard threshold, so you can see how much room is left before it is time to compact.
- **Tokens used** out of the context window size, and the percentage of the whole window.
- **A hint** once usage passes a threshold.
- **A prompt cache warning**. Each request re-sends the whole context, which is cheap while the prompt cache is warm. In the last ten minutes before the cache expires the line shows `cache expires in 4m`; once it has expired it shows `cache cold · next message re-sends 95.0K`, because the next message pays for the whole context uncached.
- **Rate limits**, only when one is running low. The five-hour and seven-day subscription limits stay hidden until 75% of one is used. It then appears as `5h 83%` or `7d 78%`, in yellow, and turns red from 90%. It disappears again once its window has reset.

## Thresholds

A tier applies once usage passes either its share of the window or its absolute token count, whichever comes first.

| Tier | Triggers at | Hint |
|---|---|---|
| Soft (yellow) | 200K tokens or 50% of the window | `consider /compact` |
| Hard (red) | 400K tokens or 75% of the window | `/compact now or start a new session` |

These are rules of thumb, not official limits. Change the `SOFT` and `HARD` constants at the top of `statusline.py` to move them; the line on the bar follows `HARD`. `RATE_SHOW` and `RATE_HIGH` set when a rate limit appears and when it turns red, and `EFFORT_SHOW` lists the effort levels that are shown.

## Install

Requires Python 3; there are no other dependencies.

Run the installer with [uv](https://docs.astral.sh/uv/):

```sh
uv run https://raw.githubusercontent.com/SteffenSimonsen/statusline/main/install.py
```

or with Python alone:

```sh
curl -fsSL https://raw.githubusercontent.com/SteffenSimonsen/statusline/main/install.py | python3 -
```

It downloads `statusline.py` to `~/.claude/statusline/` and sets `statusLine` in `~/.claude/settings.json`, keeping your other settings and a backup in `settings.json.bak`. It honours `CLAUDE_CONFIG_DIR`. Run it again to update; pass `--ref <tag>` to install a specific version.

### Manual install

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
