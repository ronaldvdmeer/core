"""Constants for the Duco integration."""

from datetime import timedelta

from duco_connectivity.models import NodeType

from homeassistant.const import Platform

DOMAIN = "duco"
PLATFORMS = [Platform.FAN, Platform.SELECT, Platform.SENSOR, Platform.VALVE]
ZONE_NODE_TYPES: tuple[NodeType, ...] = (
    NodeType.VLV,
    NodeType.VLVRH,
    NodeType.VLVCO2,
    NodeType.VLVCO2RH,
    NodeType.EAV,
    NodeType.EAVRH,
    NodeType.EAVVOC,
    NodeType.EAVCO2,
)
SCAN_INTERVAL = timedelta(seconds=10)
