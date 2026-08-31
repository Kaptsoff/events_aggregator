from unittest.mock import Mock, patch

from app.provider import EventsPaginator, EventsProviderClient


def test_paginator_follows_next_links():
    client = Mock(spec=EventsProviderClient)
    client.events.side_effect = [
        {"results": [{"id": "1"}], "next": "api/events/?cursor=next"},
        {"results": [{"id": "2"}], "next": None},
    ]
    assert list(EventsPaginator(client, "2000-01-01")) == [{"id": "1"}, {"id": "2"}]
    assert client.events.call_count == 2
    client.events.assert_any_call("2000-01-01", "api/events/?cursor=next")


@patch("app.provider.httpx.request")
def test_client_uses_api_key(mock_request):
    response = Mock(status_code=200)
    response.json.return_value = {"results": []}
    mock_request.return_value = response
    EventsProviderClient("http://provider", "secret").events("2000-01-01")
    assert mock_request.call_args.kwargs["headers"]["x-api-key"] == "secret"


@patch("app.provider.httpx.request")
def test_client_registration_and_cancellation(mock_request):
    response = Mock(status_code=201)
    response.json.return_value = {"ticket_id": "ticket-1"}
    mock_request.return_value = response
    client = EventsProviderClient("http://provider", "secret")

    ticket_id = client.register(
        "event-1", "Ivan", "Ivanov", "ivan@example.com", "A1"
    )

    assert ticket_id == "ticket-1"
    assert mock_request.call_args.kwargs["json"]["seat"] == "A1"

    response.json.return_value = {"success": True}
    assert client.unregister("event-1", ticket_id) is True
