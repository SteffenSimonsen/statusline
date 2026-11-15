#!/usr/bin/env python3
"""Claude Code status line: model, context usage, compaction hint, cache, rate limits."""
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

# Rate limits are judged by pace as well as level: usage so far is projected
# to the end of the window. A limit is yellow from RATE_WARN percent used or
# PACE_WARN percent projected, and red from RATE_HIGH used or 100 projected.
RATE_WARN, RATE_HIGH = 70, 90
PACE_WARN = 85
# No projection until this share of the window has passed; too noisy before.
PACE_MIN_ELAPSED = 0.10
RATE_WINDOWS = (("five_hour", "5h", 5 * 3600), ("seven_day", "7d", 7 * 86400))
# One-cell gauge that fills from the bottom, one to eight eighths. These are
# block elements, like the bar, so they are all drawn at the same size.
LEVELS = "▁▂▃▄▅▆▇█"

# Prompt cache: show a countdown once it expires within this many seconds.
# Seeing it change while idle needs "refreshInterval" on the statusLine setting.
CACHE_SOON = 10 * 60

CYAN, GREEN, YELLOW, RED = "\033[36m", "\033[32m", "\033[33m", "\033[31m"
GREY, RESET = "\033[90m", "\033[0m"

# Gradient stops for the bars, as RGB.
G_GREEN, G_YELLOW, G_RED = (70, 200, 120), (240, 200, 60), (235, 75, 65)
TRACK = (58, 58, 64)  # unfilled part of a bar
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


def gradient(pos, yellow_pos):
    """Colour at pos (0..1 along a bar): green, yellow at yellow_pos, then red."""
    if pos <= yellow_pos:
        return mix(G_GREEN, G_YELLOW, pos / yellow_pos)
    return mix(G_YELLOW, G_RED, (pos - yellow_pos) / (1 - yellow_pos))


def bar(fraction, width, yellow_pos, tier_colour):
    """A bar filled to fraction (0..1), in eighths of a cell.

    With 24-bit colour it is drawn as a gradient on a dark track; otherwise
    in tier_colour with a dotted track.
    """
    eighths = min(width * 8, int(fraction * width * 8))
    eighths = max(1, eighths)  # any usage shows a sliver
    full, part = divmod(eighths, 8)

    if not TRUECOLOR:
        cells = "█" * full + (EIGHTHS[part] if part else "")
        return f"{tier_colour}{cells}{GREY}{'░' * (width - len(cells))}{RESET}"

    out = ["\033[48;2;%d;%d;%dm" % TRACK]
    for i in range(width):
        if i < full:
            char = "█"
        elif i == full and part:
            char = EIGHTHS[part]
        else:
            char = " "
        if char != " ":
            out.append("\033[38;2;%d;%d;%dm" % gradient(i / (width - 1), yellow_pos))
        out.append(char)
    out.append(RESET)
    return "".join(out)


def context(used, size, pct):
    """Bar, token counts, percentage and compaction hint for the context window.

    The bar fills toward the HARD threshold, so a full bar means "compact now".
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
        bar(used / hard, BAR_WIDTH, soft / hard, colour),
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


def clock(at, now):
    """Time of day for a moment within a day of now, otherwise the weekday too."""
    style = "%H:%M" if at - now < 86400 else "%a %H:%M"
    return time.strftime(style, time.localtime(at))


def gauge(pct, colour):
    """A one-cell gauge for pct used, filling from the bottom on a dark track."""
    eighths = min(8, round(pct / 100 * 8))
    if pct > 0:
        eighths = max(1, eighths)
    if not TRUECOLOR:
        return f"{colour}{LEVELS[eighths - 1]}{RESET}" if eighths else f"{GREY}▁{RESET}"
    track = "\033[48;2;%d;%d;%dm" % TRACK
    return f"{track}{colour}{LEVELS[eighths - 1] if eighths else ' '}{RESET}"


def rate_limits(limits):
    """Subscription rate limits, e.g. "5h ▄ 44%  7d ▁ 6%". Empty if not provided.

    The gauge shows how much is used. The colour shows whether the current pace
    lasts until the reset; if it does not, the time it runs out is shown.
    """
    now = time.time()
    parts = []
    for key, label, length in RATE_WINDOWS:
        window = limits.get(key) or {}
        pct = window.get("used_percentage")
        if pct is None:
            continue
        resets_at = window.get("resets_at")

        # Project usage to the end of the window from the pace so far.
        projected, runs_out_at = None, None
        if resets_at and pct > 0:
            elapsed = length - (resets_at - now)
            if PACE_MIN_ELAPSED * length <= elapsed <= length:
                projected = pct * length / elapsed
                if projected >= 100 and pct < 100:
                    runs_out_at = now + (100 - pct) * elapsed / pct

        if pct >= RATE_HIGH or runs_out_at:
            colour = RED
        elif pct >= RATE_WARN or (projected or 0) >= PACE_WARN:
            colour = YELLOW
        else:
            colour = GREEN

        text = f"{GREY}{label}{RESET} {gauge(pct, colour)} {colour}{round(pct)}%{RESET}"
        if runs_out_at:
            text += f"{colour} out ~{clock(runs_out_at, now)}{RESET}"
        elif resets_at and pct >= RATE_WARN:
            text += f"{GREY} →{clock(resets_at, now)}{RESET}"
        parts.append(text)
    return "  ".join(parts)


def render(data):
    model = (data.get("model") or {}).get("display_name") or "Claude"
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

    parts = [f"{CYAN}{model}{RESET}"]
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
    data = json.load(sys.stdin)
except Exception:
    data = {}

print(render(data))
# A spacer row between the status line and the mode indicator below it.
# U+2800 (braille blank) looks empty but is not whitespace, so it is not trimmed.
print("⠀")
