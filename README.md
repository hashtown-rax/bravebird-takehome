# Sauce Demo Checkout Bot

Automated checkout bot for [saucedemo.com](https://www.saucedemo.com) using Python and Playwright.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Credentials

Copy the example env file and fill in the values:

```bash
cp .env.example .env
```

The bot reads `SAUCE_USERNAME` and `SAUCE_PASSWORD` from the `.env` file (or from environment variables). It will not run without them.

## Running — CLI

```bash
python3 bot.py

# Watch the bot work in a visible browser
python3 bot.py --headed

# Override the user via env var
SAUCE_USERNAME=performance_glitch_user python3 bot.py
```

Edit `input.json` to change the shopping list or customer details.

## Running — Web UI

```bash
python3 manage.py runserver
```

Open http://localhost:8000 — select a user role, configure the shopping list and customer details, then hit **Run Bot**. The role dropdown overrides the username; the password is always read from `.env`.

## Output

| File                | Contents                                           |
|---------------------|----------------------------------------------------|
| `products.json`     | All products scraped from the inventory page        |
| `confirmation.png`  | Screenshot of the order confirmation page           |
| `result.json`       | Run status, totals, missing items, errors           |

## Scaling to 40 different websites

To run this against many sites with different UIs, I'd make three changes:

1. **Site config files** — Extract selectors and URLs into per-site YAML/JSON configs (e.g. `sites/saucedemo.yaml`). The bot reads a config and uses those selectors instead of hardcoded ones. This keeps one bot engine with swappable site definitions.

2. **Parallel execution** — Use `pytest-playwright` or a task runner like Celery to launch runs concurrently, each with its own browser context. 40 sequential runs are slow; 40 parallel ones finish in roughly the time of the slowest single run.

3. **Resilience and reporting** — Add retries with backoff for flaky page loads, structured logging per site, and a summary report that aggregates results across all 40 runs so failures are easy to spot.
