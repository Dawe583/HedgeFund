"""Loss-streak cool-down guard - pure functions, zero dependencies.

A bot that keeps losing is either out of sync with the regime or tilted.
After MAX_LOSSES consecutive losing closes the bot pauses for COOLDOWN_HOURS
(wins reset the streak). State lives in the kv store (get/set callables).
"""

MAX_LOSSES = 3
COOLDOWN_HOURS = 4


def _streak_key(bot):
    return "guard:streak:" + bot


def _until_key(bot):
    return "guard:cooldown_until:" + bot


def record_close(get_state, set_state, bot, pnl, now_ts, max_losses=MAX_LOSSES, cooldown_h=COOLDOWN_HOURS):
    """Update the streak after a closed trade."""
    try:
        streak = int(get_state(_streak_key(bot)) or 0)
    except (TypeError, ValueError):
        streak = 0
    streak = streak + 1 if pnl <= 0 else 0
    until = 0.0
    if streak >= max_losses:
        until = now_ts + cooldown_h * 3600
        streak = 0
    set_state(_streak_key(bot), streak)
    set_state(_until_key(bot), until)
    return {"streak": streak, "cooldown_until": until}


def is_paused(get_state, bot, now_ts):
    """True when the bot is inside a cool-down window."""
    try:
        until = float(get_state(_until_key(bot)) or 0)
    except (TypeError, ValueError):
        return False, "guard ok"
    if until and now_ts < until:
        left = int((until - now_ts) / 60)
        return True, "cool-down after loss streak (%d min left)" % left
    return False, "guard ok"


def status(get_state, bot, now_ts):
    """Dashboard-friendly snapshot."""
    try:
        streak = int(get_state(_streak_key(bot)) or 0)
    except (TypeError, ValueError):
        streak = 0
    paused, reason = is_paused(get_state, bot, now_ts)
    return {"bot": bot, "loss_streak": streak, "paused": paused, "reason": reason}
