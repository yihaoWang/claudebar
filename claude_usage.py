#!/usr/bin/env python3
"""Claude Usage Monitor - macOS menu bar app showing Claude plan usage limits."""

import json
from datetime import datetime, timezone
from pathlib import Path

import browser_cookie3
import requests
import rumps
from AppKit import (
    NSMutableAttributedString,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSRightTextAlignment,
    NSTextTab,
)

CONFIG_PATH = Path.home() / ".claude_usage_config.json"
REFRESH_INTERVAL = 30  # seconds
CHROME_BASE = Path.home() / "Library/Application Support/Google/Chrome"

REQUIRED_HEADERS = {
    "anthropic-client-platform": "web_claude_ai",
    "anthropic-client-version": "1.0.0",
    "content-type": "application/json",
    "referer": "https://claude.ai/settings/usage",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
}

# (api_key, icon, full_label) — all three always shown in dropdown
STATS = [
    ("five_hour",        "⏺",  "Current Session"),
    ("seven_day",        "⬡",  "Weekly · All Models"),
    ("seven_day_sonnet", "✳",  "Weekly · Sonnet"),
]

# Default: which api_keys appear in the menu bar title
DEFAULT_TITLE_KEYS: set[str] = {"five_hour", "seven_day"}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f)


def find_claude_cookie_file() -> str | None:
    for cookie_file in CHROME_BASE.glob("*/Cookies"):
        try:
            jar = browser_cookie3.chrome(domain_name=".claude.ai", cookie_file=str(cookie_file))
            for cookie in jar:
                if cookie.name == "sessionKey":
                    return str(cookie_file)
        except Exception as e:
            print(f"Skipping {cookie_file}: {e}")
    return None


def get_claude_cookies(cookie_file: str) -> dict[str, str]:
    jar = browser_cookie3.chrome(domain_name=".claude.ai", cookie_file=cookie_file)
    return {c.name: c.value for c in jar}


def cookies_to_jar(cookies: dict[str, str]) -> requests.cookies.RequestsCookieJar:
    jar = requests.cookies.RequestsCookieJar()
    for name, value in cookies.items():
        jar.set(name, value, domain=".claude.ai")
    return jar


def fetch_usage(org_id: str, jar: requests.cookies.RequestsCookieJar) -> dict | None:
    url = f"https://claude.ai/api/organizations/{org_id}/usage"
    try:
        resp = requests.get(url, headers=REQUIRED_HEADERS, cookies=jar, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}"}
    except requests.RequestException as e:
        return {"error": str(e)}


def stat_icon(icon: str, percent: float) -> str:
    return "⚠️" if percent >= 80 else icon


def format_resets_at(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str).astimezone()
        now = datetime.now(timezone.utc).astimezone()
        delta = dt - now
        total_mins = int(delta.total_seconds() / 60)
        if total_mins < 60:
            return f"{total_mins}m"
        hours = total_mins // 60
        mins = total_mins % 60
        if hours < 24:
            return f"{hours}h {mins}m"
        return dt.strftime("%a %I:%M %p")
    except Exception:
        return ""


def parse_usage(data: dict) -> list[dict]:
    items = []
    for api_key, icon, full_label in STATS:
        entry = data.get(api_key)
        if not isinstance(entry, dict):
            continue
        pct = float(entry.get("utilization") or 0)
        resets_raw = entry.get("resets_at") or ""
        resets_str = format_resets_at(resets_raw) if resets_raw else ""
        items.append({
            "api_key": api_key,
            "icon": icon,
            "full_label": full_label,
            "percent": pct,
            "resets": resets_str,
        })
    return items



def set_menu_item_title_right_aligned(menu_item: rumps.MenuItem, title: str, tab_x: float = 280) -> None:
    para_style = NSMutableParagraphStyle.alloc().init()
    tab_stop = NSTextTab.alloc().initWithTextAlignment_location_options_(NSRightTextAlignment, tab_x, {})
    para_style.setTabStops_([tab_stop])
    attr_str = NSMutableAttributedString.alloc().initWithString_(title)
    attr_str.addAttribute_value_range_(NSParagraphStyleAttributeName, para_style, (0, len(title)))
    menu_item._menuitem.setAttributedTitle_(attr_str)


def make_menu_bar_title(items: list[dict], title_keys: set[str]) -> str:
    parts = [
        f"{i['icon']} {int(i['percent'])}%"
        for i in items
        if i["api_key"] in title_keys
    ]
    return "  ·  ".join(parts) if parts else "-- · --"


class ClaudeUsageApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("-- · --", quit_button=None)
        self.config = load_config()
        self._cookie_file: str | None = self.config.get("cookie_file")
        self._cached_items: list[dict] = []

        # Which stats to show in the menu bar title (persisted in config)
        saved_keys = self.config.get("title_keys")
        self._title_keys: set[str] = set(saved_keys) if saved_keys else set(DEFAULT_TITLE_KEYS)

        # Stat display rows (one label per stat, clickable to toggle menu bar presence)
        self._label_items: list[rumps.MenuItem] = []

        menu_items: list = []
        for api_key, icon, full_label in STATS:
            label_item = rumps.MenuItem(f"{icon} {full_label}", callback=self._toggle_title_key)
            label_item._api_key = api_key
            label_item.state = 1 if api_key in self._title_keys else 0
            self._label_items.append(label_item)
            menu_items.append(label_item)
            menu_items.append(None)

        self._updated_item = rumps.MenuItem("Updated: --:--", callback=None)
        menu_items += [
            self._updated_item,
            rumps.MenuItem("↺ Refresh", callback=self.refresh_now),
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self.menu = menu_items
        self.timer = rumps.Timer(self._timer_callback, REFRESH_INTERVAL)
        self.timer.start()

    def _timer_callback(self, timer):
        self._do_refresh()

    def _toggle_title_key(self, sender: rumps.MenuItem) -> None:
        api_key = sender._api_key
        if api_key in self._title_keys:
            self._title_keys.discard(api_key)
            sender.state = 0
        else:
            self._title_keys.add(api_key)
            sender.state = 1
        self.config["title_keys"] = list(self._title_keys)
        save_config(self.config)
        if self._cached_items:
            self.title = make_menu_bar_title(self._cached_items, self._title_keys)

    def _do_refresh(self) -> None:
        if not self._cookie_file:
            self._cookie_file = find_claude_cookie_file()
            if self._cookie_file:
                self.config["cookie_file"] = self._cookie_file
                save_config(self.config)

        if not self._cookie_file:
            self.title = "☁️ ?"
            self._label_items[0].title = "No Chrome session found"
            return

        try:
            cookies = get_claude_cookies(self._cookie_file)
        except Exception as e:
            self.title = "☁️ Err"
            self._label_items[0].title = f"Cookie error: {e}"
            return

        org_id = self.config.get("org_id") or cookies.get("lastActiveOrg")
        if not org_id:
            self.title = "☁️ ?"
            self._label_items[0].title = "Org ID not found"
            return

        if not self.config.get("org_id"):
            self.config["org_id"] = org_id
            save_config(self.config)

        jar = cookies_to_jar(cookies)
        data = fetch_usage(org_id, jar)

        if data is None or "error" in data:
            err = data.get("error", "No response") if data else "No response"
            self.title = "☁️ Err"
            self._label_items[0].title = f"⚠️ {err[:60]}"
            return

        items = parse_usage(data)
        self._cached_items = items
        self.title = make_menu_bar_title(items, self._title_keys)

        for idx, item in enumerate(items):
            pct = item["percent"]
            icon = stat_icon(item["icon"], pct)
            resets = f"  ↻ {item['resets']}" if item["resets"] else ""
            title = f"{icon} {item['full_label']}\t{int(pct)}%{resets}"
            set_menu_item_title_right_aligned(self._label_items[idx], title)
            self._label_items[idx].state = 1 if item["api_key"] in self._title_keys else 0

        self._updated_item.title = f"Updated: {datetime.now().strftime('%H:%M')}"

    @rumps.clicked("↺ Refresh")
    def refresh_now(self, _: rumps.MenuItem) -> None:
        self._do_refresh()


if __name__ == "__main__":
    ClaudeUsageApp().run()
