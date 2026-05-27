import httpx

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    if _client is None or _client.is_closed:
        raise RuntimeError("HTTP 클라이언트 미초기화 — lifespan 설정을 확인하세요.")
    return _client


async def startup() -> None:
    global _client
    _client = httpx.AsyncClient()


async def shutdown() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None
