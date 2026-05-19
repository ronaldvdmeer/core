"""Tests for the Duco valve platform."""

from unittest.mock import AsyncMock, patch

from duco_connectivity import (
    DucoConnectionError,
    Node,
    NodeGeneralInfo,
    NodeVentilationInfo,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.duco.const import DOMAIN, SCAN_INTERVAL
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform

_VALVE_ENTITY = "valve.bedroom_valve_opening"


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_duco_client: AsyncMock,
) -> MockConfigEntry:
    """Set up only the valve platform for testing."""
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.duco.PLATFORMS", [Platform.VALVE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_valve_entities_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that valve entities are created with the correct state."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_valve_entities_disabled_by_default(
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that valve entities are disabled by default."""
    entry = entity_registry.async_get(_VALVE_ENTITY)
    assert entry is not None
    assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_valve_coordinator_update_marks_unavailable(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that valve entities become unavailable when the coordinator fails."""
    mock_duco_client.async_get_nodes = AsyncMock(
        side_effect=DucoConnectionError("offline")
    )

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(_VALVE_ENTITY)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_valve_node_added_and_removed_dynamically(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    mock_nodes: list[Node],
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test supported valve nodes are added and removed dynamically."""
    entity_id = "valve.new_valve_opening"
    assert hass.states.get(entity_id) is None

    new_node = Node(
        node_id=200,
        general=NodeGeneralInfo(
            node_type="VLVCO2RH",
            sub_type=0,
            network_type="RF",
            parent=1,
            asso=1,
            name="New Valve",
            identify=0,
        ),
        ventilation=NodeVentilationInfo(
            state="AUTO",
            time_state_remain=0,
            time_state_end=0,
            mode="AUTO",
            flow_lvl_tgt=35,
        ),
    )
    mock_duco_client.async_get_nodes.return_value = [*mock_nodes, new_node]

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "open"
    assert state.attributes["current_position"] == 35

    mock_duco_client.async_get_nodes.return_value = mock_nodes
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_config_entry.unique_id}_200")}
    )
    assert device is None
