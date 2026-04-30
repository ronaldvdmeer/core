"""Tests for the Duco binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from duco.models import DiagComponent, DiagStatus
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_duco_client: AsyncMock,
) -> MockConfigEntry:
    """Set up only the binary sensor platform for testing."""
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.duco.PLATFORMS", [Platform.BINARY_SENSOR]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry


@pytest.mark.usefixtures("init_integration")
async def test_binary_sensor_entities_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that diagnostic binary sensor entities are created with the correct state."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_diagnostic_error_state(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test that a binary sensor is on (problem) when a subsystem reports an error."""
    mock_duco_client.async_get_diagnostics.return_value = [
        DiagComponent(component="Ventilation", status=DiagStatus.ERROR),
        DiagComponent(component="VentCool", status=DiagStatus.OK),
        DiagComponent(component="SunCtrl", status=DiagStatus.OK),
    ]
    coordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.living_ventilation").state == STATE_ON
