import pytest
from invariance import Invariance, InvarianceApiError


def test_requires_api_key():
    with pytest.raises(ValueError, match="api_key is required"):
        Invariance(api_key="")


def test_default_api_url():
    inv = Invariance(api_key="inv_test_abc")
    assert inv._http._client.base_url == "https://api.invariance.dev"
    inv.close()


def test_custom_api_url():
    inv = Invariance(api_key="inv_test_abc", api_url="http://localhost:3001")
    assert str(inv._http._client.base_url) == "http://localhost:3001"
    inv.close()


def test_context_manager():
    with Invariance(api_key="inv_test_abc") as inv:
        assert inv.runs is not None
        assert inv.nodes is not None
        assert inv.agents is not None


def test_api_error_fields():
    err = InvarianceApiError(
        status=403,
        code="forbidden",
        message="Access denied",
        details={"reason": "wrong agent"},
        request_id="req_123",
    )
    assert err.status == 403
    assert err.code == "forbidden"
    assert str(err) == "Access denied"
    assert err.details == {"reason": "wrong agent"}
    assert err.request_id == "req_123"
