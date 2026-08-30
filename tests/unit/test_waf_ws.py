"""WAF WebSocket connection store tests."""

from governance.agent_waf.ws_store import delete_connection, list_connections, save_connection
from shared.storage.factory import get_repository


def test_ws_connection_store_filters_by_agent():
    get_repository.cache_clear()
    save_connection("conn-1", "agent-a")
    save_connection("conn-2", "all")

    assert set(list_connections(agent_id="agent-a")) == {"conn-1", "conn-2"}

    delete_connection("conn-1")
    assert list_connections(agent_id="agent-a") == ["conn-2"]

    get_repository.cache_clear()
