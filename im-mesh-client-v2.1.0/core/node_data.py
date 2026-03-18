"""
Node and channel data extraction mixin for MeshtasticClientReal.

Provides methods for querying node info, channel config, device settings,
and helper methods for extracting data from Meshtastic protobuf/dict structures.

This is a mixin class - it accesses self.interface, self.connected, self.host,
self.port, self.my_node_info, self.nodes_db, self.channels_db via the host class.
"""

import asyncio
import base64
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class NodeDataMixin:
    """Mixin providing node/channel data extraction and query methods."""

    # ----- Static helpers for extracting data from Meshtastic node structures -----

    @staticmethod
    def _safe_get(obj, key, default=None):
        """Safely get a value from a dict or object attribute."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def _extract_user_info(cls, node_info) -> dict:
        """Extract user info (longName, shortName, hwModel) from a node_info structure.

        Handles both dict and protobuf object formats.
        Returns dict with keys: longName, shortName, hwModel (may be None).
        """
        result = {'longName': None, 'shortName': None, 'hwModel': 'Unknown'}

        user = cls._safe_get(node_info, 'user')
        if user:
            for key in ('longName', 'shortName', 'hwModel'):
                val = cls._safe_get(user, key)
                if val is not None:
                    result[key] = val

        # Fallback: direct attributes on node_info
        for key in ('longName', 'shortName', 'hwModel'):
            if result[key] is None or (key == 'hwModel' and result[key] == 'Unknown'):
                val = cls._safe_get(node_info, key)
                if val is not None:
                    result[key] = val

        return result

    @classmethod
    def _extract_sub_dict(cls, node_info, sub_key: str, attrs: list) -> dict:
        """Extract a sub-dictionary (e.g. 'position', 'deviceMetrics') from node_info.

        Handles dict, protobuf object, and None cases.
        Returns dict of non-None values, or empty dict.
        """
        sub = cls._safe_get(node_info, sub_key)
        if not sub:
            return {}
        result = {}
        for attr in attrs:
            val = cls._safe_get(sub, attr)
            if val is not None:
                result[attr] = val
        return result

    @classmethod
    def _extract_scalar_attrs(cls, node_info, attrs: list) -> dict:
        """Extract scalar top-level attributes from node_info.

        Returns dict of non-None values.
        """
        result = {}
        for attr in attrs:
            val = cls._safe_get(node_info, attr)
            if val is not None:
                result[attr] = val
        return result

    # ----- PSK encoding -----

    @staticmethod
    def _encode_psk(psk) -> Optional[str]:
        """Safely encode a PSK value to base64 string."""
        if psk is None:
            return None
        try:
            if isinstance(psk, bytes):
                return base64.b64encode(psk).decode('ascii')
            elif isinstance(psk, str):
                psk.encode('utf-8')  # Verify valid UTF-8
                return psk
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        # Fallback: force to base64
        if isinstance(psk, str):
            return base64.b64encode(psk.encode('latin-1')).decode('ascii')
        return base64.b64encode(bytes(psk)).decode('ascii')

    # ----- Channel processing -----

    def _process_channel(self, index: int, channel) -> Dict[str, Any]:
        """Extract and normalize a single channel's data."""
        channel_data = {
            'index': index,
            'name': f"Channel {index}",
            'id': getattr(channel, 'id', None),
            'uplink': getattr(channel, 'uplink', False),
            'downlink': getattr(channel, 'downlink', False),
        }

        if hasattr(channel, 'settings') and channel.settings:
            settings = channel.settings

            # Resolve name: settings > channel-level > default
            settings_name = getattr(settings, 'name', '')
            channel_name = getattr(channel, 'name', '')
            if settings_name:
                channel_data['name'] = settings_name
            elif channel_name:
                channel_data['name'] = channel_name

            channel_data.update({
                'psk': self._encode_psk(getattr(settings, 'psk', None)),
                'modemPreset': getattr(settings, 'modemPreset', None),
                'id': getattr(settings, 'id', channel_data['id']),
                'uplink': getattr(settings, 'uplink_enabled', channel_data['uplink']),
                'downlink': getattr(settings, 'downlink_enabled', channel_data['downlink']),
            })

        # Determine role: Primary (idx 0), Secondary (configured), Unconfigured
        has_name = channel_data['name'] != f"Channel {index}"
        has_psk = channel_data.get('psk') and channel_data['psk'] not in ['', 'AQ==']

        if index == 0:
            channel_data['role'] = 'Primary'
        elif has_name or has_psk:
            channel_data['role'] = 'Secondary'
        else:
            channel_data['role'] = 'Unconfigured'

        return channel_data

    # ----- Node data building -----

    def _build_node_data(self, node_id: str, node_info) -> Dict[str, Any]:
        """Build a normalized node data dict from raw interface node info."""
        node_data = {'id': node_id, 'num': node_id}

        # Names
        user_info = self._extract_user_info(node_info)
        long_name = user_info['longName']
        short_name = user_info['shortName']
        node_data['name'] = long_name or short_name or f"Node-{node_id}"
        node_data['shortName'] = short_name
        node_data['longName'] = long_name

        # Scalar attributes (snr, rssi, lastHeard, etc.)
        scalars = self._extract_scalar_attrs(node_info,
            ['snr', 'rssi', 'lastHeard', 'lastSeen', 'hopsAway', 'role',
             'hwModel', 'hwModelString', 'batteryLevel', 'voltage'])
        node_data.update(scalars)

        # Role fallback from user sub-dict
        hw_model = user_info.get('hwModel', 'Unknown')
        if 'role' not in node_data:
            user = self._safe_get(node_info, 'user')
            if user:
                role = self._safe_get(user, 'role')
                if role is not None:
                    node_data['role'] = role

        # Position data
        pos_data = self._extract_sub_dict(node_info, 'position',
            ['latitude', 'longitude', 'altitude', 'time', 'locationSource'])
        if pos_data:
            node_data['position'] = pos_data

        # Device metrics with top-level backward compat
        met_data = self._extract_sub_dict(node_info, 'deviceMetrics',
            ['batteryLevel', 'voltage', 'channelUtilization', 'airUtilTx', 'uptimeSeconds'])
        if met_data:
            node_data['deviceMetrics'] = met_data
            for key in ('batteryLevel', 'voltage'):
                if key in met_data:
                    node_data[key] = met_data[key]

        # Normalize lastHeard / lastSeen
        if 'lastHeard' in node_data:
            node_data['lastSeen'] = node_data['lastHeard']
        elif 'lastSeen' in node_data:
            node_data['lastHeard'] = node_data['lastSeen']

        # Hardware model and favorites
        node_data['hwModel'] = hw_model
        node_data['hwModelString'] = hw_model
        node_data['isFavorite'] = self._safe_get(node_info, 'isFavorite', False)

        return node_data

    # ----- Query methods -----

    async def get_node_info(self) -> Dict[str, Any]:
        """Get information about the connected node."""
        try:
            if not self.interface or not self.connected:
                return {'connected': False, 'host': self.host, 'port': self.port}

            node_info = {
                'connected': True,
                'host': self.host,
                'port': self.port
            }

            if self.my_node_info:
                # Handle different my_node_info structures
                if isinstance(self.my_node_info, dict):
                    node_info.update({
                        'node_id': self.my_node_info.get('num', 'unknown'),
                        'short_name': self.my_node_info.get('user', {}).get('shortName', 'unknown'),
                        'long_name': self.my_node_info.get('user', {}).get('longName', 'unknown'),
                        'hw_model': self.my_node_info.get('user', {}).get('hwModel', 'unknown'),
                        'firmware_version': self.my_node_info.get('deviceMetrics', {}).get('firmwareVersion', 'unknown')
                    })
                else:
                    # Handle object structure
                    user_info = getattr(self.my_node_info, 'user', None)
                    device_metrics = getattr(self.my_node_info, 'deviceMetrics', None)

                    node_info.update({
                        'node_id': getattr(self.my_node_info, 'num', 'unknown'),
                        'short_name': getattr(user_info, 'shortName', 'unknown') if user_info else 'unknown',
                        'long_name': getattr(user_info, 'longName', 'unknown') if user_info else 'unknown',
                        'hw_model': getattr(user_info, 'hwModel', 'unknown') if user_info else 'unknown',
                        'firmware_version': getattr(device_metrics, 'firmwareVersion', 'unknown') if device_metrics else 'unknown'
                    })

            return node_info

        except (AttributeError, KeyError, TypeError) as e:
            logger.warning(f"Error getting node info: {e}")
            logger.debug(f"my_node_info structure: {type(self.my_node_info)} - {self.my_node_info}")
            return {'connected': False, 'host': self.host, 'port': self.port, 'error': str(e)}

    def is_connected(self) -> bool:
        """Check if connected to Meshtastic device."""
        return self.connected and self.interface and self.interface.isConnected

    async def get_channel_info(self) -> List[Dict[str, Any]]:
        """Get channel configuration from device."""
        try:
            if not self.connected or not self.interface:
                logger.warning("Cannot get channels - not connected or no interface")
                return []

            local_node = getattr(self.interface, 'localNode', None)
            if not local_node:
                logger.info("Using cached channel data")
                return list(self.channels_db.values())

            raw_channels = getattr(local_node, 'channels', None)
            if not raw_channels:
                logger.warning("Local node has no channels")
                return list(self.channels_db.values())

            channels = []
            for index, channel in enumerate(raw_channels):
                try:
                    channels.append(self._process_channel(index, channel))
                except (AttributeError, KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Error processing channel {index}: {e}")
                    channels.append({
                        'index': index, 'name': f"Channel {index}",
                        'role': 'Unknown', 'error': str(e)
                    })

            logger.info(f"Processed {len(channels)} channels")
            return channels

        except (AttributeError, RuntimeError, ConnectionError) as e:
            logger.error(f"Critical error in get_channel_info: {e}")
            return []

    async def get_device_settings(self) -> Dict[str, Any]:
        """Get device configuration settings."""
        try:
            if not self.connected or not self.interface:
                return {"error": "Not connected to device"}

            settings = {
                "device_type": "meshtastic_node",
                "connection": {
                    "host": self.host,
                    "port": self.port,
                    "connected": True
                },
                "node_info": await self.get_node_info(),
                "capabilities": [
                    "text_messaging",
                    "binary_messaging",
                    "channel_config",
                    "node_discovery"
                ]
            }

            return settings

        except (AttributeError, ConnectionError, RuntimeError) as e:
            logger.warning(f"Failed to get device settings: {e}")
            return {"error": str(e)}

    async def request_node_info_update(self) -> None:
        """Request fresh node information from the device."""
        if not self.connected or not self.interface:
            logger.warning("Cannot request node info - not connected")
            return

        try:
            logger.info("Requesting node info update from device")
            # The interface should automatically handle this
            await asyncio.sleep(1)  # Give time for updates

        except (ConnectionError, OSError, RuntimeError) as e:
            logger.warning(f"Failed to request node info update: {e}")

    async def request_channel_update(self) -> None:
        """Request fresh channel configuration from the device."""
        if not self.connected or not self.interface:
            logger.warning("Cannot request channel info - not connected")
            return

        try:
            logger.info("Requesting channel configuration update from device")
            await self._request_initial_data()  # Refresh channel data

        except (ConnectionError, OSError, RuntimeError, AttributeError) as e:
            logger.warning(f"Failed to request channel update: {e}")

    def get_node_list(self) -> List[Dict[str, Any]]:
        """Get list of all known nodes from interface."""
        try:
            if not self.connected or not self.interface:
                logger.warning("Cannot get nodes - not connected or no interface")
                return []

            if not (hasattr(self.interface, 'nodes') and self.interface.nodes):
                logger.warning("Interface has no nodes or nodes attribute missing")
                return []

            nodes = []
            for node_id, node_info in self.interface.nodes.items():
                try:
                    nodes.append(self._build_node_data(node_id, node_info))
                except (KeyError, AttributeError, TypeError, ValueError) as e:
                    logger.warning(f"Error processing node {node_id}: {e}")
                    nodes.append({
                        'id': node_id, 'num': node_id,
                        'name': f"Node-{node_id}",
                        'hwModelString': 'Unknown', 'error': str(e)
                    })

            logger.info(f"Processed {len(nodes)} nodes from interface")
            return nodes

        except (AttributeError, RuntimeError, ConnectionError) as e:
            logger.exception(f"Critical error in get_node_list: {e}")
            return []

    async def request_node_update(self) -> None:
        """Request node information update - alias for request_node_info_update."""
        await self.request_node_info_update()

    async def get_device_config(self) -> Dict[str, Any]:
        """Get device configuration."""
        return await self.get_device_settings()
