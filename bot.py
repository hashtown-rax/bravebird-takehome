"""
Sauce Demo checkout bot.

Core logic is in run_bot() — used by both the CLI and the Django web UI.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).parent / ".env")

SITE_URL = "https://www.saucedemo.com"
LOGIN_TIMEOUT = 30_000  # 30s — enough for performance_glitch_user's slow login


# --- Core bot logic ---


def login(page, username, password, on_log=print):
    """Navigate to the login page, fill credentials, and wait for the inventory page."""
    page.goto(SITE_URL)
    page.fill("#user-name", username)
    page.fill("#password", password)
    page.click("#login-button")

    # Check for login error message before waiting for navigation
    error_element = page.query_selector("[data-test='error']")
    if error_element:
        raise RuntimeError(f"Login failed: {error_element.inner_text()}")

    page.wait_for_url("**/inventory.html", timeout=LOGIN_TIMEOUT)
    on_log(f"Logged in as {username}")


def scrape_all_products(page):
    """Scrape every product's name, description and price from the inventory page."""
    page.wait_for_selector(".inventory_item")
    product_cards = page.query_selector_all(".inventory_item")

    products = []
    for card in product_cards:
        name = card.query_selector(".inventory_item_name").inner_text()
        description = card.query_selector(".inventory_item_desc").inner_text()
        price_text = card.query_selector(".inventory_item_price").inner_text()
        price = float(price_text.replace("$", ""))
        products.append({"name": name, "description": description, "price": price})

    return products


def add_items_to_cart(page, shopping_list, products, on_log=print):
    """Try to add each item in the shopping list to the cart.
    Returns (added_items, not_found_items).
    """
    available_product_names = {product["name"] for product in products}
    added_items = []
    not_found_items = []

    for item_name in shopping_list:
        if item_name not in available_product_names:
            on_log(f"Item not found: {item_name}")
            not_found_items.append(item_name)
            continue

        product_cards = page.query_selector_all(".inventory_item")
        for card in product_cards:
            if card.query_selector(".inventory_item_name").inner_text() == item_name:
                card.query_selector("button").click()
                on_log(f"Added to cart: {item_name}")
                added_items.append(item_name)
                break

    return added_items, not_found_items


def fill_checkout_form(page, customer):
    """Navigate from cart to checkout, fill the customer form, and continue."""
    page.click(".shopping_cart_link")
    page.wait_for_url("**/cart.html")

    page.click("#checkout")
    page.wait_for_url("**/checkout-step-one.html")

    page.fill("#first-name", customer["first_name"])
    page.fill("#last-name", customer["last_name"])
    page.fill("#postal-code", customer["zip"])
    page.click("#continue")
    page.wait_for_url("**/checkout-step-two.html")


def read_checkout_totals(page):
    """Read the item total, tax, and grand total from the checkout overview page."""
    item_total_text = page.locator(".summary_subtotal_label").inner_text()
    tax_text = page.locator(".summary_tax_label").inner_text()
    grand_total_text = page.locator(".summary_total_label").inner_text()

    item_total = float(item_total_text.split("$")[1])
    tax = float(tax_text.split("$")[1])
    grand_total = float(grand_total_text.split("$")[1])
    return item_total, tax, grand_total


def verify_item_total(page_item_total, products, added_items):
    """Check that the page's item total matches the sum of added product prices."""
    expected_total = round(
        sum(product["price"] for product in products if product["name"] in added_items),
        2,
    )
    if abs(page_item_total - expected_total) > 0.001:
        raise ValueError(
            f"Item total mismatch: page shows ${page_item_total}, "
            f"expected ${expected_total} from product prices"
        )


def complete_order(page):
    """Click Finish and wait for the confirmation page."""
    page.click("#finish")
    page.wait_for_selector(".complete-header")


def run_bot(username, password, shopping_list, customer, output_dir, headed=False, on_log=print):
    """
    Run the full checkout flow.

    Returns a dict with:
      - result: status, totals, items_not_found, error
      - products: all scraped products
      - added: items that were added to the cart
      - logs: list of log messages
      - customer: the customer details used
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    logs = []

    def log(message):
        logs.append(message)
        on_log(message)

    result = {
        "status": "failed",
        "item_total": None,
        "tax": None,
        "total": None,
        "items_not_found": [],
        "error": None,
    }
    products = []
    added_items = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        page = browser.new_page()

        try:
            log("Step 1/5: Logging in...")
            login(page, username, password, on_log=log)

            log("Step 2/5: Scraping products...")
            products = scrape_all_products(page)
            with open(output_dir / "products.json", "w") as products_file:
                json.dump(products, products_file, indent=2)
            log(f"Found {len(products)} products")

            log("Step 3/5: Adding items to cart...")
            added_items, not_found_items = add_items_to_cart(
                page, shopping_list, products, on_log=log
            )
            result["items_not_found"] = not_found_items

            if not added_items:
                raise RuntimeError("No items were added to the cart")

            log("Step 4/5: Checkout and verifying totals...")
            fill_checkout_form(page, customer)
            item_total, tax, grand_total = read_checkout_totals(page)
            result["item_total"] = item_total
            result["tax"] = tax
            result["total"] = grand_total
            verify_item_total(item_total, products, added_items)
            log(f"Totals verified — subtotal: ${item_total}, tax: ${tax}, total: ${grand_total}")

            log("Step 5/5: Finishing order...")
            complete_order(page)
            screenshot_path = output_dir / "confirmation.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            log("Order complete — screenshot saved")

            result["status"] = "success"

        except Exception as error:
            result["error"] = str(error)
            log(f"FAILED: {error}")

        finally:
            with open(output_dir / "result.json", "w") as result_file:
                json.dump(result, result_file, indent=2)
            browser.close()

    return {
        "result": result,
        "products": products,
        "added": added_items,
        "logs": logs,
        "customer": customer,
    }


# --- CLI entry point ---

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def run_cli():
    parser = argparse.ArgumentParser(description="Sauce Demo checkout bot")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    args = parser.parse_args()

    username = os.environ.get("SAUCE_USERNAME")
    password = os.environ.get("SAUCE_PASSWORD")

    if not username or not password:
        print(f"  {RED}Error: SAUCE_USERNAME and SAUCE_PASSWORD environment variables are required.{RESET}")
        print(f"  {DIM}Example: SAUCE_USERNAME=standard_user SAUCE_PASSWORD=secret_sauce python3 bot.py{RESET}")
        return 1

    output_dir = Path(__file__).parent

    with open(output_dir / "input.json") as input_file:
        input_data = json.load(input_file)

    def cli_log(message):
        if message.startswith("Step"):
            print(f"  {CYAN}{message}{RESET}")
        elif message.startswith("FAILED"):
            print(f"  {RED}{message}{RESET}", file=sys.stderr)
        elif "not found" in message.lower():
            print(f"    {YELLOW}WARN{RESET} {message}")
        else:
            print(f"    {GREEN}OK{RESET} {message}")

    print(f"\n  {BOLD}Sauce Demo Bot{RESET} {DIM}({username}){RESET}\n")

    data = run_bot(
        username=username,
        password=password,
        shopping_list=input_data["items"],
        customer=input_data["customer"],
        output_dir=output_dir,
        headed=args.headed,
        on_log=cli_log,
    )

    run_result = data["result"]
    print()
    print(f"  {BOLD}{'=' * 44}{RESET}")
    status_color = GREEN if run_result["status"] == "success" else RED
    print(f"  Status:      {status_color}{BOLD}{run_result['status'].upper()}{RESET}")
    if run_result["item_total"] is not None:
        print(f"  Item total:  ${run_result['item_total']:.2f}")
        print(f"  Tax:         ${run_result['tax']:.2f}")
        print(f"  Total:       {BOLD}${run_result['total']:.2f}{RESET}")
    if run_result["items_not_found"]:
        print(f"  Not found:   {YELLOW}{', '.join(run_result['items_not_found'])}{RESET}")
    if run_result["error"]:
        print(f"  Error:       {RED}{run_result['error']}{RESET}")
    print(f"  {'=' * 44}\n")

    return 0 if run_result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(run_cli())
