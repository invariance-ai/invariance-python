class Invariance:
    def __init__(self, api_key: str, api_url: str | None = None) -> None:
        self.api_key = api_key
        self.api_url = api_url or "https://api.invariance.dev"

