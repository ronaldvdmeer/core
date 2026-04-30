"""Binary sensor platform for the Duco integration."""

from __future__ import annotations

import logging

from duco.models import DiagComponent, DiagStatus, Node, NodeType

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DucoConfigEntry, DucoCoordinator
from .entity import DucoEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

DIAG_COMPONENT_TO_TRANSLATION_KEY: dict[str, str] = {
    "Communication": "diag_communication",
    "Modbus": "diag_modbus",
    "Network": "diag_network",
    "SunCtrl": "diag_sun_ctrl",
    "VentCool": "diag_vent_cool",
    "Ventilation": "diag_ventilation",
    "WeatherStation": "diag_weather_station",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DucoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Duco binary sensor entities."""
    coordinator = entry.runtime_data

    box_node = next(
        (
            node
            for node in coordinator.data.nodes.values()
            if node.general.node_type == NodeType.BOX
        ),
        None,
    )
    if box_node is None:
        return

    entities: list[DucoDiagnosticBinarySensor] = []
    for diag in coordinator.data.diagnostics:
        if diag.component not in DIAG_COMPONENT_TO_TRANSLATION_KEY:
            _LOGGER.debug("Skipping unknown diagnostic component: %s", diag.component)
            continue
        entities.append(DucoDiagnosticBinarySensor(coordinator, box_node, diag))
    async_add_entities(entities)


class DucoDiagnosticBinarySensor(DucoEntity, BinarySensorEntity):
    """Binary sensor entity representing a Duco diagnostic subsystem status."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DucoCoordinator,
        node: Node,
        diag: DiagComponent,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(coordinator, node)
        self._component = diag.component
        self._attr_unique_id = (
            f"{coordinator.config_entry.unique_id}_diag_{diag.component.lower()}"
        )
        self._attr_translation_key = DIAG_COMPONENT_TO_TRANSLATION_KEY[diag.component]

    @property
    def is_on(self) -> bool | None:
        """Return True if the subsystem is in an error state."""
        # Treat a missing component in the latest diagnostics payload as
        # unknown instead of healthy so incomplete API data is not masked.
        for diagnostic in self.coordinator.data.diagnostics:
            if diagnostic.component == self._component:
                return diagnostic.status == DiagStatus.ERROR

        return None
