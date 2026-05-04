"""Unit tests for external adapter registry."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from structlog.testing import capture_logs

from app.integrations.llm.adapter_registry import (
    ENTRY_POINT_GROUP,
    clear_registry,
    get_external_adapter,
    list_external_providers,
    load_external_adapters,
)
from app.integrations.llm.base import CostInfo, LLMMessage, LLMProviderAdapter, LLMResponse


class _FakeAdapter(LLMProviderAdapter):
    """Minimal adapter for testing registration."""

    provider_name = "fake_gateway"
    display_name = "Fake Gateway"

    async def create_message(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        pass  # type: ignore[return-value]

    def extract_cost(self, response: LLMResponse) -> CostInfo:
        pass  # type: ignore[return-value]


class _AnotherAdapter(LLMProviderAdapter):
    """Second adapter for multi-load tests."""

    provider_name = "another"
    display_name = "Another"

    async def create_message(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        pass  # type: ignore[return-value]

    def extract_cost(self, response: LLMResponse) -> CostInfo:
        pass  # type: ignore[return-value]


def _make_entry_point(name: str, value: str, target: Any) -> MagicMock:
    """Build a MagicMock that quacks like an importlib.metadata.EntryPoint."""
    ep = MagicMock()
    ep.name = name
    ep.value = value
    ep.group = ENTRY_POINT_GROUP
    ep.load.return_value = target
    return ep


@pytest.fixture(autouse=True)
def _clear_and_isolate_entry_points():
    """Clear the registry around each test and stub entry-point discovery
    to empty by default so tests don't pick up real installed adapters."""
    clear_registry()
    with patch(
        "app.integrations.llm.adapter_registry.entry_points",
        return_value=[],
    ):
        yield
    clear_registry()


class TestAdapterRegistry:
    """Tests for loading and routing external adapters via the legacy
    module-path spec (``CALSETA_EXTERNAL_ADAPTERS``)."""

    def test_empty_spec_is_noop(self) -> None:
        load_external_adapters("")
        assert list_external_providers() == []

    def test_load_valid_adapter(self) -> None:
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.FakeAdapter = _FakeAdapter
            mock_import.return_value = mock_module

            load_external_adapters("mypackage.llm:FakeAdapter")

        providers = list_external_providers()
        assert len(providers) == 1
        assert providers[0]["provider_name"] == "fake_gateway"
        assert providers[0]["is_external"] is True

    def test_get_external_adapter_returns_instance(self) -> None:
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.FakeAdapter = _FakeAdapter
            mock_import.return_value = mock_module
            load_external_adapters("mypackage.llm:FakeAdapter")

        adapter = get_external_adapter("fake_gateway")
        assert adapter is not None
        assert isinstance(adapter, _FakeAdapter)

    def test_get_unknown_returns_none(self) -> None:
        assert get_external_adapter("nonexistent") is None

    def test_bad_format_logged_not_raised(self) -> None:
        # No colon separator — should log error, not crash
        load_external_adapters("no_colon_here")
        assert list_external_providers() == []

    def test_import_error_logged_not_raised(self) -> None:
        with patch("importlib.import_module", side_effect=ImportError("no such module")):
            load_external_adapters("bad.module:Adapter")
        assert list_external_providers() == []

    def test_non_subclass_rejected(self) -> None:
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.NotAnAdapter = str  # not an adapter subclass
            mock_import.return_value = mock_module
            load_external_adapters("pkg:NotAnAdapter")
        assert list_external_providers() == []

    def test_duplicate_name_skipped(self) -> None:
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.FakeAdapter = _FakeAdapter
            mock_import.return_value = mock_module
            load_external_adapters("pkg:FakeAdapter,pkg:FakeAdapter")
        assert len(list_external_providers()) == 1

    def test_multiple_adapters(self) -> None:
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.FakeAdapter = _FakeAdapter
            mock_module.AnotherAdapter = _AnotherAdapter
            mock_import.return_value = mock_module
            load_external_adapters("pkg:FakeAdapter,pkg:AnotherAdapter")
        assert len(list_external_providers()) == 2


class TestEntryPointLoading:
    """S10: entry points are the recommended adapter registration path.

    These tests verify discovery via importlib.metadata works end-to-end
    and that the legacy module-path spec emits the
    ``external_adapter.module_path_deprecated`` warning.
    """

    def test_entry_point_loads_and_registers(self) -> None:
        """Adapter declared under ``calseta.llm_adapters`` is registered
        without touching the deprecated env var."""
        ep = _make_entry_point(
            "fake", "tests.fakes:FakeAdapter", _FakeAdapter,
        )
        with patch(
            "app.integrations.llm.adapter_registry.entry_points",
            return_value=[ep],
        ):
            load_external_adapters()  # no spec — entry points only

        providers = list_external_providers()
        assert len(providers) == 1
        assert providers[0]["provider_name"] == "fake_gateway"
        assert providers[0]["is_external"] is True

        # Routing works end-to-end
        instance = get_external_adapter("fake_gateway")
        assert isinstance(instance, _FakeAdapter)

    def test_entry_point_load_failure_is_logged_not_raised(self) -> None:
        ep = _make_entry_point("broken", "broken:Adapter", None)
        ep.load.side_effect = ImportError("missing package")
        with patch(
            "app.integrations.llm.adapter_registry.entry_points",
            return_value=[ep],
        ):
            load_external_adapters()
        assert list_external_providers() == []

    def test_module_path_emits_deprecation_warning(self) -> None:
        """Loading via the legacy module-path spec emits
        ``external_adapter.module_path_deprecated`` so operators see it."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.FakeAdapter = _FakeAdapter
            mock_import.return_value = mock_module

            with capture_logs() as logs:
                load_external_adapters("mypackage.llm:FakeAdapter")

        deprecation_events = [
            entry for entry in logs
            if entry.get("event") == "external_adapter.module_path_deprecated"
        ]
        assert deprecation_events, (
            "Expected at least one external_adapter.module_path_deprecated "
            f"warning, got events: {[e.get('event') for e in logs]}"
        )
        # The deprecation log carries enough context for operators to act
        assert deprecation_events[0]["entry"] == "mypackage.llm:FakeAdapter"
        assert deprecation_events[0]["log_level"] == "warning"
        # Adapter still loads successfully (back-compat preserved)
        assert len(list_external_providers()) == 1

    def test_entry_points_and_module_paths_coexist(self) -> None:
        """Both registration paths can register adapters in one load call."""
        ep = _make_entry_point(
            "ep_adapter", "tests.fakes:FakeAdapter", _FakeAdapter,
        )
        with (
            patch(
                "app.integrations.llm.adapter_registry.entry_points",
                return_value=[ep],
            ),
            patch("importlib.import_module") as mock_import,
        ):
            mock_module = MagicMock()
            mock_module.AnotherAdapter = _AnotherAdapter
            mock_import.return_value = mock_module
            load_external_adapters("pkg:AnotherAdapter")

        names = {p["provider_name"] for p in list_external_providers()}
        assert names == {"fake_gateway", "another"}
