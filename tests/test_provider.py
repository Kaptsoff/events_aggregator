from unittest.mock import Mock, patch

from app.provider import EventsPaginator, EventsProviderClient


def test_paginator_follows_next_links():
    client = Mock(spec=EventsProviderClient)
    client._request.side_effect = [
        {"results": [{"id": "1"}], "next": "api/events/?cursor=next"},
        {"results": [{"id": "2"}], "next": None},
    ]
    assert list(EventsPaginator(client, "2000-01-01")) == [{"id": "1"}, {"id": "2"}]
    assert client._request.call_count == 2


@patch("app.provider.httpx.request")
def test_client_uses_api_key(mock_request):
    response = Mock(status_code=200)
    response.json.return_value = {"results": []}
    mock_request.return_value = response
    EventsProviderClient("http://provider", "secret").events("2000-01-01")
    assert mock_request.call_args.kwargs["headers"]["x-api-key"] == "secret"
