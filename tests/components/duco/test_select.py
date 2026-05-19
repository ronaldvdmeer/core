"""Tests for the Duco select platform."""

from unittest.mock import AsyncMock, patch

from duco_connectivity import (
    DucoConnectionError,
    DucoError,
    DucoRateLimitError,
    Node,
    NodeGeneralInfo,
    NodeVentilationInfo,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.duco.const import DOMAIN, SCAN_INTERVAL
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform

_SELECT_ENTITY = "select.bedroom_valve_ventilation_mode"


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_duco_client: AsyncMock,
) -> MockConfigEntry:
    """Set up only the select platform for testing."""
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.duco.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry


@pytest.mark.usefixtures("init_integration")
async def test_select_entities_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that select entities are created with the correct state."""
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_select_normalizes_timed_state(hass: HomeAssistant) -> None:
    """Test timed manual states are normalized to the stable option."""
    state = hass.states.get(_SELECT_ENTITY)
    assert state is not None
    assert state.state == "man2"


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("option", "expected_duco_state"),
    [
        ("auto", "AUTO"),
        ("man1", "MAN1"),
        ("cnt3", "CNT3"),
        ("empt", "EMPT"),
    ],
)
async def test_select_set_state(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    option: str,
    expected_duco_state: str,
) -> None:
    """Test select writes map to the correct Duco ventilation state."""
    mock_duco_client.async_set_ventilation_state = AsyncMock()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: _SELECT_ENTITY, "option": option},
        blocking=True,
    )

    mock_duco_client.async_set_ventilation_state.assert_called_once_with(
        60, expected_duco_state
    )


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("exception", "match"),
    [
        (DucoConnectionError("Connection refused"), "Failed to set ventilation state"),
        (DucoError("Unexpected error"), "Failed to set ventilation state"),
        (DucoRateLimitError(), "daily write limit"),
    ],
)
async def test_select_set_state_error(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    exception: Exception,
    match: str,
) -> None:
    """Test that a HomeAssistantError is raised on select API failure."""
    mock_duco_client.async_set_ventilation_state = AsyncMock(side_effect=exception)

    with pytest.raises(HomeAssistantError, match=match):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: _SELECT_ENTITY, "option": "cnt3"},
            blocking=True,
        )


@pytest.mark.usefixtures("init_integration")
async def test_select_coordinator_update_marks_unavailable(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that select entities become unavailable when the coordinator fails."""
    mock_duco_client.async_get_nodes = AsyncMock(
        side_effect=DucoConnectionError("offline")
    )

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(_SELECT_ENTITY)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("platform", "entity_id"),
    [(Platform.SELECT, "select.new_valve_ventilation_mode")],
)
async def test_select_node_added_and_removed_dynamically(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    mock_nodes: list[Node],
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    device_registry: dr.DeviceRegistry,
    entity_id: str,
    platform: Platform,
) -> None:
    """Test supported valve nodes are added and removed dynamically."""
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
    assert state.state == "auto"

    mock_duco_client.async_get_nodes.return_value = mock_nodes
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_config_entry.unique_id}_200")}
    )
    assert device is None
