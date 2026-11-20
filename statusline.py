#!/usr/bin/env python3
"""Claude Code status line: model, effort, context usage, compaction hint, cache, rate limits."""
import json
import os
import sys
import time

# Hint thresholds. A tier applies once usage passes EITHER its share of the
# window or its absolute token count, whichever comes first. These are rules
# of thumb, not official limits; tune them to taste.
SOFT = (0.50, 200_000)  # worth compacting at the next natural break
HARD = (0.75, 400_000)  # compact now, or start a new session

BAR_WIDTH = 20

# Effort levels that are named after the model. They use many more tokens,
# which is easy to forget once one is set.
EFFORT_SHOW = ("xhigh", "max")

# A rate limit stays hidden until RATE_SHOW percent of it is used. It is
# yellow from there and red from RATE_HIGH.
RATE_SHOW, RATE_HIGH = 75, 90
RATE_WINDOWS = (("five_hour", "5h"), ("seven_day", "7d"))

# Prompt cache: show a countdown once it expires within this many seconds.
# Seeing it change while idle needs "refreshInterval" on the statusLine setting.
CACHE_SOON = 10 * 60

CYAN, GREEN, YELLOW, RED = "\033[36m", "\033[32m", "\033[33m", "\033[31m"
MAGENTA, GREY, RESET = "\033[35m", "\033[90m", "\033[0m"

# Gradient stops for the bar, as RGB.
G_GREEN, G_YELLOW, G_RED = (70, 200, 120), (240, 200, 60), (235, 75, 65)
TRACK = (58, 58, 64)  # unfilled part of the bar
MARK = (160, 160, 170)  # the line on the track at the HARD threshold
FG, BG = "\033[38;2;%d;%d;%dm", "\033[48;2;%d;%d;%dm"
TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")

# Left-aligned partial blocks, one to seven eighths of a cell.
EIGHTHS = " ▏▎▍▌▋▊▉"


def fmt(n, trim=False):
    """Format a token count: 950 -> 950, 18600 -> 18.6K.

    With trim, a zero decimal is dropped: 1000000 -> 1M rather than 1.0M.
    """
    for limit, suffix in ((1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            text = f"{n / limit:.1f}"
            if trim:
                text = text.rstrip("0").rstrip(".")
            return text + suffix
    return str(int(n))


def limit_of(tier, size):
    """Token count at which a tier starts, for this window size."""
    share, tokens = tier
    return min(tokens, size * share)


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient(pos, yellow_pos, red_pos):
    """Colour at pos (0..1 along the bar): green, yellow at yellow_pos, red from red_pos."""
    if pos >= red_pos:
        return G_RED
    if pos < yellow_pos:
        return mix(G_GREEN, G_YELLOW, pos / yellow_pos)
    return mix(G_YELLOW, G_RED, (pos - yellow_pos) / (red_pos - yellow_pos))


def bar(fraction, width, yellow_pos, red_pos, tier_colour):
    """A bar filled to fraction (0..1), in eighths of a cell.

    A thin line on the unfilled part marks red_pos. With 24-bit colour the bar
    is drawn as a gradient on a dark track; otherwise in tier_colour with a
    dotted track.
    """
    eighths = min(width * 8, int(fraction * width * 8))
    eighths = max(1, eighths)  # any usage shows a sliver
    full, part = divmod(eighths, 8)
    filled = full + (1 if part else 0)  # cells with anything in them
    mark = round(red_pos * width)  # the cell whose left edge is at red_pos

    if not TRUECOLOR:
        cells = "█" * full + (EIGHTHS[part] if part else "")
        track = ["░"] * (width - filled)
        if filled <= mark < width:
            track[mark - filled] = f"{RESET}▏{GREY}"
        return f"{tier_colour}{cells}{GREY}{''.join(track)}{RESET}"

    out = [BG % TRACK]
    for i in range(width):
        if i < filled:
            out.append(FG % gradient(i / width, yellow_pos, red_pos))
            out.append("█" if i < full else EIGHTHS[part])
        elif i == mark:
            out.append(FG % MARK + "▏")
        else:
            out.append(" ")
    out.append(RESET)
    return "".join(out)


def context(used, size, pct):
    """Bar, token counts, percentage and compaction hint for the context window.

    The bar spans the whole window, so it agrees with the percentage. It turns
    yellow at the SOFT threshold and red at HARD, where a line on the track
    shows how much room is left before "compact now".
    """
    hard = limit_of(HARD, size)
    soft = limit_of(SOFT, size)
    if used >= hard:
        colour, hint = RED, "/compact now or start a new session"
    elif used >= soft:
        colour, hint = YELLOW, "consider /compact"
    else:
        colour, hint = GREEN, ""
    parts = [
        bar(used / size, BAR_WIDTH, soft / size, hard / size, colour),
        f"{colour}{fmt(used)}{GREY} / {fmt(size, trim=True)}{RESET}",
        f"{colour}{round(pct)}%{RESET}",
    ]
    if hint:
        parts.append(f"{colour}{hint}{RESET}")
    return parts


def cache(info, used, size):
    """Prompt cache warning. Empty while the cache is comfortably warm.

    Once the cache has expired, the next message re-sends the whole context
    uncached, which is the most expensive moment of a long session.
    """
    expires_at = info.get("expires_at")
    if not info.get("caching_observed") or not expires_at:
        return ""
    left = expires_at - time.time()
    if left <= 0 or info.get("warm") is False:
        tokens = info.get("recache_tokens_if_cold") or used
        if not tokens:
            return f"{YELLOW}cache cold{RESET}"
        colour = RED if size and tokens >= limit_of(SOFT, size) else YELLOW
        return f"{colour}cache cold · next message re-sends {fmt(tokens)}{RESET}"
    if left <= CACHE_SOON:
        return f"{GREY}cache expires in {max(1, round(left / 60))}m{RESET}"
    return ""


def rate_limits(limits):
    """Subscription rate limits that are nearly used up, e.g. "5h 83%".

    Empty while both are below RATE_SHOW percent used.
    """
    parts = []
    for key, label in RATE_WINDOWS:
        pct = round((limits.get(key) or {}).get("used_percentage") or 0)
        if pct >= RATE_SHOW:
            colour = RED if pct >= RATE_HIGH else YELLOW
            parts.append(f"{GREY}{label}{RESET} {colour}{pct}%{RESET}")
    return "  ".join(parts)


def render(data):
    model = (data.get("model") or {}).get("display_name") or "Claude"
    effort = (data.get("effort") or {}).get("level")
    ctx = data.get("context_window") or {}
    size = ctx.get("context_window_size")
    pct = ctx.get("used_percentage")

    # Tokens currently in the context window: input plus cached input.
    usage = ctx.get("current_usage") or {}
    used = sum(
        usage.get(k) or 0
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )
    if not used and pct is not None and size:
        used = size * pct / 100

    name = f"{CYAN}{model}{RESET}"
    if effort in EFFORT_SHOW:
        name += f" {MAGENTA}{effort}{RESET}"
    parts = [name]
    if used and size:
        parts += context(used, size, used / size * 100 if pct is None else pct)
    elif pct is not None:
        parts.append(f"ctx {round(pct)}%")

    cache_text = cache(data.get("prompt_cache") or {}, used, size)
    if cache_text:
        parts.append(cache_text)

    limits_text = rate_limits(data.get("rate_limits") or {})
    if limits_text:
        parts.append(f"{GREY}│{RESET}")
        parts.append(limits_text)
    return "  ".join(parts)


try:
    # Read bytes so the JSON is decoded as UTF-8, not in the locale code page
    # that Windows uses for a piped stdin.
    data = json.load(sys.stdin.buffer)
except Exception:
    data = {}

# Windows writes to a pipe in the locale code page (e.g. cp1252), which cannot
# encode the block characters; -E also disables PYTHONIOENCODING.
sys.stdout.reconfigure(encoding="utf-8")
print(render(data))
# A spacer row between the status line and the mode indicator below it.
# U+2800 (braille blank) looks empty but is not whitespace, so it is not trimmed.
print("⠀")
