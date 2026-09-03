"""Client identity for the throttle.

The whole limit rests on this one function: get the key wrong and either
everyone shares a bucket (the API throttles itself) or anyone gets a fresh
bucket per request (the limit does nothing). The spoofing case below is the
reason it reads the *last* forwarded hop, and is the thing most likely to be
"fixed" into `hops[0]` by someone who hasn't hit this test.
"""

from app.rate_limit import client_ip


class _Client:
    def __init__(self, host: str) -> None:
        self.host = host


class _Request:
    def __init__(self, headers: dict[str, str], peer: str | None = "10.0.0.1") -> None:
        self.headers = headers
        self.client = _Client(peer) if peer else None


def test_direct_connection_uses_the_peer():
    assert client_ip(_Request({})) == "10.0.0.1"


def test_one_proxy_yields_the_client_not_the_proxy():
    # Railway appends the address it observed, so the peer (10.0.0.1) is the
    # proxy and the single forwarded hop is the caller.
    assert client_ip(_Request({"x-forwarded-for": "203.0.113.9"})) == "203.0.113.9"


def test_a_spoofed_leading_hop_cannot_win_a_fresh_bucket():
    # Caller sends "1.2.3.4"; the proxy appends what it actually saw. Reading
    # hops[0] here would let anyone rotate that header past the limit.
    forwarded = {"x-forwarded-for": "1.2.3.4, 203.0.113.9"}
    assert client_ip(_Request(forwarded)) == "203.0.113.9"


def test_whitespace_and_empty_entries_are_ignored():
    assert client_ip(_Request({"x-forwarded-for": " 1.2.3.4 ,, 203.0.113.9 "})) == "203.0.113.9"
    # A header present but empty must fall back rather than key on "".
    assert client_ip(_Request({"x-forwarded-for": ""})) == "10.0.0.1"


def test_no_peer_at_all_still_returns_a_key():
    assert client_ip(_Request({}, peer=None)) == "unknown"
