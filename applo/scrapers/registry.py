class ScraperRegistry:
    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(scraper_cls):
            cls._registry[name] = scraper_cls
            return scraper_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> type:
        return cls._registry[name]

    @classmethod
    def list_all(cls) -> dict[str, type]:
        return dict(cls._registry)
