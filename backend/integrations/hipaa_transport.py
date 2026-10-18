import requests
import logging
import ssl
from typing import Any, Dict, Set
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from urllib.parse import urlparse

# Configure logging to avoid PHI leakage
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TLS13Adapter(HTTPAdapter):
    """
    HTTPAdapter that forces TLS 1.3.
    """
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        # Force TLS 1.3
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

class HIPAATransport:
    """
    HIPAA-compliant transport layer ensuring TLS 1.3, SSRF protection, and no PHI logging.
    """
    def __init__(self, timeout: float = 0.5, allowed_domains: Set[str] = None):
        self.timeout = timeout
        self.allowed_domains = allowed_domains or set()
        self.session = requests.Session()

        # Force TLS 1.3
        adapter = TLS13Adapter()
        self.session.mount("https://", adapter)

    def _is_allowed_url(self, url: str) -> bool:
        """
        Validates that the URL is using HTTPS and belongs to an allowed domain.
        """
        if not url.startswith("https://"):
            return False

        parsed = urlparse(url)
        return parsed.hostname in self.allowed_domains

    def safe_request(self, method: str, url: str, payload: Dict[str, Any] = None, headers: Dict[str, Any] = None) -> requests.Response:
        """
        Executes an HTTP request without logging PHI and with SSRF protection.
        """
        if not self._is_allowed_url(url):
            raise ValueError(f"URL {url} is not in the allowed domains list.")

        # PHI protection: Log only the hostname, no path or query params
        parsed = urlparse(url)
        logger.info(f"Executing {method} request to {parsed.hostname}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            # Ensure we don't log the exception if it contains PHI (rare for RequestException but safe)
            logger.error(f"Request failed for {parsed.hostname}: {type(e).__name__}")
            raise e
