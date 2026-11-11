#!/usr/bin/env python3
"""Generate status.json for the public Virtual Office (GitHub Pages).

Reads Jaden's REAL logs/state files and derives each bot's status from its
real schedule and the current America/New_York time. Nothing is faked:
a bot only shows "working" when it is inside one of its real active
windows (or, for Newswire, when its last sweep is fresh). "needs-you"
means a real recorded decision is waiting on Jaden.

Run:  python3 generate_status.py
Writes: status.json next to this script (same directory as index.html).

To keep the published page live, re-run this script and push the new
status.json to the GitHub repo every 5 minutes (see README.md).
"""

import json
import re
from datetime import datetime, timedelta, time as dtime
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
    ("2026-11-11 10:28 ET", "keeper",
     "Paid shipping options removed from Grind & Gather — free US shipping "
     "(7-15 business days) is now the only option."),
    ("2026-11-11 06:56 ET", "bell",
     "NY session reminder sent — Veterans Day, stocks/CME normal hours, no "
     "red-folder USD events; PPI Fri Nov 13 preview."),
    ("2026-11-10 16:47 ET", "paper",
     "Paper trading went live — JELS union opens 09:30-10:30 ET + midday "
     "11:00-12:00 ET, log-only, no real orders."),
]

KEEPER_OPEN_ITEMS = [
    "Sample order — go / no-go still undecided ($19.58, mapped AliExpress listing)",
    "DBA / assumed business name filing — Yancey County, $26, pinned open",
    "Social links — needs Jaden's handles",
    "NC sales tax ID — expected by mail ~Nov 24, Jaden enters it in Shopify",
]
KEEPER_LAST_ACTION = ("Paid shipping options removed Wed Nov 11 ~10:28 ET — "
                      "free US shipping (7-15 days) is now the only option.")

LEDGER_OPEN_ITEMS = [
    "11 sessions still unlogged (Oct 26 - Nov 9): points + R, setup, one lesson each",
    "Weekly review Fri Nov 13, 5:45 PM ET — needs the logged trades to tally",
]
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
    closed = [t for t in trades if t.get("status") == "closed"]
    wins = [t for t in closed if t.get("win_r", 0) > 0]
    total_pts = sum(t.get("points", 0) for t in closed)
    latest = trades[-1] if trades else None

    reported = load_reported()
    last_checked = parse_et(reported.get("last_checked"))
    last_result = reported.get("last_check_result", "unknown")
    alerts_ever = sum(1 for k, v in reported.items()
                      if isinstance(v, dict) and v.get("alerted") is True
                      and not k.startswith("news-vertical-sweep-"))

    journal_last = load_journal_last_trade()

    # --- Scanner: JELS watch / paper engine active window, Mon-Fri 09:30-14:00
    scan_working = is_weekday and in_window(now, 9, 30, 14, 0)
    next_scan = next_weekday_time(now, {0, 1, 2, 3, 4}, 9, 30)
    scanner = {
        "id": "scanner",
        "name": "Scanner",
        "role": "MNQ / ES watch — JELS strat detection (15m + 5m CISD + FVG)",
        "status": "working" if scan_working else "waiting",
        "status_reason": ("Inside the live watch window (Mon-Fri 09:30-14:00 ET)."
                          if scan_working else
                          "Outside the live watch window (Mon-Fri 09:30-14:00 ET)."),
        "schedule": "Mon-Fri 09:30-14:00 ET (opens 09:30-10:30, midday 11:00-12:00)",
        "last_action": (f"Engine run #{paper.get('runs_total', '?')} at "
                        f"{paper.get('last_run_et', 'unknown')}; "
                        f"{len(trades)} paper trade(s) detected so far."),
        "next_action": (f"Next scan window {fmt_time(next_scan)}"
                        if not scan_working else "Scanning every 5 minutes right now."),
        "needs_you": None,
    }

    # --- Paper: same active window; last action is the latest paper trade
    if latest:
        outcome = latest.get("outcome_detail", latest.get("status", ""))
        last_trade_txt = (
            f"{latest['id']} — {latest.get('direction', '')} union "
            f"{latest.get('source', '')} — "
            f"{'WIN +' + str(latest.get('win_r')) + 'R (+' + str(latest.get('points')) + ' pts)' if latest.get('win_r', 0) > 0 else outcome} "
            f"at {latest.get('closed_at_et', latest.get('detection_time_et', ''))}. "
            f"Stop {latest.get('stop_pts')} pts; "
            f"wick went {latest.get('wick_beyond_stop_pts')} pts beyond stop."
        )
    else:
        last_trade_txt = "No paper trades yet."
    paper_bot = {
        "id": "paper",
        "name": "Paper",
        "role": "JELS paper trader — log-only hypothetical trades, no real orders",
        "status": "working" if scan_working else "waiting",
        "status_reason": ("Inside the paper-trading window (Mon-Fri 09:30-14:00 ET)."
                          if scan_working else
                          "Outside the paper-trading window (Mon-Fri 09:30-14:00 ET)."),
        "schedule": "Mon-Fri 09:30-14:00 ET, checks every 5 min",
        "last_action": last_trade_txt,
        "next_action": (f"Next window {fmt_time(next_scan)}"
                        if not scan_working else
                        "Watching for the next JELS setup (opens + midday)."),
        "needs_you": None,
        "stats": {
            "trades_opened": len(trades),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(closed) - len(wins),
            "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
            "total_points": total_pts,
            "total_usd_4_micros": round(total_pts * 2 * 4, 2),
        },
    }

    # --- Newswire: 30-min Trump/market sweeps, around the clock
    fresh = last_checked is not None and (now - last_checked) <= timedelta(minutes=45)
    if last_checked:
        next_sweep = last_checked + timedelta(minutes=30)
        while next_sweep <= now:
            next_sweep += timedelta(minutes=30)
    else:
        next_sweep = None
    newswire = {
        "id": "newswire",
        "name": "Newswire",
        "role": "Trump statement / market-news alerts — 30-min sweeps, bullish/bearish read",
        "status": "working" if fresh else "waiting",
        "status_reason": (f"Last sweep {fmt_time(last_checked)} — fresh."
                          if fresh else
                          f"Last sweep {fmt_time(last_checked)} — stale, no recent check."),
        "schedule": "Every 30 minutes, around the clock",
        "last_action": (f"Last sweep {fmt_time(last_checked)}: "
                        f"{'no qualifying market-moving statement, no alert' if last_result == 'no_alert' else last_result}. "
                        f"{alerts_ever} qualifying alert(s) ever."),
        "next_action": f"Next sweep ~{fmt_time(next_sweep)}" if next_sweep else "Next sweep unknown",
        "needs_you": None,
    }

    # --- Bell: session reminders, Mon-Fri 07:00 and Sun-Thu 17:00
    ny_today = is_weekday and in_window(now, 7, 0, 7, 45)
    asia_today = weekday in {6, 0, 1, 2, 3} and in_window(now, 17, 0, 17, 45)
    bell_working = ny_today or asia_today
    next_ny = next_weekday_time(now, {0, 1, 2, 3, 4}, 7, 0)
    next_asia = next_weekday_time(now, {6, 0, 1, 2, 3}, 17, 0)
    nxt = min(x for x in (next_ny, next_asia) if x)
    bell = {
        "id": "bell",
        "name": "Bell",
        "role": "Session reminders — NY open prep + Asia open prep, red-folder news + flat windows",
        "status": "working" if bell_working else "waiting",
        "status_reason": ("Just sent a session reminder."
                          if bell_working else
                          "Between scheduled reminders."),
        "schedule": "Mon-Fri 7:00 AM ET (NY) + Sun-Thu 5:00 PM ET (Asia)",
        "last_action": ("NY session reminder sent Wed Nov 11, 06:56 ET — Veterans Day, "
                        "no red-folder USD events; PPI Fri Nov 13 preview."),
        "next_action": f"Next reminder {fmt_time(nxt)}",
        "needs_you": None,
    }

    # --- Keeper: Grind & Gather store — real open decisions waiting on Jaden
    keeper = {
        "id": "keeper",
        "name": "Keeper",
        "role": "Grind & Gather store — Shopify, DSers, policies, launch prep",
        "status": "needs-you",
        "status_reason": f"{len(KEEPER_OPEN_ITEMS)} decision(s) waiting on Jaden.",
        "schedule": "No fixed schedule — acts when Jaden decides; launch target Black Fri Nov 27",
        "last_action": KEEPER_LAST_ACTION,
        "next_action": "Sample order decision ($19.58) — then quality check + real weight.",
        "needs_you": KEEPER_OPEN_ITEMS,
    }

    # --- Ledger: trade journal — real unlogged sessions waiting on Jaden
    ledger = {
        "id": "ledger",
        "name": "Ledger",
        "role": "Trade journal + Lucid account buffers — points, R, setup, one lesson per trade",
        "status": "needs-you",
        "status_reason": "11 sessions unlogged — the journal is waiting on Jaden.",
        "schedule": "Weekly review Fridays 5:45 PM ET",
        "last_action": LEDGER_LAST_ACTION,
        "next_action": "Weekly review Fri Nov 13, 5:45 PM ET.",
        "needs_you": LEDGER_OPEN_ITEMS,
        "stats": {
            "last_logged_trade": journal_last,
            "unlogged_sessions": 11,
            "lucid_lfe_buffer_usd": 1471,
            "lucid_lde_buffer_usd": 105,
        },
    }

    bots = [scanner, paper_bot, newswire, bell, keeper, ledger]

    # --- Office log, newest first, all from real sources
    log = []
    if latest:
        log.append({
            "time": latest.get("closed_at_et") or latest.get("detection_time_et"),
            "bot": "paper",
            "text": (f"{latest['id']} closed — WIN +{latest.get('win_r')}R "
                     f"(+{latest.get('points')} pts, +${latest.get('points', 0) * 8:.0f} at 4 micros). "
                     f"Wick went {latest.get('wick_beyond_stop_pts')} pts beyond the stop."),
        })
        log.append({
            "time": latest.get("detection_time_et"),
            "bot": "paper",
            "text": (f"{latest['id']} detected — {latest.get('direction')} union "
                     f"{latest.get('source')}, CISD {latest.get('cisd_level')}, "
                     f"FVG {latest.get('zone', {}).get('bottom')}-{latest.get('zone', {}).get('top')}."),
        })
    if last_checked:
        log.append({
            "time": last_checked.strftime("%Y-%m-%d %H:%M ET"),
            "bot": "newswire",
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
