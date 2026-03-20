"""
OceanChain AIS Client Module

Persistent async WebSocket client that connects to AISstream.io
and maintains a live snapshot of vessel positions.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from config import AISSTREAM_API_KEY, AISSTREAM_WS_URL

logger = logging.getLogger(__name__)


class AISClient:
    """
    Persistent WebSocket client for AISstream.io.
    
    Maintains a live snapshot of vessel positions, continuously updated
    from the AIS data stream. The snapshot is keyed by MMSI, with each
    update overwriting the previous position for that vessel.
    """
    
    def __init__(self) -> None:
        self._snapshot: dict[str, dict[str, Any]] = {}
        self._connected: bool = False
        self._reconnect_delay: float = 5.0
        self._message_count: int = 0
        self._last_message_time: Optional[datetime] = None
    
    def get_current_snapshot(self) -> dict[str, dict[str, Any]]:
        """
        Return a shallow copy of the current vessel position snapshot.
        
        Returns:
            dict mapping MMSI (str) to position data dict
        """
        return self._snapshot.copy()
    
    def get_vessel_count(self) -> int:
        """Return the number of vessels currently in the snapshot."""
        return len(self._snapshot)
    
    def get_message_count(self) -> int:
        """Return the total number of messages processed since startup."""
        return self._message_count
    
    def is_connected(self) -> bool:
        """Return whether the client is currently connected."""
        return self._connected
    
    def _parse_position_report(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Parse an AISstream PositionReport message into our internal format.
        
        Args:
            message: Raw message from AISstream
            
        Returns:
            Parsed position dict or None if parsing failed
        """
        try:
            metadata = message.get("Metadata", {})
            position_report = message.get("Message", {}).get("PositionReport", {})
            
            if not metadata or not position_report:
                return None
            
            mmsi = str(metadata.get("MMSI", ""))
            if not mmsi:
                return None
            
            # Parse timestamp from ISO format
            time_utc_str = metadata.get("time_utc", "")
            try:
                timestamp_dt = datetime.fromisoformat(time_utc_str.replace("Z", "+00:00"))
                timestamp_unix = int(timestamp_dt.timestamp())
            except (ValueError, AttributeError):
                timestamp_unix = int(datetime.utcnow().timestamp())
            
            # Parse heading - 511 means unavailable, store as 0xFFFF
            heading_raw = position_report.get("TrueHeading", 511)
            if heading_raw == 511 or heading_raw is None:
                heading = 0xFFFF
            else:
                heading = int(heading_raw)
            
            return {
                "mmsi": mmsi,
                "ship_name": str(metadata.get("ShipName", "")).strip(),
                "latitude": float(position_report.get("Latitude", 0.0)),
                "longitude": float(position_report.get("Longitude", 0.0)),
                "speed": float(position_report.get("SpeedOverGround", 0.0)),
                "heading": heading,
                "timestamp": timestamp_unix,
            }
        
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse position report: {e}")
            return None
    
    async def _handle_message(self, raw_message: str) -> None:
        """
        Process a single message from the WebSocket.
        
        Args:
            raw_message: Raw JSON string from WebSocket
        """
        try:
            message = json.loads(raw_message)
            
            # Check if this is a PositionReport message
            message_type = message.get("MessageType", "")
            if message_type != "PositionReport":
                return
            
            position = self._parse_position_report(message)
            if position:
                mmsi = position["mmsi"]
                self._snapshot[mmsi] = position
                self._message_count += 1
                self._last_message_time = datetime.utcnow()
                
                # Log periodically
                if self._message_count % 10000 == 0:
                    logger.info(
                        f"Processed {self._message_count} messages, "
                        f"{len(self._snapshot)} vessels in snapshot"
                    )
        
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode JSON message: {e}")
    
    async def _connect_and_subscribe(self) -> websockets.WebSocketClientProtocol:
        """
        Establish WebSocket connection and send subscription message.
        
        Returns:
            WebSocket connection object
        """
        logger.info(f"Connecting to AISstream at {AISSTREAM_WS_URL}")
        
        websocket = await websockets.connect(
            AISSTREAM_WS_URL,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10,
        )
        
        # Send subscription message
        subscription = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": [[[-90, -180], [90, 180]]],  # Global coverage
            "FilterMessageTypes": ["PositionReport"],
        }
        
        await websocket.send(json.dumps(subscription))
        logger.info("Subscription message sent, waiting for data...")
        
        self._connected = True
        return websocket
    
    async def run(self) -> None:
        """
        Main loop - connects to AISstream and processes messages indefinitely.
        
        Automatically reconnects on any exception with a 5-second backoff.
        This method runs forever and should be called as an asyncio task.
        """
        while True:
            try:
                websocket = await self._connect_and_subscribe()
                
                async for raw_message in websocket:
                    await self._handle_message(raw_message)
            
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                self._connected = False
            
            except WebSocketException as e:
                logger.error(f"WebSocket error: {e}")
                self._connected = False
            
            except asyncio.CancelledError:
                logger.info("AIS client shutdown requested")
                self._connected = False
                raise
            
            except Exception as e:
                logger.error(f"Unexpected error in AIS client: {e}", exc_info=True)
                self._connected = False
            
            # Reconnect with backoff
            logger.info(f"Reconnecting in {self._reconnect_delay} seconds...")
            await asyncio.sleep(self._reconnect_delay)


# Global singleton instance
ais_client = AISClient()
