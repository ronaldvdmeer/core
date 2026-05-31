"""Tests for the Duco select platform."""

from unittest.mock import AsyncMock

from duco_connectivity import DucoConnectionError, DucoError, DucoRateLimitError
from duco_connectivity.models import VentilationState
import pytest

from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import setup_platform_integration

from tests.common import MockConfigEntry

_SELECT_ENTITY = "select.living_ventilation_state"


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_duco_client: AsyncMock,
) -> MockConfigEntry:
    """Set up only the select platform for testing."""
    return await setup_platform_integration(hass, mock_config_entry, [Platform.SELECT])


@pytest.mark.usefixtures("init_integration")
async def test_select_entity_state(hass: HomeAssistant) -> None:
    """Test that the select entity exposes the discovered ventilation states."""
    state = hass.states.get(_SELECT_ENTITY)

    assert state is not None
    assert state.state == VentilationState.AUTO.value
    assert state.attributes["options"] == [
        ventilation_state.value
        for ventilation_state in VentilationState
        if ventilation_state is not VentilationState.UNKNOWN
    ]


@pytest.mark.usefixtures("init_integration")
async def test_select_option_sets_typed_ventilation_state(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
) -> None:
    """Test that selecting an option uses the typed ventilation-state helper."""
    mock_duco_client.async_set_ventilation_state = AsyncMock()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: _SELECT_ENTITY, ATTR_OPTION: VentilationState.CNT1.value},
        blocking=True,
    )

    mock_duco_client.async_set_ventilation_state.assert_called_once_with(
        1, VentilationState.CNT1
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
async def test_select_option_error(
    hass: HomeAssistant,
    mock_duco_client: AsyncMock,
    exception: Exception,
    match: str,
) -> None:
    """Test that changing the select option raises HomeAssistantError on failure."""
    mock_duco_client.async_set_ventilation_state = AsyncMock(side_effect=exception)

    with pytest.raises(HomeAssistantError, match=match):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: _SELECT_ENTITY, ATTR_OPTION: VentilationState.CNT1.value},
            blocking=True,
        )
