"""Async HTTP client for HackerNews API.

Fully encapsulated, self-managing async client using httpx with automatic
retry logic, connection pooling, and rate limiting.
"""

import asyncio
import json
from typing import Any, Optional

import httpx

from .config import config
from .exceptions import APIError, ItemNotFoundError, NetworkError, RetryExhaustedError
from .logger import logger
from .models import HNItem, HNUser


class HackerNewsClient:
    """Async HTTP client for HackerNews Firebase API.

    This client is fully self-managing with:
    - Automatic connection pooling and keep-alive
    - Exponential backoff retry logic
    - Concurrent request limiting via semaphore
    - Proper resource cleanup via async context manager

    Example:
        async with HackerNewsClient() as client:
            item = await client.get_item(1)
            highest = await client.get_highest_item_id()
    """

    def __init__(
        self,
        max_concurrent: Optional[int] = None,
        max_retries: Optional[int] = None,
        timeout: Optional[tuple[float, float]] = None,
    ) -> None:
        """Initialize the client.

        Args:
            max_concurrent: Maximum concurrent requests (default from config)
            max_retries: Maximum retry attempts (default from config)
            timeout: (connect, read) timeout tuple (default from config)
        """
        self.base_url = config.api.base_url
        self.max_retries = max_retries or config.api.max_retries
        self.backoff_factor = config.api.backoff_factor

        # Concurrency control - store as instance variable for connection pool config
        self._max_concurrent = max_concurrent or config.concurrency.max_concurrent_requests
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

        # HTTP client (will be initialized in __aenter__)
        self._client: Optional[httpx.AsyncClient] = None

        # Set timeout (connect, read, write, pool)
        if timeout:
            connect_timeout, read_timeout = timeout
        else:
            connect_timeout, read_timeout = config.api.timeout

        self._timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=5.0,  # Write timeout
            pool=5.0,   # Pool timeout
        )

        logger.info(
            f"Initialized HackerNewsClient (max_concurrent={self._max_concurrent}, "
            f"max_retries={self.max_retries})"
        )

    async def __aenter__(self) -> "HackerNewsClient":
        """Enter async context manager, creating the HTTP client."""
        # Configure connection pooling based on instance settings
        limits = httpx.Limits(
            max_connections=self._max_concurrent * 2,
            max_keepalive_connections=self._max_concurrent,
        )

        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            limits=limits,
            http2=False,  # HTTP/2 disabled (requires h2 package)
            follow_redirects=True,
        )

        logger.debug("HTTP client created and ready")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager, cleaning up resources."""
        if self._client:
            await self._client.aclose()
            logger.debug("HTTP client closed")

    async def _fetch_with_retry(
        self,
        url: str,
        attempt: int = 0,
    ) -> bytes:
        """Fetch URL with exponential backoff retry logic.

        Args:
            url: URL to fetch
            attempt: Current attempt number (for recursion)

        Returns:
            Response content as bytes

        Raises:
            RetryExhaustedError: If all retries fail
            ItemNotFoundError: If item returns 404
            APIError: For other API errors
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        try:
            async with self._semaphore:  # Limit concurrent requests
                response = await self._client.get(url)
                response.raise_for_status()
                return response.content

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ItemNotFoundError(f"Item not found: {url}")
            raise APIError(f"HTTP {e.response.status_code}: {url}") from e

        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
            # Network errors - retry with backoff
            if attempt >= self.max_retries:
                raise RetryExhaustedError(attempt, e)

            # Calculate backoff delay
            delay = self.backoff_factor * (2 ** attempt)
            logger.warning(
                f"Network error on attempt {attempt + 1}/{self.max_retries + 1} "
                f"for {url}: {e}. Retrying in {delay:.2f}s..."
            )

            await asyncio.sleep(delay)
            return await self._fetch_with_retry(url, attempt + 1)

        except Exception as e:
            raise NetworkError(f"Unexpected error fetching {url}: {e}") from e

    async def get_item(self, item_id: int) -> Optional[HNItem]:
        """Fetch a single item by ID.

        Args:
            item_id: HackerNews item ID

        Returns:
            HNItem if found, None if the item is null/deleted

        Raises:
            APIError: On API errors
            NetworkError: On network errors
        """
        url = f"{self.base_url}/item/{item_id}.json"

        try:
            content = await self._fetch_with_retry(url)

            # Check for null response (deleted/nonexistent item)
            if content == b"null":
                logger.debug(f"Item {item_id} is null (deleted/nonexistent)")
                return None

            # Parse JSON and create HNItem
            data = json.loads(content)
            return HNItem(**data)

        except ItemNotFoundError:
            return None

    async def get_items_batch(
        self,
        item_ids: list[int],
    ) -> list[Optional[HNItem]]:
        """Fetch multiple items concurrently.

        Args:
            item_ids: List of item IDs to fetch

        Returns:
            List of HNItem objects (None for deleted/null items or errors)
        """
        tasks = [self.get_item(item_id) for item_id in item_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to None and log errors
        processed_results = []
        for item_id, result in zip(item_ids, results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching item {item_id}: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        return processed_results

    async def get_user(self, username: str) -> Optional[HNUser]:
        """Fetch a user profile.

        Args:
            username: HackerNews username

        Returns:
            HNUser if found, None if user doesn't exist

        Raises:
            APIError: On API errors
        """
        url = f"{self.base_url}/user/{username}.json"

        try:
            content = await self._fetch_with_retry(url)

            if content == b"null":
                logger.debug(f"User {username} not found")
                return None

            data = json.loads(content)
            return HNUser(**data)

        except ItemNotFoundError:
            return None

    async def get_highest_item_id(self) -> int:
        """Fetch the highest item ID from HackerNews.

        Returns:
            The highest item ID currently available

        Raises:
            APIError: On API errors
        """
        url = f"{self.base_url}/maxitem.json"
        content = await self._fetch_with_retry(url)

        highest_id = json.loads(content)
        logger.info(f"Highest item ID: {highest_id}")
        return int(highest_id)

    async def get_raw_items_batch(
        self,
        item_ids: list[int],
    ) -> list[bytes]:
        """Fetch multiple items as raw JSON bytes (for bundling).

        Args:
            item_ids: List of item IDs to fetch

        Returns:
            List of raw JSON response bytes (including b'null' for deleted items)
        """
        async def fetch_raw(item_id: int) -> bytes:
            url = f"{self.base_url}/item/{item_id}.json"
            try:
                return await self._fetch_with_retry(url)
            except ItemNotFoundError:
                return b"null"
            except Exception as e:
                logger.error(f"Error fetching item {item_id}: {e}")
                return b"null"

        tasks = [fetch_raw(item_id) for item_id in item_ids]
        return await asyncio.gather(*tasks, return_exceptions=False)
