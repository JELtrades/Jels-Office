#!/usr/bin/env python3
"""Generate status.json for the public Virtual Office (GitHub Pages).

Reads Jaden's REAL logs/state files and derives each bot's status from its
real schedule and the current America/New_York time. Nothing is faked:
a bot only shows "working" when it is inside one of its real active
windows (or, for Bell, when its last Trump sweep is fresh or a reminder just fired). "needs-you"
means a real recorded decision is waiting on Jaden.

Run:  python3 generate_status.py
Writes: status.json next to this script (same directory as index.html).

To keep the published page live, re-run this script and push the new
status.json to the GitHub repo every 5 minutes (see README.md).
"""

import json
import re
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
WORKSPACE = Path.home() / "workspace"

PAPER_STATE = WORKSPACE / "goals/trading-session-reminders/hidden_files/ict-paper-state.json"
REPORTED = WORKSPACE / "goals/trump-statement-market-alerts/hidden_files/reported.json"
JOURNAL = WORKSPACE / "goals/trade-journal/files/trade-journal.md"

# ---------------------------------------------------------------------------
# Recorded facts that live in MEMORY.md / the session log, not in a machine
# file. Each is a real dated event or a real open item awaiting Jaden.
# ---------------------------------------------------------------------------
RECORDED_LOG = [
    # (time_et_str, bot_id, text)
    ("2026-11-11 18:12 ET", "clip3",
     "Clip 3 assigned by Jaden — the fixer: fixes finished videos and "
     "crisps them up, fixes the sound, matches the style all the way "
     "through, and adds a funny ending. First job: polish Jane's gum "
     "video into a v2. Now working at his desk."),
    ("2026-11-11 17:35 ET", "muse",
     "Muse's office expanded to 10x12, same size as the trading room — big "
     "3.8-wide desk at the far end, and a second dog: a Catahoula Leopard "
     "Dog (merle coat) with its own bed in the office. Both dogs wander the "
     "office and lie in their own beds."),
    ("2026-11-11 16:58 ET", "keeper",
     "George sits waiting until launch — Nov 27, 2026, at Jaden's call. "
     "Launch items (social links, store password + test order) parked until then."),
    ("2026-11-11 16:54 ET", "clip2",
     "Clip 2 named Jane by Jaden — makes the same style of video as the "
     "viral explainer Rob finds, just with a different idea. Rob sends his "
     "best finds to Jane. Now working at her desk."),
    ("2026-11-11 16:51 ET", "clip1",
     "Clip 1 named Rob by Jaden — viral ideas scout: finds explainer-video "
     "ideas on Instagram that haven't been done yet. Now working at his desk."),
    ("2026-11-11 16:00 ET", "paper",
     "Asia model + midday model (lunch piece on fixed150) wired into paper "
     "trading — first Asia model session tonight 19:00 ET, first lunch "
     "piece Thu Nov 12 12:00 ET. First paper trade corrected to a LOSS "
     "(-14 pts) by Jaden — wick 4 pts past the stop. Lucid Flex 50K pass "
     "practice live: daily caps +$1,200 / -$300, 40% consistency, EOD "
     "trailing floor (balance $49,888, floor $48,000, room $1,888)."),
    ("2026-11-11 15:11 ET", "clip1",
     "Clipping room opened at the back end of the hallway — three new bots "
     "(Clip 1/2/3) awaiting assignments from Jaden; recording gear in place."),
    ("2026-11-11 10:28 ET", "keeper",
     "Paid shipping options removed from Grind & Gather — free US shipping "
     "(7-15 business days) is now the only option."),
    ("2026-11-11 06:56 ET", "bell",
     "NY session reminder sent — Veterans Day, stocks/CME normal hours, no "
     "red-folder USD events; PPI Fri Nov 13 preview."),
    ("2026-11-10 16:47 ET", "paper",
     "Paper trading went live — JELS Nyam model opens 09:30-10:30 ET + midday "
     "11:00-12:00 ET, log-only, no real orders."),
    ("2026-11-11 14:25 ET", "muse",
     "Muse's office opened at the end of the hallway — waiting bots take the "
     "couches, bots that need help come to sit in the guest chairs."),
]

KEEPER_OPEN_ITEMS = [
    "Social links in Shopify — needs Jaden's handles",
    "Store password — remove at launch, then place a test order",
]
# Black Friday — Grind & Gather launch. George waits until this date;
# on/after it his open items surface as needs-you again.
LAUNCH_DATE = date(2026, 11, 27)
KEEPER_LAST_ACTION = ("Paid shipping options removed Wed Nov 11 ~10:28 ET — "
                      "free US shipping (7-15 days) is now the only option.")

LEDGER_LAST_ACTION = "Weekly review — week of Nov 2-6 (no trades logged that week)."


def parse_et(s):
    """Parse '2026-11-11 10:22 ET' or ISO '2026-11-11T10:22:00-05:00' to ET datetime."""
    if not s:
        return None
    s = s.strip()
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(ET) if dt.tzinfo else dt.replace(tzinfo=ET)
    except ValueError:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", s)
    if m:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    return None


def fmt_time(dt):
    return dt.strftime("%a %b %-d, %-I:%M %p ET") if dt else "unknown"


def next_weekday_time(now, weekdays, hour, minute):
    """Next datetime (ET) on one of `weekdays` (Mon=0..Sun=6) at hour:minute."""
    for ahead in range(0, 8):
        cand = (now + timedelta(days=ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cand.weekday() in weekdays and cand > now:
            return cand
    return None


def in_window(now, start_h, start_m, end_h, end_m):
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start <= now < end


# NOTE: the paper-trading evening block (Sun-Thu 18:00-01:00 ET, Asia
# model) was removed Thu Nov 12 2026 — Jaden scrapped the Asia model.
# in_evening_block / next_evening_time were deleted with it; Scanner
# and Paper now run on the day block only. (Bell's 5 PM Asia session
# reminder is a separate standing commitment and is untouched.)


# ---------------------------------------------------------------------------
# Read the real sources
# ---------------------------------------------------------------------------
def load_paper():
    try:
        return json.loads(PAPER_STATE.read_text())
    except Exception as e:
        return {"error": str(e), "trades": []}


def load_reported():
    try:
        return json.loads(REPORTED.read_text())
    except Exception as e:
        return {"error": str(e)}


def load_journal_last_trade():
    try:
        text = JOURNAL.read_text()
    except Exception:
        return None
    dates = re.findall(r"^\|\s*(2026-\d{2}-\d{2})\s*\|", text, flags=re.M)
    return max(dates) if dates else None


# ---------------------------------------------------------------------------
# Build the status document
# ---------------------------------------------------------------------------
def build():
    now = datetime.now(ET)
    weekday = now.weekday()  # Mon=0 .. Sun=6
    is_weekday = weekday < 5

    paper = load_paper()
    trades = paper.get("trades", [])
    # Voided trades are records only — never scored (win_r/points may be None).
    closed = [t for t in trades
              if t.get("status") == "closed" and not t.get("voided")]
    wins = [t for t in closed if (t.get("win_r") or 0) > 0]
    total_pts = sum(t.get("points") or 0 for t in closed)
    scored = [t for t in trades if not t.get("voided")]
    latest = scored[-1] if scored else None

    reported = load_reported()
    last_checked = parse_et(reported.get("last_checked"))
    last_result = reported.get("last_check_result", "unknown")
    alerts_ever = sum(1 for k, v in reported.items()
                      if isinstance(v, dict) and v.get("alerted") is True
                      and not k.startswith("news-vertical-sweep-"))

    journal_last = load_journal_last_trade()

    # --- Scanner: JELS watch / paper engine active window —
    # day block Mon-Fri 09:30-15:00 only (the evening block was removed
    # Nov 12 2026 when Jaden scrapped the Asia model).
    day_block = is_weekday and in_window(now, 9, 30, 15, 0)
    scan_working = day_block
    next_scan = next_weekday_time(now, {0, 1, 2, 3, 4}, 9, 30)
    scanner = {
        "id": "scanner",
        "name": "Scanner",
        "role": "MNQ / ES watch — JELS strat detection (15m + 5m CISD + FVG)",
        "status": "working" if scan_working else "waiting",
        "status_reason": ("Inside the live watch window (Mon-Fri 09:30-15:00 ET)."
                          if scan_working else
                          "Outside the live watch window (Mon-Fri 09:30-15:00 ET)."),
        "schedule": ("Mon-Fri 09:30-15:00 ET "
                     "(Nyam opens 09:30-10:30, midday model 11:00-13:00)"),
        "last_action": (f"Engine run #{paper.get('runs_total', '?')} at "
                        f"{paper.get('last_run_et', 'unknown')}; "
                        f"{len(trades)} paper trade(s) detected so far."),
        "next_action": (f"Next scan window {fmt_time(next_scan)}"
                        if not scan_working else "Scanning every 5 minutes right now."),
        "needs_you": None,
    }

    # --- Paper: same active window; last action is the latest paper trade
    # (The Nov 11 correction turned the first trade into a LOSS — the text
    # must render WIN/LOSS from the sign of win_r, never hardcode WIN.)
    if latest:
        label = (latest.get("track_label") or latest.get("model")
                 or "Nyam model")
        wr = latest.get("win_r")
        if latest.get("status") == "closed":
            if wr is not None and wr > 0:
                res_txt = f"WIN +{wr}R (+{latest.get('points')} pts)"
            elif wr is not None and wr < 0:
                res_txt = f"LOSS {wr}R ({latest.get('points')} pts)"
                if latest.get("outcome_detail"):
                    res_txt += f" ({latest['outcome_detail']})"
            elif wr == 0:
                res_txt = "breakeven"
            else:
                res_txt = latest.get("outcome_detail", "closed")
        else:
            res_txt = "open — awaiting entry/outcome"
        if latest.get("management") == "fixed150":
            stop_txt = "$150 fixed stop (18.75 pts at 4 micros)"
        else:
            stop_txt = f"Stop {latest.get('stop_pts')} pts"
        last_trade_txt = (
            f"{latest['id']} — {latest.get('direction', '')} {label} "
            f"{latest.get('source', '')} — {res_txt} "
            f"at {latest.get('closed_at_et', latest.get('detection_time_et', ''))}. "
            f"{stop_txt}; "
            f"wick went {latest.get('wick_beyond_stop_pts')} pts beyond stop."
        )
    else:
        last_trade_txt = "No paper trades yet."
    # Flex 50K practice tracker — rides in the paper state file
    # (engine persists state["flex"] on every run; derived from the
    # closed trades, never a second ledger).
    flex = paper.get("flex", {}) or {}
    cap_state_txt = {"trading": "trading",
                     "profit_cap": "day done — hit +$1,200 profit cap",
                     "loss_cap": "day done — hit −$300 loss cap"}.get(
                         flex.get("cap_state"), "trading")
    paper_bot = {
        "id": "paper",
        "name": "Paper",
        "role": ("JELS paper trader — log-only hypothetical trades, no real "
                 "orders; practicing the Lucid Flex 50K pass (daily caps "
                 "+$1,200 / −$300, 40% consistency, EOD trailing floor)"),
        "status": "working" if scan_working else "waiting",
        "status_reason": ("Inside the paper-trading window (Mon-Fri 09:30-15:00 ET)."
                          if scan_working else
                          "Outside the paper-trading window (Mon-Fri 09:30-15:00 ET)."),
        "schedule": ("Mon-Fri 09:30-15:00 ET, checks every 5 min"),
        "last_action": last_trade_txt,
        "next_action": (f"Next window {fmt_time(next_scan)}"
                        if not scan_working else
                        "Watching for the next JELS setup (opens + midday "
                        "model)."),
        "needs_you": None,
        "stats": {
            "trades_opened": len(trades),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(closed) - len(wins),
            "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
            "total_points": total_pts,
            "total_usd_4_micros": round(total_pts * 2 * 4, 2),
            "flex_target_progress_usd": flex.get("total_pnl_usd"),
            "flex_target_pct": flex.get("target_progress_pct"),
            "flex_balance_usd": flex.get("balance"),
            "flex_floor_usd": flex.get("floor"),
            "flex_floor_locked": flex.get("floor_locked"),
            "flex_room_usd": flex.get("room_usd"),
            "flex_best_day_usd": flex.get("best_day_usd"),
            "flex_best_day_date": flex.get("best_day_date"),
            "flex_best_day_ratio": flex.get("best_day_ratio"),
            "flex_required_total_usd": flex.get("required_total_usd"),
            "flex_days_traded": flex.get("days_traded"),
            "flex_today_pnl_usd": flex.get("today_pnl_usd"),
            "flex_today_date": flex.get("today_date"),
            "flex_cap_state": flex.get("cap_state"),
            "flex_cap_state_text": cap_state_txt,
            "flex_passed": flex.get("passed"),
        },
    }

    # --- Bell's Trump-sweep half: 30-min sweeps, around the clock
    # (The old separate news bot's job is folded into Bell — same "tell Jaden when it matters" work.)
    fresh = last_checked is not None and (now - last_checked) <= timedelta(minutes=45)
    if last_checked:
        next_sweep = last_checked + timedelta(minutes=30)
        while next_sweep <= now:
            next_sweep += timedelta(minutes=30)
    else:
        next_sweep = None

    # --- Bell: alerts & reminders — Trump sweeps + session reminders
    ny_today = is_weekday and in_window(now, 7, 0, 7, 45)
    asia_today = weekday in {6, 0, 1, 2, 3} and in_window(now, 17, 0, 17, 45)
    reminder_working = ny_today or asia_today
    # Working when either half is live: a reminder just fired, or the last
    # Trump sweep is fresh. Waiting only when both halves are quiet.
    bell_working = reminder_working or fresh
    next_ny = next_weekday_time(now, {0, 1, 2, 3, 4}, 7, 0)
    next_asia = next_weekday_time(now, {6, 0, 1, 2, 3}, 17, 0)
    nxt = min(x for x in (next_ny, next_asia) if x)
    if reminder_working:
        bell_reason = "Just sent a session reminder."
        if fresh:
            bell_reason += f" Last Trump sweep {fmt_time(last_checked)} — fresh."
    elif fresh:
        bell_reason = f"Last Trump sweep {fmt_time(last_checked)} — fresh; between session reminders."
    else:
        bell_reason = (f"Between session reminders; last Trump sweep "
                       f"{fmt_time(last_checked)} — stale, no recent check.")
    bell = {
        "id": "bell",
        "name": "Bell",
        "role": "Alerts & reminders — Trump statement / market-news sweeps every 30 min + session reminders (NY 7 AM, Asia 5 PM)",
        "status": "working" if bell_working else "waiting",
        "status_reason": bell_reason,
        "schedule": ("Trump sweeps every 30 min, around the clock + session reminders "
                     "Mon-Fri 7:00 AM ET (NY) and Sun-Thu 5:00 PM ET (Asia)"),
        "last_action": ("NY session reminder sent Wed Nov 11, 06:56 ET — Veterans Day, "
                        "no red-folder USD events; PPI Fri Nov 13 preview. "
                        f"Last Trump sweep {fmt_time(last_checked)}: "
                        f"{'no qualifying market-moving statement, no alert' if last_result == 'no_alert' else last_result}. "
                        f"{alerts_ever} qualifying alert(s) ever."),
        "next_action": (f"Next Trump sweep ~{fmt_time(next_sweep)} · "
                        f"next reminder {fmt_time(nxt)}" if next_sweep else
                        f"Next reminder {fmt_time(nxt)}"),
        "needs_you": None,
    }

    # --- George (keeper): Grind & Gather store, Shopify only.
    # Jaden Nov 11 ~16:58 ET: "make george just sit waiting till we have
    # the launch date" — date rule, not a hardcoded status. Before the
    # Nov 27 launch he waits (on the shop sofa); on/after launch his
    # open items surface as needs-you again. Items stay recorded in the
    # detail text either way so nothing is lost.
    launch_reached = now.date() >= LAUNCH_DATE
    keeper = {
        "id": "keeper",
        "name": "George",
        "role": "Grind & Gather store — Shopify only: product, discount, policies, payments, launch",
        "status": "needs-you" if (launch_reached and KEEPER_OPEN_ITEMS) else "waiting",
        "status_reason": (
            f"{len(KEEPER_OPEN_ITEMS)} decision(s) waiting on Jaden."
            if launch_reached else
            "Waiting for launch — Nov 27, 2026. "
            f"{len(KEEPER_OPEN_ITEMS)} launch item(s) parked until then."),
        "schedule": "No fixed schedule — acts when Jaden decides; launch target Black Fri Nov 27",
        "last_action": KEEPER_LAST_ACTION,
        "next_action": (
            "Remove the store password at launch, then place a test order."
            if launch_reached else
            "Launch Nov 27, 2026 — then: social links (needs Jaden's handles); "
            "remove the store password, then place a test order."),
        "needs_you": KEEPER_OPEN_ITEMS if launch_reached else None,
    }

    # --- Frank (ledger): trade journal — looks back for logs himself; a day
    # with no log means Jaden probably didn't trade, so nothing waits on him.
    frank_working = weekday == 4 and in_window(now, 17, 45, 18, 45)
    ledger = {
        "id": "ledger",
        "name": "Frank",
        "role": "Trade journal + Lucid account buffers — looks back for logs himself; a day with no log means Jaden probably didn't trade",
        "status": "working" if frank_working else "waiting",
        "status_reason": ("Weekly review in progress — tallying the logged trades."
                          if frank_working else
                          "Between reviews — a day with no log means Jaden probably didn't trade."),
        "schedule": "Weekly review Fridays 5:45 PM ET",
        "last_action": LEDGER_LAST_ACTION,
        "next_action": "Weekly review Fri Nov 13, 5:45 PM ET.",
        "needs_you": None,
        "stats": {
            "last_logged_trade": journal_last,
            "lucid_lfe_buffer_usd": 1471,
            "lucid_lde_buffer_usd": 105,
        },
    }

    # --- Muse: Jaden's assistant — always at his desk in the office at the
    # end of the hallway, typing. Waiting bots sit on the couches; a bot
    # that needs Jaden comes to sit in one of Muse's guest chairs.
    muse = {
        "id": "muse",
        "name": "Muse",
        "role": "Jaden's assistant — answers, builds, and runs the office",
        "status": "working",
        "status_reason": "Always on — typing at the desk in the office at the end of the hallway.",
        "schedule": "Always on",
        "last_action": "Reworked the office — waiting bots take the couches, needs-you bots come to the guest chairs.",
        "next_action": "On call whenever Jaden (or a bot) needs help.",
        "needs_you": None,
    }

    # --- Clip 1/2/3: the new YouTube/clipping room at the back end of the
    # hallway. Clip 1 is Rob — assigned by Jaden Nov 11 ~16:51 ET as the
    # viral ideas scout, so he works at his desk. Clip 2 is Jane — assigned
    # Nov 11 ~16:54 ET to make the videos, working at her desk. Clip 3 is
    # Flea — the fixer, assigned Nov 11 ~18:12 ET to fix finished videos
    # and crisp them up (renamed Flea Nov 11 ~18:21 ET), working at his desk.
    clips = []
    for i in (1, 2, 3):
        if i == 1:
            # Rob — viral ideas scout (Jaden, Nov 11 ~16:51 ET): finds only
            # viral explainer-video ideas on Instagram that haven't been
            # done yet, and sends the best finds to Jane (clip2). Working
            # at his desk.
            clips.append({
                "id": "clip1",
                "name": "Rob",
                "role": "Viral ideas scout — finds explainer-video ideas on Instagram that haven't been done yet, and sends the best finds to Jane",
                "status": "working",
                "status_reason": "On the job — hunting viral explainer-video ideas on Instagram that haven't been done yet, and passing the best finds to Jane.",
                "schedule": "Always on — scouting Instagram for fresh explainer ideas",
                "last_action": "Assigned by Jaden Wed Nov 11 — now scouting Instagram for viral explainer-video ideas that haven't been done yet, and sending the best finds to Jane.",
                "next_action": "Keep scouting Instagram for the next viral explainer idea to send Jane.",
                "needs_you": None,
            })
            continue
        if i == 2:
            # Jane — makes the videos (Jaden, Nov 11 ~16:54 ET): same style
            # of video as the viral explainer Rob finds, just with a
            # different idea. Rob sends her his best finds. Working at
            # her desk.
            clips.append({
                "id": "clip2",
                "name": "Jane",
                "role": "Makes the same style of video as the viral explainer Rob finds — just with a different idea",
                "status": "working",
                "status_reason": "On the job — making explainer videos in the style of Rob's viral finds, with fresh ideas.",
                "schedule": "Always on — making explainer videos from Rob's finds",
                "last_action": "Assigned by Jaden Wed Nov 11 — now making explainer videos in the style of Rob's viral finds, each with a different idea.",
                "next_action": "Make the next explainer video from Rob's latest find.",
                "needs_you": None,
            })
            continue
        if i == 3:
            # Flea (clip3) — the fixer (Jaden, Nov 11 ~18:12 ET; renamed
            # Flea Nov 11 ~18:21 ET): fixes finished videos and crisps them
            # up — fixes the sound, matches the style all the way through,
            # and adds a funny ending. First job: polish Jane's gum video
            # into a v2. Working at his desk.
            clips.append({
                "id": "clip3",
                "name": "Flea",
                "role": "Fixes finished videos and crisps them up — fixes the sound, matches the style all the way through, and adds a funny ending",
                "status": "working",
                "status_reason": "On the job — polishing Jane's gum video into a v2: fixing the sound, matching the style all the way through, and adding a funny ending.",
                "schedule": "Always on — fixing finished videos and crisping them up",
                "last_action": "Assigned by Jaden Wed Nov 11 — now fixing finished videos and crisping them up; first job is Jane's gum video.",
                "next_action": "Polish Jane's gum video into a v2 — sound fix, style match, funny ending.",
                "needs_you": None,
            })
            continue
        clips.append({
            "id": f"clip{i}",
            "name": f"Clip {i}",
            "role": "YouTube / clipping — awaiting assignment from Jaden",
            "status": "waiting",
            "status_reason": "No jobs assigned yet — Jaden assigns them when the room is done.",
            "schedule": "No fixed schedule — awaiting assignment from Jaden",
            "last_action": "Clipping room opened Wed Nov 11 — three new bots awaiting assignments from Jaden.",
            "next_action": "Awaiting assignment from Jaden.",
            "needs_you": None,
        })

    bots = [scanner, paper_bot, bell, keeper, ledger, muse] + clips

    # --- Office log, newest first, all from real sources
    log = []
    if latest:
        lwr = latest.get("win_r")
        if latest.get("status") == "closed" and lwr is not None and lwr > 0:
            res_txt = (f"WIN +{lwr}R (+{latest.get('points')} pts, "
                       f"+${latest.get('points', 0) * 8:.0f} at 4 micros)")
        elif latest.get("status") == "closed" and lwr is not None and lwr < 0:
            res_txt = (f"LOSS {lwr}R ({latest.get('points')} pts, "
                       f"${latest.get('points', 0) * 8:.0f} at 4 micros)")
        else:
            res_txt = latest.get("outcome_detail", latest.get("status", ""))
        log.append({
            "time": latest.get("closed_at_et") or latest.get("detection_time_et"),
            "bot": "paper",
            "text": (f"{latest['id']} closed — {res_txt}. "
                     f"Wick went {latest.get('wick_beyond_stop_pts')} pts beyond the stop."),
        })
        log.append({
            "time": latest.get("detection_time_et"),
            "bot": "paper",
            "text": (f"{latest['id']} detected — {latest.get('direction')} "
                     f"{latest.get('track_label') or latest.get('model') or 'Nyam model'} "
                     f"{latest.get('source')}, CISD {latest.get('cisd_level')}, "
                     f"FVG {latest.get('zone', {}).get('bottom')}-{latest.get('zone', {}).get('top')}."),
        })
    if last_checked:
        log.append({
            "time": last_checked.strftime("%Y-%m-%d %H:%M ET"),
            "bot": "bell",
            "text": "Trump sweep — no qualifying market-moving statement, no alert.",
        })
    for t, bot_id, text in RECORDED_LOG:
        log.append({"time": t, "bot": bot_id, "text": text})

    def log_key(entry):
        dt = parse_et(entry["time"])
        return dt or datetime.min.replace(tzinfo=ET)

    log.sort(key=log_key, reverse=True)

    return {
        "generated_at_et": now.strftime("%Y-%m-%d %H:%M:%S ET"),
        "generated_at_utc": datetime.now().astimezone().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "office": "Jaden's Virtual Office",
        "note": ("Statuses are derived from each bot's real schedule and current "
                 "Eastern Time. Working means inside a real active window; "
                 "needs-you means a real decision is waiting on Jaden."),
        "bots": bots,
        "log": log[:12],
    }


def main():
    doc = build()
    out = HERE / "status.json"
    out.write_text(json.dumps(doc, indent=2))
    print(f"Wrote {out}")
    for b in doc["bots"]:
        print(f"  {b['name']:9s} {b['status']:10s} — {b['last_action'][:90]}")
    print(f"  log entries: {len(doc['log'])}")


if __name__ == "__main__":
    main()
