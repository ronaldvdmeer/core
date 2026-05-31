"""Data update coordinator for the Duco integration."""

from dataclasses import dataclass
import logging

from duco_connectivity import DucoClient
from duco_connectivity.exceptions import (
    DucoConnectionError,
    DucoError,
    DucoResponseError,
)
from duco_connectivity.models import (
    BoardInfo,
    KnownActionName,
    Node,
    NodeListActionItemList,
    VentilationState,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .validation import UnsupportedBoardError, async_get_supported_board_info

_LOGGER = logging.getLogger(__name__)

type DucoConfigEntry = ConfigEntry[DucoCoordinator]


def _coerce_supported_ventilation_state(option: str) -> VentilationState | None:
    """Return a known typed ventilation state advertised by action discovery."""
    try:
        state = VentilationState(option)
    except ValueError:
        return None
    if state is VentilationState.UNKNOWN:
        return None
    return state


def _extract_supported_ventilation_states(
    node_actions: NodeListActionItemList,
) -> dict[int, tuple[VentilationState, ...]]:
    """Extract supported typed ventilation states per node from action discovery."""
    supported_states_by_node: dict[int, tuple[VentilationState, ...]] = {}

    for node_action_list in node_actions.nodes:
        for action in node_action_list.actions:
            if action.action.known_value != KnownActionName.SET_VENTILATION_STATE:
                continue

            supported_states = tuple(
                state
                for option in action.enum_values
                if (state := _coerce_supported_ventilation_state(option)) is not None
            )
            if supported_states:
                supported_states_by_node[node_action_list.node_id] = supported_states
            break

    return supported_states_by_node


@dataclass(slots=True, kw_only=True)
class DucoData:
    """Data returned by the Duco coordinator."""

    nodes: dict[int, Node]
    rssi_wifi: int | None


class DucoCoordinator(DataUpdateCoordinator[DucoData]):
    """Coordinator for the Duco integration."""

    config_entry: DucoConfigEntry
    board_info: BoardInfo
    supported_ventilation_states: dict[int, tuple[VentilationState, ...]]

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: DucoConfigEntry,
        client: DucoClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_setup(self) -> None:
        """Fetch board info once during initial setup."""
        try:
            self.board_info = await async_get_supported_board_info(self.client)
        except UnsupportedBoardError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="unsupported_board",
            ) from err
        except DucoResponseError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": repr(err)},
            ) from err
        except DucoConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": repr(err)},
            ) from err
        except DucoError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": repr(err)},
            ) from err

        self.supported_ventilation_states = {}
        try:
            node_actions = await self.client.async_get_node_actions()
        except DucoError as err:
            # Action discovery only powers the optional select entity, so setup
            # should continue when this supplemental endpoint is unavailable.
            _LOGGER.debug("Could not fetch Duco node actions", exc_info=err)
        else:
            self.supported_ventilation_states = _extract_supported_ventilation_states(
                node_actions
            )

    async def _async_update_data(self) -> DucoData:
        """Fetch node data from the Duco box."""
        try:
            nodes = await self.client.async_get_nodes()
        except DucoConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": repr(err)},
            ) from err
        except DucoError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": repr(err)},
            ) from err

        # LAN info only backs the diagnostic RSSI sensor, so failures on this
        # supplemental endpoint, including connection failures, should not make
        # the primary node entities unavailable.
        rssi_wifi = self.data.rssi_wifi if self.data else None
        try:
            lan_info = await self.client.async_get_lan_info()
        except DucoError as err:
            _LOGGER.debug("Could not fetch Duco LAN info", exc_info=err)
        else:
            rssi_wifi = lan_info.rssi_wifi

        return DucoData(
            nodes={node.node_id: node for node in nodes},
            rssi_wifi=rssi_wifi,
        )
