"""
EMERGENCY DEMO — one-shot WhatsApp send via direct send URL.
Temporary hack: fresh Chrome, QR login, open send link, click Send. No reuse.
"""

import logging
import threading
import time
import urllib.parse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from app.config import Settings

logger = logging.getLogger(__name__)

# Hardcoded demo target (India +91)
DEMO_PHONE = "917013361752"
LOGIN_WAIT_SECONDS = 300
MAX_URL_TEXT_LEN = 3500

_SEND_BUTTON_LOCATORS: list[tuple[str, str]] = [
    (By.XPATH, '//button[@aria-label="Send"]'),
    (By.XPATH, '//span[@data-icon="send"]/ancestor::button'),
    (By.CSS_SELECTOR, 'button[aria-label="Send"]'),
    (By.CSS_SELECTOR, 'span[data-icon="send"]'),
    (By.XPATH, '//div[@role="button"]//span[@data-icon="send"]'),
]


class WhatsAppServiceError(Exception):
    pass


class WhatsAppService:
    """Demo-only: one fresh Chrome per send, direct wa.me/send URL, click Send."""

    def __init__(self, settings: Settings) -> None:
        self._lock = threading.Lock()

    def _format_message(self, sender: str, subject: str, date: str, body: str) -> str:
        text = (
            "🚨 NEW PLACEMENT ALERT\n\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Date: {date}\n\n"
            f"FULL EMAIL:\n{body}"
        )
        if len(text) > MAX_URL_TEXT_LEN:
            text = text[: MAX_URL_TEXT_LEN - 20] + "\n...(truncated)"
        return text

    def _launch_chrome(self) -> webdriver.Chrome:
        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--remote-allow-origins=*")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(90)
        driver.implicitly_wait(0)
        return driver

    def _wait_for_qr_login(self, driver: webdriver.Chrome) -> None:
        logger.info(">>> Scan QR code in the Chrome window (demo) <<<")
        try:
            WebDriverWait(driver, LOGIN_WAIT_SECONDS).until(
                lambda d: bool(
                    d.find_elements(By.CSS_SELECTOR, "#pane-side")
                    or d.find_elements(By.CSS_SELECTOR, 'motion-content')
                    or d.find_elements(By.CSS_SELECTOR, 'motion-content motion')
                )
            )
            logger.info("WhatsApp logged in")
            time.sleep(2)
        except TimeoutException as exc:
            raise WhatsAppServiceError(
                "QR login timed out. Scan QR in Chrome and try POST /check again."
            ) from exc

    def _click_send(self, driver: webdriver.Chrome) -> None:
        for by, selector in _SEND_BUTTON_LOCATORS:
            try:
                btn = WebDriverWait(driver, 45).until(
                    EC.element_to_be_clickable((by, selector))
                )
                btn.click()
                logger.info("Clicked Send")
                time.sleep(2)
                return
            except TimeoutException:
                continue
        raise WhatsAppServiceError("Send button not found on WhatsApp page")

    def send_placement_alert(
        self,
        sender: str,
        subject: str,
        date: str,
        body: str,
    ) -> list[str]:
        """Open fresh Chrome, login once, open send URL, click Send, close Chrome."""
        with self._lock:
            driver: webdriver.Chrome | None = None
            try:
                message = self._format_message(sender, subject, date, body)
                encoded = urllib.parse.quote(message, safe="")
                send_url = (
                    f"https://web.whatsapp.com/send?phone={DEMO_PHONE}&text={encoded}"
                )

                logger.info("Launching fresh Chrome for demo send to %s", DEMO_PHONE)
                driver = self._launch_chrome()

                driver.get("https://web.whatsapp.com")
                time.sleep(3)
                self._wait_for_qr_login(driver)

                logger.info("Opening pre-filled send URL")
                driver.get(send_url)
                time.sleep(5)

                self._click_send(driver)
                return ["demo-sent"]

            except WhatsAppServiceError:
                raise
            except (WebDriverException, OSError) as exc:
                raise WhatsAppServiceError(f"Demo send failed: {exc}") from exc
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except WebDriverException:
                        pass
                    logger.info("Chrome closed")

    def startup(self) -> None:
        """No-op for demo — browser opens only when sending."""

    def shutdown(self) -> None:
        pass

    @property
    def is_ready(self) -> bool:
        return False

    @property
    def in_cooldown(self) -> bool:
        return False
