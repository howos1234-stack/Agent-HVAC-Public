"""Repository interface; implementations return validated records, not DataFrames."""

from typing import Protocol

from agent_hvac.schemas.components import ComponentQuery, ProductRecord, ReloadSummary


class ComponentRepository(Protocol):
    def search(self, query: ComponentQuery) -> list[ProductRecord]: ...

    def reload(self) -> ReloadSummary: ...
