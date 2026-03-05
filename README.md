# claudebar

A macOS menu bar app that displays your Claude.ai plan usage in real time.

![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- Shows current session and weekly usage in the menu bar
- Color-coded indicators: green / yellow / red based on usage percentage
- Displays time until each limit resets
- Configurable which stats appear in the menu bar title
- Auto-refreshes every 30 seconds

## Requirements

- macOS
- Google Chrome with an active claude.ai session
- Python 3.11+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
python claude_usage.py
```

## Finding your Chrome profile

claudebar scans all profiles under:

```
~/Library/Application Support/Google/Chrome/
```

To find which profile you use for claude.ai:

1. Open Chrome and go to `chrome://version`
2. Look at the **Profile Path** field, e.g. `…/Chrome/Profile 3`
3. The app will auto-detect the correct profile on first run

If auto-detection fails, you can manually set `cookie_file` in `~/.claude_usage_config.json`:

```json
{
  "cookie_file": "/Users/<you>/Library/Application Support/Google/Chrome/Profile 3/Cookies"
}
```

## How it works

claudebar reads the `sessionKey` cookie directly from your Chrome profile and calls the Claude.ai usage API. No credentials are stored in the project — all runtime state is saved to `~/.claude_usage_config.json`.

## Config

`~/.claude_usage_config.json` is auto-generated on first run and stores:

- `org_id` — your Claude organization ID
- `cookie_file` — path to the Chrome cookie file in use
- `title_keys` — which stats to show in the menu bar
