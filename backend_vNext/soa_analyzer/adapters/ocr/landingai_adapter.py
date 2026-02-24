"""LandingAI OCR Adapter for SOA table extraction"""
import os
import time
import logging
import requests
from typing import Dict, Any, Optional
from PIL import Image
import io


class LandingAIOCRAdapter:
    """Adapter for LandingAI Table Extraction API"""

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or os.getenv("LANDINGAI_API_KEY")
        if not self.api_key:
            raise ValueError("LANDINGAI_API_KEY not found in environment")

        # Use endpoint from env or parameter, fallback to default
        self.base_url = endpoint or os.getenv("LANDINGAI_ENDPOINT", "https://api.va.landing.ai/v1/ade/parse")
        self.headers = {
            "Authorization": f"Basic {self.api_key}"  # Changed from Bearer to Basic
        }

        # Standard logging
        self.logger = logging.getLogger(__name__)

    def extract_table(self, image: Image.Image) -> Dict[str, Any]:
        """
        Extract table structure from image using LandingAI

        Returns:
            Dictionary with:
            - 'html': HTML string of the table
            - 'markdown': Markdown string (alternative format)
            - 'text': Plain text (fallback)
        """

        max_retries = 5
        base_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # Convert PIL Image to bytes (fresh copy for each attempt)
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)  # Reset buffer position

                # Prepare request
                files = {"document": ("image.png", img_byte_arr, "image/png")}
                headers = {"Authorization": f"Basic {self.api_key}"}  # Use Basic auth

                # Log attempt
                if attempt > 0:
                    pass  # TODO: Add logging
                    # self.logger.info(
                        # "landingai_api_retry",
# attempt=attempt + 1,
#                         max_retries=max_retries,
#                         endpoint=self.base_url
                    # )  # TODO: Fix structured logging syntax
                else:
                    pass  # TODO: Add logging
                    # self.logger.debug(
                        # "landingai_api_call",
# endpoint=self.base_url,
#                         image_size=image.size,
#                         image_format=image.format
                    # )  # TODO: Fix structured logging syntax

                # Make API call with increased timeout
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    files=files,
                    timeout=120  # Increased timeout for large images
                )

                # Check response status - retry on server errors (5xx)
                if response.status_code >= 500:
                    pass  # TODO: Add logging
                    # self.logger.warning(
                        # "landingai_api_server_error",
# status_code=response.status_code,
#                         response_body=response.text[:500],
#                         attempt=attempt + 1,
#                         will_retry=attempt < max_retries - 1
                    # )  # TODO: Fix structured logging syntax

                    if attempt < max_retries - 1:
                        delay = base_delay ** (attempt + 1)
                        pass  # TODO: Add logging
                        # self.logger.info(
                            # "landingai_api_retry_delay",
# delay_seconds=delay,
#                             next_attempt=attempt + 2
                        # )  # TODO: Fix structured logging syntax
                        time.sleep(delay)
                        continue
                    else:
                        raise Exception(
                            f"LandingAI API failed with status {response.status_code} after {max_retries} attempts: {response.text[:200]}"
                        )

                # Client errors (4xx) - don't retry
                if response.status_code != 200:
                    pass  # TODO: Add logging
                    # self.logger.error(
                        # "landingai_api_error",
# status_code=response.status_code,
#                         response_body=response.text[:500],
#                         endpoint=self.base_url
                    # )  # TODO: Fix structured logging syntax
                    raise Exception(
                        f"LandingAI API failed with status {response.status_code}: {response.text[:200]}"
                    )

                response.raise_for_status()
                result = response.json()

                # Log success with attempt count
                pass  # TODO: Add logging
                # self.logger.debug(
                    # "landingai_api_success",
# result_keys=list(result.keys()),
#                     has_html=bool(result.get("html")),
#                     has_markdown=bool(result.get("markdown")),
#                     has_text=bool(result.get("text")),
#                     attempts_used=attempt + 1
                # )  # TODO: Fix structured logging syntax

                # Success - return result
                return {
                    "html": result.get("html", result.get("markdown", result.get("text", ""))),
                    "markdown": result.get("markdown", ""),
                    "text": result.get("text", ""),
                    "confidence": result.get("confidence", 1.0)  # Default to high confidence
                }

            except requests.exceptions.Timeout as e:
                pass  # TODO: Add logging
                # self.logger.warning(
                    # "landingai_api_timeout",
# timeout=120,
#                     endpoint=self.base_url,
#                     attempt=attempt + 1,
#                     will_retry=attempt < max_retries - 1
                # )  # TODO: Fix structured logging syntax

                if attempt < max_retries - 1:
                    delay = base_delay ** (attempt + 1)
                    pass  # TODO: Add logging
                    # self.logger.info(
                        # "landingai_api_retry_delay",
# delay_seconds=delay,
#                         next_attempt=attempt + 2
                    # )  # TODO: Fix structured logging syntax
                    time.sleep(delay)
                    continue
                else:
                    pass  # TODO: Add logging
                    # self.logger.error(
                        # "landingai_api_timeout_final",
# timeout=120,
#                         attempts=max_retries
                    # )  # TODO: Fix structured logging syntax
                    raise Exception(f"LandingAI API timeout after {max_retries} attempts (120s each): {e}") from e

            except requests.exceptions.RequestException as e:
                # Network errors - retry
                pass  # TODO: Add logging
                # self.logger.warning(
                    # "landingai_api_request_failed",
# error=str(e),
#                     endpoint=self.base_url,
#                     attempt=attempt + 1,
#                     will_retry=attempt < max_retries - 1
                # )  # TODO: Fix structured logging syntax

                if attempt < max_retries - 1:
                    delay = base_delay ** (attempt + 1)
                    pass  # TODO: Add logging
                    # self.logger.info(
                        # "landingai_api_retry_delay",
# delay_seconds=delay,
#                         next_attempt=attempt + 2
                    # )  # TODO: Fix structured logging syntax
                    time.sleep(delay)
                    continue
                else:
                    pass  # TODO: Add logging
                    # self.logger.error(
                        # "landingai_api_request_failed_final",
# error=str(e),
#                         attempts=max_retries
                    # )  # TODO: Fix structured logging syntax
                    raise Exception(f"LandingAI API request failed after {max_retries} attempts: {e}") from e

            except Exception as e:
                # Unexpected errors - don't retry
                pass  # TODO: Add logging
                # self.logger.error(
                    # "landingai_api_unexpected_error",
# error=str(e),
#                     error_type=type(e).__name__
                # )  # TODO: Fix structured logging syntax
                raise

        # Should never reach here, but just in case
        raise Exception(f"LandingAI API failed after {max_retries} attempts")

    async def extract_table_async(self, image: Image.Image) -> Dict[str, Any]:
        """Async version (calls sync for now)"""
        return self.extract_table(image)
