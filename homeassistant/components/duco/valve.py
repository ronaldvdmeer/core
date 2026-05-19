"""Valve platform for the Duco integration."""

from duco_connectivity.models import Node

from homeassistant.components.valve import ValveEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, ZONE_NODE_TYPES
from .coordinator import DucoConfigEntry, DucoCoordinator
from .entity import DucoEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DucoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Duco valve entities."""
    coordinator = entry.runtime_data
    known_nodes: set[int] = set()

    @callback
    def _async_add_new_entities() -> None:
        """Add new valve entities and remove stale ones on coordinator updates."""
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

        new_entities: list[DucoValvePositionEntity] = []
        for node in coordinator.data.nodes.values():
            if (
                node.node_id in known_nodes
                or node.general.node_type not in ZONE_NODE_TYPES
            ):
                continue
            known_nodes.add(node.node_id)
            new_entities.append(DucoValvePositionEntity(coordinator, node))

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))
    _async_add_new_entities()


class DucoValvePositionEntity(DucoEntity, ValveEntity):
    """Read-only valve entity that reports the zone opening target."""

    _attr_translation_key = "opening"
    # The select is the authoritative control. This valve entity is opt-in
    # supplemental reporting for users who want a valve-style visualization.
    _attr_entity_registry_enabled_default = False
    _attr_reports_position = True

    def __init__(self, coordinator: DucoCoordinator, node: Node) -> None:
        """Initialize the valve entity."""
        super().__init__(coordinator, node)
        self._attr_unique_id = (
            f"{coordinator.config_entry.unique_id}_{node.node_id}_opening"
        )

    @property
    def current_valve_position(self) -> int | None:
        """Return the current zone opening as a percentage."""
        # Use the normalized airflow target as the user-facing opening proxy.
        return self._node.ventilation.flow_lvl_tgt if self._node.ventilation else None
