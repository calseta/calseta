"""Unit tests for external adapter registry."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from app.integrations.llm.adapter_registry import (
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


class TestAdapterRegistry:
    """Tests for loading and routing external adapters."""

    def setup_method(self) -> None:
        clear_registry()

    def teardown_method(self) -> None:
        clear_registry()

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
        class _AnotherAdapter(LLMProviderAdapter):
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

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.FakeAdapter = _FakeAdapter
            mock_module.AnotherAdapter = _AnotherAdapter
            mock_import.return_value = mock_module
            load_external_adapters("pkg:FakeAdapter,pkg:AnotherAdapter")
        assert len(list_external_providers()) == 2
