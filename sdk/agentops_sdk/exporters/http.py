import logging
import random
import time
from typing import List

import requests

from agentops_sdk.config import AgentOpsConfig
from agentops_sdk.events import EventBatchPayload, TelemetryEvent
from agentops_sdk.exporters.base import BaseExporter

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 413, 422}


class HttpExporter(BaseExporter):
    """Exports telemetry events via HTTP to the AgentOps ingestion API.

    Features:
    - Bounded retries with exponential backoff and randomized jitter to prevent retry storms.
    - Explicit classification of transient (retryable) vs permanent (non-retryable) failures.
    - Observes 'Retry-After' response header when rate-limited (HTTP 429).
    - Best-effort isolation: network/DNS/backend failures never escape to the agent.
    """

    def __init__(self, config: AgentOpsConfig):
        self.config = config
        self.endpoint = f"{config.api_endpoint.rstrip('/')}/v1/telemetry/events"
        self.session = requests.Session()
        if config.api_key:
            self.session.headers.update({"Authorization": f"Bearer {config.api_key}"})

    def export(self, events: List[TelemetryEvent]) -> bool:
        if not events:
            return True

        project_id = self.config.project_id
        if not project_id:
            project_id = events[0].project_id

        payload = EventBatchPayload(
            project_id=project_id,
            batch=events
        )
        serialized_payload = payload.model_dump()

        max_attempts = max(1, self.config.max_retries + 1)
        base_backoff = max(0.01, self.config.retry_backoff_seconds)

        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    self.endpoint,
                    json=serialized_payload,
                    timeout=self.config.timeout_seconds
                )

                if response.status_code in (200, 201, 202):
                    return True

                if response.status_code in NON_RETRYABLE_STATUS_CODES:
                    logger.debug(
                        f"Non-retryable HTTP error {response.status_code} during telemetry export: "
                        f"{response.text[:200]}"
                    )
                    return False

                if response.status_code in TRANSIENT_STATUS_CODES:
                    if attempt < max_attempts - 1:
                        sleep_time = self._calculate_backoff(attempt, base_backoff, response)
                        time.sleep(sleep_time)
                        continue
                    else:
                        logger.debug(
                            f"Transient HTTP error {response.status_code} exhausted {max_attempts} attempts."
                        )
                        return False

                # Any other unexpected status code
                response.raise_for_status()
                return True

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_attempts - 1:
                    sleep_time = min(10.0, base_backoff * (2 ** attempt) * random.uniform(0.5, 1.5))
                    time.sleep(sleep_time)
                    continue
                logger.debug(f"Network error during telemetry export after {max_attempts} attempts: {type(e).__name__}")
                return False
            except Exception as e:
                # Other unexpected exceptions: do not crash
                logger.debug(f"Failed to export telemetry: {type(e).__name__}")
                return False

        return False

    def _calculate_backoff(
        self, attempt: int, base_backoff: float, response: requests.Response
    ) -> float:
        """Calculate exponential backoff with full jitter, honoring Retry-After if present."""
        if response.status_code == 429 and "Retry-After" in response.headers:
            try:
                retry_after = float(response.headers["Retry-After"])
                if 0 < retry_after <= 30.0:
                    return retry_after + random.uniform(0.05, 0.25)
            except (ValueError, TypeError):
                pass

        # Exponential backoff with random jitter between [0.5, 1.5]
        raw_backoff = base_backoff * (2 ** attempt)
        jitter = random.uniform(0.5, 1.5)
        return min(10.0, raw_backoff * jitter)

    def shutdown(self):
        self.session.close()
