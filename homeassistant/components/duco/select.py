"""Select platform for the Duco integration."""

import logging

from duco_connectivity.exceptions import DucoError, DucoRateLimitError
from duco_connectivity.models import Node, VentilationState

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, ZONE_NODE_TYPES
from .coordinator import DucoConfigEntry, DucoCoordinator
from .entity import DucoEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

_SELECTABLE_STATES: tuple[VentilationState, ...] = (
    VentilationState.AUTO,
    VentilationState.MAN1,
    VentilationState.MAN2,
    VentilationState.MAN3,
    VentilationState.CNT1,
    VentilationState.CNT2,
    VentilationState.CNT3,
    VentilationState.EMPT,
)

_STATE_TO_OPTION: dict[VentilationState, str] = {
    state: state.lower() for state in _SELECTABLE_STATES
}
_STATE_TO_OPTION.update(
    {
        VentilationState.AUT1: VentilationState.AUTO.lower(),
        VentilationState.AUT2: VentilationState.AUTO.lower(),
        VentilationState.AUT3: VentilationState.AUTO.lower(),
        VentilationState.MAN1x2: VentilationState.MAN1.lower(),
        VentilationState.MAN1x3: VentilationState.MAN1.lower(),
        VentilationState.MAN2x2: VentilationState.MAN2.lower(),
        VentilationState.MAN2x3: VentilationState.MAN2.lower(),
        VentilationState.MAN3x2: VentilationState.MAN3.lower(),
        VentilationState.MAN3x3: VentilationState.MAN3.lower(),
    }
)
_OPTION_TO_STATE: dict[str, VentilationState] = {
    state.lower(): state for state in _SELECTABLE_STATES
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DucoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Duco select entities."""
    coordinator = entry.runtime_data
    known_nodes: set[int] = set()

    @callback
    def _async_add_new_entities() -> None:
        """Add new select entities and remove stale ones on coordinator updates."""
        stale_node_ids = known_nodes - coordinator.data.nodes.keys()
        if stale_node_ids:
            device_reg = dr.async_get(hass)
            mac = entry.unique_id
            for node_id in stale_node_ids:
                device = device_reg.async_get_device(
                    identifiers={(DOMAIN, f"{mac}_{node_id}")}
                )
                if device:
                    device_reg.async_update_device(
                        device.id,
                        remove_config_entry_id=entry.entry_id,
                    )
            known_nodes.difference_update(stale_node_ids)

        new_entities: list[DucoVentilationModeSelectEntity] = []
        for node in coordinator.data.nodes.values():
            if (
                node.node_id in known_nodes
                or node.general.node_type not in ZONE_NODE_TYPES
            ):
                continue
            known_nodes.add(node.node_id)
            new_entities.append(DucoVentilationModeSelectEntity(coordinator, node))

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))
    _async_add_new_entities()


class DucoVentilationModeSelectEntity(DucoEntity, SelectEntity):
    """Select entity for the ventilation mode of a Duco valve-style node."""

    _attr_translation_key = "ventilation_mode"
    _attr_options = [state.lower() for state in _SELECTABLE_STATES]

    def __init__(self, coordinator: DucoCoordinator, node: Node) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, node)
        self._attr_unique_id = (
            f"{coordinator.config_entry.unique_id}_{node.node_id}_ventilation_mode"
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self._node.ventilation is None:
            return None
        # Collapse transient timed states back to stable options so the select
        # only advertises durable choices.
        return _STATE_TO_OPTION.get(self._node.ventilation.state)

    async def async_select_option(self, option: str) -> None:
        """Set the ventilation mode for the zone."""
        self._valid_option_or_raise(option)
        try:
            await self.coordinator.client.async_set_ventilation_state(
                self._node_id, _OPTION_TO_STATE[option]
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
