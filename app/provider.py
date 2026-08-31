from collections.abc import Iterator
from typing import Any, Optional
from urllib.parse import urljoin

import httpx


class EventsProviderError(RuntimeError):
    pass


class EventsProviderClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"x-api-key": self.api_key, **kwargs.pop("headers", {})}
        url = (
            path
            if path.startswith("http")
            else urljoin(self.base_url, path.lstrip("/"))
        )
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EventsProviderError(str(exc)) from exc
        data = response.json()
        return data if isinstance(data, dict) else {"results": data}

    def events(self, changed_at: str) -> dict[str, Any]:
        return self._request("GET", "api/events/", params={"changed_at": changed_at})

    def seats(self, event_id: str) -> list[str]:
        data = self._request("GET", f"api/events/{event_id}/seats/")
        return list(data.get("seats", data.get("available_seats", [])))

    def register(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
    ) -> str:
        data = self._request(
            "POST",
            f"api/events/{event_id}/register/",
            json={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "seat": seat,
            },
        )
        return str(data["ticket_id"])

    def unregister(self, event_id: str, ticket_id: str) -> bool:
        data = self._request(
            "DELETE",
            f"api/events/{event_id}/unregister/",
            json={"ticket_id": ticket_id},
        )
        return bool(data.get("success", True))


class EventsPaginator:
    def __init__(self, client: EventsProviderClient, changed_at: str):
        self.client = client
        self.changed_at = changed_at

    def __iter__(self) -> Iterator[dict[str, Any]]:
        next_url: Optional[str] = f"api/events/?changed_at={self.changed_at}"
        while next_url:
            page = self.client._request("GET", next_url)
            yield from page.get("results", [])
            next_url = page.get("next")
