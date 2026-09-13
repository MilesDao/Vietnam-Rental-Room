"""Crawler orchestration: browser launch, auth gate, scroll loop, safety stops.

This module owns *navigation and control flow* only. It does not contain
Facebook DOM selectors — those live in ``parser.py``. It calls into
``parser`` for extraction and ``exporter`` for storage.

Run with::

    python -m src.crawler --config config.yaml
    python -m src.crawler --config config.yaml --max-posts 20
    python -m src.crawler --config config.yaml --inspect
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import exporter, parser, utils

# Substrings that indicate Facebook is challenging us. If any appears in the
# page URL or visible text we STOP immediately (never attempt to bypass).
_SAFETY_SIGNALS = [
    "captcha",
    "/checkpoint/",
    "checkpoint required",
    "confirm your identity",
    "we need to confirm",
    "suspicious",
    "unusual activity",
    "temporarily blocked",
    "you're temporarily blocked",
    "you’re temporarily blocked",
    "security check",
    "xác nhận danh tính",  # confirm identity (vi)
    "tạm thời bị chặn",     # temporarily blocked (vi)
    "hoạt động bất thường",  # unusual activity (vi)
]

# Substrings that indicate we are on a login/auth wall rather than the group.
_LOGIN_SIGNALS = [
    "/login",
    "log in to facebook",
    "log into facebook",
    "đăng nhập",
]


def load_config(path: str) -> dict[str, Any]:
    """Load YAML config and apply defaults for optional sections."""
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    cfg.setdefault("group_url", "https://web.facebook.com/groups/1164344644748784")
    cfg.setdefault("max_posts", 1000)
    crawl = cfg.setdefault("crawl", {})
    crawl.setdefault("save_every", 10)
    crawl.setdefault("max_scroll_without_new_posts", 10)
    crawl.setdefault("min_delay_seconds", 2)
    crawl.setdefault("max_delay_seconds", 5)
    # Keep only this many posts in the DOM (older extracted ones are detached)
    # to bound memory on long crawls and avoid renderer OOM crashes. 0 disables.
    crawl.setdefault("prune_dom_keep", 40)

    browser = cfg.setdefault("browser", {})
    browser.setdefault("user_data_dir", "./data/browser_profile")
    browser.setdefault("headless", False)
    browser.setdefault("page_load_timeout_ms", 60_000)
    # Which browser build backs the persistent profile. "chrome" uses the
    # system Google Chrome (Facebook keeps it logged in far more reliably than
    # Playwright's bundled Chromium). null -> bundled Chromium.
    browser.setdefault("channel", "chrome")
    # If set (e.g. "http://localhost:9222"), the crawler ATTACHES to a Chrome
    # YOU launched with --remote-debugging-port and logged into yourself,
    # instead of managing its own profile. Most reliable for Facebook, which
    # keeps a human-launched Chrome logged in. null -> managed profile mode.
    browser.setdefault("cdp_url", None)

    paths = cfg.setdefault("paths", {})
    paths.setdefault("posts_jsonl", "./data/posts.jsonl")
    paths.setdefault("posts_csv", "./data/posts.csv")
    paths.setdefault("checkpoint", "./data/checkpoints.json")
    paths.setdefault("validation_report", "./data/validation_report.md")
    paths.setdefault("log", "./logs/crawler.log")
    paths.setdefault("dom_sample", "./data/dom_sample.html")

    # Anchor every relative path to the CONFIG FILE's directory, not the
    # current working directory. This guarantees the browser profile (and all
    # data/log files) resolve to the SAME absolute location on every run, no
    # matter which folder you launch from — the fix for "logged in again".
    base = Path(path).resolve().parent
    for key, val in list(paths.items()):
        p = Path(str(val))
        if not p.is_absolute():
            paths[key] = str((base / p).resolve())
    udd = Path(str(browser["user_data_dir"]))
    if not udd.is_absolute():
        browser["user_data_dir"] = str((base / udd).resolve())
    return cfg


def _connect_cdp(pw, cdp_url: str, logger):
    """Connect to an existing Chrome over CDP, tolerant of localhost/IPv6.

    Chrome's --remote-debugging-port binds to IPv4 127.0.0.1, but "localhost"
    can resolve to IPv6 ::1 first (giving ECONNREFUSED). So we try the given
    URL, then a 127.0.0.1 variant, before failing with actionable guidance.
    """
    candidates = [cdp_url]
    if "localhost" in cdp_url:
        candidates.append(cdp_url.replace("localhost", "127.0.0.1"))
    last_exc: Exception | None = None
    for url in candidates:
        try:
            browser = pw.chromium.connect_over_cdp(url)
            if url != cdp_url:
                logger.info("CDP connected via %s (localhost -> 127.0.0.1)", url)
            return browser
        except Exception as exc:
            last_exc = exc
            logger.warning("CDP connect failed for %s: %s", url, exc)
    raise RuntimeError(
        f"Could not connect to Chrome DevTools at {cdp_url}.\n"
        "Start a debuggable Chrome FIRST (fully quit other Chrome windows, or\n"
        "the debug port is silently ignored):\n"
        '  google-chrome --remote-debugging-port=9222 '
        '--user-data-dir="$HOME/.fb-crawler-chrome"\n'
        "Verify it is listening:\n"
        "  curl http://127.0.0.1:9222/json/version\n"
        "Then set browser.cdp_url to http://127.0.0.1:9222 in config.yaml."
    ) from last_exc


def _open_context(pw, cfg: dict, logger, *, headless: bool):
    """Open the browser context used by every mode.

    Returns ``(context, cleanup, is_cdp)``:
    - ``cdp_url`` set  -> ATTACH to your existing Chrome over CDP (does not
      launch or close your browser; cleanup only disconnects).
    - otherwise        -> launch a persistent managed profile (same dir +
      channel every run, so a saved session is reused).
    """
    browser_cfg = cfg["browser"]

    cdp_url = browser_cfg.get("cdp_url")
    if cdp_url:
        logger.info("attaching to existing Chrome via CDP: %s", cdp_url)
        browser = _connect_cdp(pw, cdp_url, logger)
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        def cleanup() -> None:
            # Disconnect only — never close the user's own browser.
            try:
                browser.close()
            except Exception:
                pass

        return context, cleanup, True

    # --- managed persistent profile ---
    user_data_dir = browser_cfg["user_data_dir"]  # already absolute
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    logger.info("using browser profile: %s", user_data_dir)

    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    channel = browser_cfg.get("channel")
    if channel:
        launch_kwargs["channel"] = channel
    try:
        ctx = pw.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)
        if channel:
            logger.info("browser channel: %s", channel)
    except Exception as exc:
        if not channel:
            raise
        logger.warning(
            "channel=%s unavailable (%s); falling back to bundled Chromium. "
            "NOTE: if you logged in under a different channel, re-run --login.",
            channel, exc,
        )
        launch_kwargs.pop("channel", None)
        ctx = pw.chromium.launch_persistent_context(user_data_dir, **launch_kwargs)

    def cleanup() -> None:
        try:
            ctx.close()
        except Exception:
            pass

    return ctx, cleanup, False


def _open_page(context, is_cdp):
    """Pick the page to drive. In CDP mode open a fresh tab so we don't hijack
    one of your existing tabs; in managed mode reuse the blank startup page."""
    if is_cdp:
        return context.new_page()
    return context.pages[0] if context.pages else context.new_page()


class SafetyStop(Exception):
    """Raised when a CAPTCHA/checkpoint/block signal is detected."""


def _page_indicates(page, signals: list[str]) -> str | None:
    """Return the first matching signal found in the URL or visible body text."""
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    for sig in signals:
        if sig in url:
            return sig
    try:
        body = (page.inner_text("body", timeout=3_000) or "").lower()
    except Exception:
        body = ""
    for sig in signals:
        if sig in body:
            return sig
    return None


def _wait_for_manual_login(page, logger, timeout_s: int = 600) -> None:
    """If a login wall is detected, wait for the user to log in manually.

    The browser window stays open and we POLL the page until the login
    signals disappear (you've reached the feed) — no Enter key or interactive
    stdin required, so the window never closes out from under you. Continues
    automatically once you're logged in, or after ``timeout_s`` seconds.

    We never read, type, store, or log credentials.
    """
    if _page_indicates(page, _LOGIN_SIGNALS) is None:
        return  # already logged in
    logger.info("Login required — waiting for manual login (window stays open).")
    print(
        "\n" + "=" * 70 + "\n"
        "Facebook needs you to LOG IN.\n"
        "Log in MANUALLY in the Chromium window that just opened.\n"
        "The crawler will NOT read or store your password.\n"
        f"It will continue automatically once you reach the feed\n"
        f"(waiting up to {timeout_s // 60} minutes). Do not close the window.\n"
        + "=" * 70,
        file=sys.stderr,
    )
    import time as _time

    deadline = _time.time() + timeout_s
    clear_streak = 0
    while _time.time() < deadline:
        try:
            page.wait_for_timeout(2_000)  # 2s tick; keeps the window alive
        except Exception:
            break  # window/page gone
        if _page_indicates(page, _LOGIN_SIGNALS) is None:
            clear_streak += 1
            if clear_streak >= 2:  # two consecutive clean checks = logged in
                logger.info("Login detected — continuing.")
                return
        else:
            clear_streak = 0
    logger.warning("Manual-login wait timed out after %ss.", timeout_s)


def run_login(cfg: dict) -> str:
    """Dedicated one-time login step: open the browser, wait for manual login,
    persist the session to the profile, then exit. Run once before crawling.
    """
    from playwright.sync_api import sync_playwright

    logger = utils.setup_logger(cfg["paths"]["log"])
    logger.info("login step started")
    browser_cfg = cfg["browser"]

    with sync_playwright() as pw:
        context, cleanup, is_cdp = _open_context(pw, cfg, logger, headless=False)
        page = _open_page(context, is_cdp)
        page.set_default_timeout(int(browser_cfg["page_load_timeout_ms"]))
        page.goto("https://web.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3_000)
        _wait_for_manual_login(page, logger)
        if _page_indicates(page, _LOGIN_SIGNALS) is None:
            # Give Chrome a moment to flush session cookies to the profile
            # before we close, so the next run reuses them.
            page.wait_for_timeout(3_000)
            target = "your Chrome (CDP)" if is_cdp else browser_cfg["user_data_dir"]
            logger.info("Login confirmed in: %s", target)
            print("Login saved. You can now run the crawler.", file=sys.stderr)
            result = "logged_in"
        else:
            logger.warning("Still not logged in when the window closed.")
            result = "not_logged_in"
        if is_cdp:
            try:
                page.close()
            except Exception:
                pass
        cleanup()
    return result


def _wait_for_posts(page, logger, timeout_s: int = 30) -> bool:
    """Wait until real post articles render, nudge-scrolling to trigger the
    feed's lazy-load. A freshly navigated tab often shows only loading
    skeletons for a few seconds. Returns True once >=1 real post is present."""
    import time as _time

    deadline = _time.time() + timeout_s
    while _time.time() < deadline:
        try:
            n = page.evaluate(parser.COUNT_POSTS_JS)
        except Exception:
            n = 0
        if n and n > 0:
            logger.info("feed rendered: %d post(s) visible", n)
            return True
        try:
            page.evaluate("window.scrollBy(0, 1000);")
            page.wait_for_timeout(1_500)
        except Exception:
            break
    logger.warning("no posts rendered after %ss (feed may be slow/empty)", timeout_s)
    return False


def _extract_cycle(page, cfg, crawl_time: str, logger) -> list[dict]:
    """Expand 'See more', run extraction JS, normalize to canonical records."""
    try:
        clicked = page.evaluate(parser.EXPAND_SEE_MORE_JS)
        if clicked:
            page.wait_for_timeout(600)  # let expanded text re-layout
    except Exception as exc:
        logger.warning("See-more expansion failed: %s", exc)

    try:
        raw_posts = page.evaluate(parser.EXTRACT_POSTS_JS)
    except Exception as exc:
        logger.warning("Extraction JS failed this cycle: %s", exc)
        return []

    records: list[dict] = []
    group_url = cfg["group_url"]
    for raw in raw_posts:
        try:
            records.append(parser.normalize_raw_post(raw, group_url, crawl_time))
        except Exception as exc:  # skip malformed, never crash the crawl
            logger.warning("Skipping malformed post: %s", exc)
    return records


def run_inspect(page, cfg, logger) -> None:
    """Dump a DOM sample and print extracted records for offline selector work."""
    n = 5
    try:
        html_list = page.evaluate(parser.DUMP_ARTICLES_JS, n)
    except Exception as exc:
        logger.warning("DOM dump failed: %s", exc)
        html_list = []
    sample_path = Path(cfg["paths"]["dom_sample"])
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sep = "\n\n<!-- ===== NEXT ARTICLE ===== -->\n\n"
    sample_path.write_text(sep.join(html_list), encoding="utf-8")
    logger.info("Wrote %d article(s) DOM sample -> %s", len(html_list), sample_path)

    crawl_time = datetime.now(timezone.utc).isoformat()
    records = _extract_cycle(page, cfg, crawl_time, logger)
    logger.info("Extracted %d record(s) in inspect mode.", len(records))
    import json as _json

    print(_json.dumps(records, ensure_ascii=False, indent=2))


def crawl(cfg: dict, *, inspect: bool = False) -> str:
    """Main entry. Returns a stop-reason string ('done', 'max_posts', ...)."""
    # Lazy import so unit tests / CSV export work without Playwright installed.
    from playwright.sync_api import sync_playwright

    logger = utils.setup_logger(cfg["paths"]["log"])
    logger.info("crawler started")

    jsonl_path = cfg["paths"]["posts_jsonl"]
    checkpoint_path = cfg["paths"]["checkpoint"]

    existing = utils.load_jsonl(jsonl_path)
    known_keys = utils.build_known_keys(existing)
    unique_posts = len(existing)
    logger.info("loaded %d existing posts", unique_posts)

    max_posts = int(cfg["max_posts"])
    crawl_cfg = cfg["crawl"]
    save_every = int(crawl_cfg["save_every"])
    max_barren = int(crawl_cfg["max_scroll_without_new_posts"])
    min_delay = float(crawl_cfg["min_delay_seconds"])
    max_delay = float(crawl_cfg["max_delay_seconds"])
    prune_keep = int(crawl_cfg.get("prune_dom_keep", 40))

    browser_cfg = cfg["browser"]

    stop_reason = "done"
    last_post_url: str | None = existing[-1].get("post_url") if existing else None
    scroll_attempts = 0
    barren_scrolls = 0
    since_checkpoint = 0

    with sync_playwright() as pw:
        context, cleanup, is_cdp = _open_context(
            pw, cfg, logger, headless=bool(browser_cfg["headless"])
        )
        page = _open_page(context, is_cdp)
        page.set_default_timeout(int(browser_cfg["page_load_timeout_ms"]))
        # Facebook's virtualized feed only renders posts in the ACTIVE tab, so
        # a background CDP tab shows loading skeletons forever. Activate it.
        try:
            page.bring_to_front()
        except Exception:
            pass

        try:
            logger.info("navigating to group: %s", cfg["group_url"])
            page.goto(cfg["group_url"], wait_until="domcontentloaded")
            page.wait_for_timeout(3_000)

            # Auth gate.
            _wait_for_manual_login(page, logger)

            # Safety check right after landing.
            sig = _page_indicates(page, _SAFETY_SIGNALS)
            if sig:
                raise SafetyStop(sig)

            # Wait for the feed to actually render (skeletons -> real posts).
            _wait_for_posts(page, logger)

            if inspect:
                run_inspect(page, cfg, logger)
                return "inspect"

            # ---- scroll / extract loop ----
            while unique_posts < max_posts:
                sig = _page_indicates(page, _SAFETY_SIGNALS)
                if sig:
                    raise SafetyStop(sig)

                crawl_time = datetime.now(timezone.utc).isoformat()
                records = _extract_cycle(page, cfg, crawl_time, logger)
                logger.info("detected %d visible posts", len(records))

                new_batch: list[dict] = []
                for record in records:
                    key = utils.post_identity_key(record)
                    if key in known_keys:
                        continue
                    known_keys.add(key)
                    new_batch.append(record)
                    if record.get("post_url"):
                        last_post_url = record["post_url"]
                    if unique_posts + len(new_batch) >= max_posts:
                        break

                if new_batch:
                    exporter.append_posts(jsonl_path, new_batch)
                    unique_posts += len(new_batch)
                    since_checkpoint += len(new_batch)
                    barren_scrolls = 0
                    logger.info(
                        "extracted %d new posts | total unique posts: %d",
                        len(new_batch), unique_posts,
                    )
                else:
                    barren_scrolls += 1
                    logger.warning(
                        "no new posts after scroll %d/%d", barren_scrolls, max_barren
                    )

                if since_checkpoint >= save_every:
                    exporter.write_checkpoint(
                        checkpoint_path,
                        group_url=cfg["group_url"],
                        unique_posts=unique_posts,
                        last_post_url=last_post_url,
                        scroll_attempts=scroll_attempts,
                    )
                    since_checkpoint = 0
                    logger.info("checkpoint saved")

                if unique_posts >= max_posts:
                    stop_reason = "max_posts"
                    break
                if barren_scrolls >= max_barren:
                    stop_reason = "no_new_posts"
                    break

                # Prune already-extracted off-screen posts to bound memory
                # (prevents the renderer OOM/"Target crashed" on long crawls).
                if prune_keep and prune_keep > 0:
                    try:
                        removed = page.evaluate(parser.PRUNE_FEED_JS, prune_keep)
                        if removed:
                            logger.info("blanked %d media element(s) in old posts", removed)
                    except Exception as exc:
                        logger.warning("DOM prune failed: %s", exc)

                # Scroll down and wait a randomized human-readable delay.
                page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
                scroll_attempts += 1
                slept = utils.human_delay(min_delay, max_delay)
                logger.info("scrolled (attempt %d), slept %.1fs", scroll_attempts, slept)

        except SafetyStop as stop:
            stop_reason = "safety_signal"
            logger.warning("CRAWLER_STOP_REASON=safety_signal detail=%s", stop)
        except KeyboardInterrupt:
            stop_reason = "interrupted"
            logger.warning("CRAWLER_STOP_REASON=interrupted")
        except Exception as exc:  # unexpected: save progress, don't lose data
            stop_reason = "error"
            logger.warning("CRAWLER_STOP_REASON=error detail=%s", exc)
        finally:
            exporter.write_checkpoint(
                checkpoint_path,
                group_url=cfg["group_url"],
                unique_posts=unique_posts,
                last_post_url=last_post_url,
                scroll_attempts=scroll_attempts,
                stop_reason=stop_reason,
            )
            logger.info("checkpoint saved (final)")
            # Close our own tab in CDP mode so tabs don't accumulate in the
            # user's Chrome across runs (a leak that eventually wedges attach).
            if is_cdp:
                try:
                    page.close()
                except Exception:
                    pass
            cleanup()

    logger.info("crawl finished: stop_reason=%s total=%d", stop_reason, unique_posts)
    return stop_reason


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Facebook public group crawler (read-only).")
    ap.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    ap.add_argument("--max-posts", type=int, default=None, help="Override max_posts")
    ap.add_argument("--group-url", default=None, help="Override group_url")
    ap.add_argument("--login", action="store_true",
                    help="Open the browser to log in manually once, save the "
                         "session, then exit. Run this first.")
    ap.add_argument("--inspect", action="store_true",
                    help="Dump DOM sample + extracted JSON for one screen, then exit")
    ap.add_argument("--headless", action="store_true", help="Run browser headless")
    ap.add_argument("--no-export", action="store_true",
                    help="Skip CSV + validation report at the end")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.max_posts is not None:
        cfg["max_posts"] = args.max_posts
    if args.group_url is not None:
        cfg["group_url"] = args.group_url
    if args.headless:
        cfg["browser"]["headless"] = True

    if args.login:
        result = run_login(cfg)
        return 0 if result == "logged_in" else 1

    stop_reason = crawl(cfg, inspect=args.inspect)

    if not args.inspect and not args.no_export:
        rows = exporter.export_csv(cfg["paths"]["posts_jsonl"], cfg["paths"]["posts_csv"])
        stats = exporter.generate_validation_report(
            cfg["paths"]["posts_jsonl"],
            cfg["paths"]["validation_report"],
            cfg["group_url"],
        )
        print(f"Exported {rows} rows to CSV. Validation stats: {stats}", file=sys.stderr)

    # Non-zero exit only for genuine failure/safety stops so scripts can react.
    return 0 if stop_reason in {"done", "max_posts", "no_new_posts", "inspect"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
