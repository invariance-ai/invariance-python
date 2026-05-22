"""Tests for DnaResource read methods."""

import httpx

from invariance import Invariance


def _inv_with_handler(handler):
    transport = httpx.MockTransport(handler)
    inv = Invariance(api_key="inv_test", api_url="http://test.local")
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test"},
        transport=transport,
    )
    return inv


def test_list_objects_hits_expected_path_and_filters():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/dna/objects"
        assert request.url.params.get("project_id") == "proj_1"
        assert request.url.params.get("kind") == "service"
        assert request.url.params.get("q") == "billing"
        return httpx.Response(200, json={"data": [{"id": "obj_1"}], "next_cursor": None})

    inv = _inv_with_handler(handler)
    res = inv.dna.list_objects(project_id="proj_1", kind="service", q="billing")
    assert res["data"][0]["id"] == "obj_1"


def test_list_object_mentions_filters_by_event_and_object():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/dna/object-mentions"
        assert request.url.params.get("event_id") == "evt_1"
        assert request.url.params.get("object_id") == "obj_1"
        return httpx.Response(200, json={"data": [], "next_cursor": None})

    inv = _inv_with_handler(handler)
    res = inv.dna.list_object_mentions(event_id="evt_1", object_id="obj_1")
    assert res["data"] == []


def test_list_edges_scoped_to_run():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/dna/edges"
        assert request.url.params.get("run_id") == "run_1"
        return httpx.Response(
            200,
            json={"data": [{"id": "edge_1", "kind": "REQUIRED"}], "next_cursor": None},
        )

    inv = _inv_with_handler(handler)
    res = inv.dna.list_edges(run_id="run_1")
    assert res["data"][0]["kind"] == "REQUIRED"
