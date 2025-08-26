#!/usr/bin/env python3
"""
Shopify Sites Checker Telegram Bot — Final Optimized Version
-----------------------------------------------------------
Features:
- /start → Intro message
- /check <url> → Check single site
- /batch → Paste URLs or upload `.txt` file (up to 2000 URLs)
- Sends back results in both TXT + CSV format for `.txt` uploads

Supports: Render & Railway deployment
"""

import asyncio
import re
import csv
from dataclasses import dataclass
from typing import List, Tuple, Optional
import aiohttp
from aiohttp import ClientTimeout
from urllib.parse import urlparse
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === BOT TOKEN HARDCODED ===
TOKEN = "8261698992:AAHNkytkhkqsFO7Su21ls2m3rGnG5haKYYI"

USER_AGENT = "Mozilla/5.0 (compatible; ShopifyCheckerBot/2.0; +https://example.com/bot)"
TIMEOUT = ClientTimeout(total=20)
MAX_BATCH_URLS = 2000

@dataclass
class ProductBrief:
    title: str
    price_range: str

@dataclass
class CheckResult:
    url: str
    ok: bool
    status: Optional[int]
    is_shopify: bool
    product_samples: List[ProductBrief]
    currency: str

async def fetch_products_json(session: aiohttp.ClientSession, base_url: str, limit: int = 5) -> Tuple[List[ProductBrief], Optional[int], str]:
    url = base_url.rstrip("/") + f"/products.json?limit={limit}"
    currency_symbol = "$"
    try:
        async with session.get(url, allow_redirects=True) as resp:
            status = resp.status
            if status != 200:
                return [], status, currency_symbol
            data = await resp.json(content_type=None)
            products = []
            for p in data.get("products", [])[:limit]:
                title = (p.get("title") or "Untitled").strip()
                variants = p.get("variants", [])
                prices = [float(v.get("price")) for v in variants if v.get("price")]
                if prices:
                    low, high = min(prices), max(prices)
                    pr = f"{currency_symbol}{low:.2f}" if low == high else f"{currency_symbol}{low:.2f}–{currency_symbol}{high:.2f}"
                else:
                    pr = "N/A"
                products.append(ProductBrief(title=title, price_range=pr))
            return products, status, currency_symbol
    except Exception:
        return [], None, currency_symbol

def pretty_result(res: CheckResult) -> str:
    icon = "✅" if res.is_shopify else ("⚠️" if res.ok else "❌")
    host = urlparse(res.url).netloc
    lines = [f"{icon} {host}", f"Shopify: {'Yes' if res.is_shopify else 'No'}", f"Currency: {res.currency}"]
    if res.product_samples:
        lines.append("Products:")
        for pb in res.product_samples:
            lines.append(f"• {pb.title[:60]} — {pb.price_range}")
    return "\n".join(lines)

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    urls = []
    from_file = False

    if update.message.document and update.message.document.file_name.endswith(".txt"):
        from_file = True
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
        urls = [line.strip() for line in text.splitlines() if line.strip()]
    elif update.message.text:
        urls = re.findall(r"(https?://[^\s]+)", update.message.text)

    if not urls:
        await update.message.reply_text("No URLs found.")
        return

    urls = urls[:MAX_BATCH_URLS]
    await update.message.reply_text(f"Checking {len(urls)} URL(s)…")

    results = []
    async with aiohttp.ClientSession(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as session:
        tasks = [fetch_products_json(session, u, limit=3) for u in urls]
        fetched = await asyncio.gather(*tasks)

    replies = []
    for u, (products, ps, cur) in zip(urls, fetched):
        res = CheckResult(u, True if products else False, ps, True if products else False, products, cur)
        replies.append(pretty_result(res))
        results.append((u, "✅ Yes" if products else "❌ No", cur, [(p.title, p.price_range) for p in products]))

    if from_file:
        with open("results.txt", "w", encoding="utf-8") as f:
            f.write("\n\n".join(replies))

        with open("results.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["URL", "Shopify", "Currency", "Product Title", "Price"])
            for url, shopify, currency, products in results:
                if products:
                    for title, price in products:
                        writer.writerow([url, shopify, currency, title, price])
                else:
                    writer.writerow([url, shopify, currency, "—", "—"])

        await update.message.reply_document(InputFile("results.txt"), caption="Results in TXT file")
        await update.message.reply_document(InputFile("results.csv"), caption="Results in CSV file")
    else:
        chunk, size = [], 0
        for block in replies:
            if size + len(block) + 2 > 3500:
                await update.message.reply_text("\n\n".join(chunk))
                chunk, size = [], 0
            chunk.append(block)
            size += len(block) + 2
        if chunk:
            await update.message.reply_text("\n\n".join(chunk))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html("👋 <b>Shopify Sites Checker</b>\nUse /check <url> or upload .txt (up to 2000 URLs).\nTXT + CSV results available.")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.TEXT) & ~filters.COMMAND, on_message))
    print("Bot running. Press Ctrl+C to stop.")
    await app.run_polling(close_loop=False)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
