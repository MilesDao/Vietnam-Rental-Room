import time
import logging
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

class BrowserFetcher:
    def __init__(self, headless=True):
        log.info("Starting Playwright...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 (research crawler; contact: trungdao131105@gmail.com)"
        )
        self.page = self.context.new_page()
        # Batdongsan has aggressive blocking. Sometimes stealth is needed, 
        # but playwright default with a good UA often works for initial load.
        
    def get(self, url: str, wait_for_selector: str = None) -> str:
        log.info(f"Browser fetching: {url}")
        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait 15 seconds for cloudflare/captcha so user can manually pass it in headed mode
            time.sleep(15)
            
            if wait_for_selector:
                try:
                    self.page.wait_for_selector(wait_for_selector, timeout=10000)
                except:
                    pass
                
            # If still navigating, wait a bit more
            try:
                self.page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass
                
            return self.page.content()
        except Exception as e:
            log.error(f"Error fetching {url} with browser: {e}")
            # Try getting content one last time
            try:
                time.sleep(2)
                return self.page.content()
            except:
                return ""
            
    def close(self):
        try:
            self.context.close()
            self.browser.close()
            self.playwright.stop()
        except:
            pass
