"""Select platform for the Duco integration."""

import logging

from duco_connectivity.exceptions import DucoError, DucoRateLimitError
from duco_connectivity.models import Node, NodeType, VentilationState

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import DucoConfigEntry, DucoCoordinator
from .entity import DucoEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DucoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Duco select entities."""
    coordinator = entry.runtime_data
    entities = [
        DucoVentilationStateSelectEntity(coordinator, node)
        for node in coordinator.data.nodes.values()
        if node.general.node_type == NodeType.BOX
        and coordinator.supported_ventilation_states.get(node.node_id)
    ]
    async_add_entities(entities)


class DucoVentilationStateSelectEntity(DucoEntity, SelectEntity):
    """Select entity for choosing a Duco ventilation state."""

    _attr_translation_key = "ventilation_state"

    def __init__(self, coordinator: DucoCoordinator, node: Node) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, node)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{node.node_id}_ventilation_state_select"
        # Action discovery is the source of truth for the states this node
        # actually accepts through SetVentilationState.
        self._attr_options = [
            state.value
            for state in coordinator.supported_ventilation_states[node.node_id]
        ]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected ventilation state."""
        node = self._node
        if node.ventilation is None:
            return None

        state = node.ventilation.state.value
        if state not in self.options:
            return None
        return state

    async def async_select_option(self, option: str) -> None:
        """Change the selected ventilation state."""
        self._valid_option_or_raise(option)
        await self._async_set_state(VentilationState(option))

    async def _async_set_state(self, state: VentilationState) -> None:
        """Send the ventilation state to the device and refresh coordinator."""
        try:
            await self.coordinator.client.async_set_ventilation_state(
                self._node_id, state
            )
        except DucoRateLimitError as err:
            _LOGGER.warning("Duco write rate limit exceeded for node %s", self._node_id)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="rate_limit_exceeded",
            ) from err
        except DucoError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="failed_to_set_state",
                translation_placeholders={"error": repr(err)},
            ) from err
        await self.coordinator.async_refresh()
