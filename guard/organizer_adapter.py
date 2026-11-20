"""
guard/organizer_adapter.py
Organizer-stream adapter (T21) for laptop 4 as tenant 'contoso':
Reads the organizer event stream (HTTP stream, WebSocket, or local feed),
and normalizes incoming stream records into allow-listed metrics and events.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from guard.thin_slice import GuardThinSlice
from contracts.models import MetricName, EventCategory

logger = logging.getLogger("airlock.guard.organizer")


class OrganizerAdapter:
    def __init__(self, guard: GuardThinSlice):
        self.guard = guard

    def process_organizer_event(self, raw_event: Dict[str, Any]) -> bool:
        """
        Parses an organizer event, filters strictly to allow-listed contracts,
        and injects into guard telemetry.
        Returns True if accepted and mapped, False otherwise.
        """
        ev_type = raw_event.get("type") or raw_event.get("event")
        
        # 1. Latency and health probe checks from organizer
        if ev_type in ("latency_check", "probe", "ping"):
            lat = raw_event.get("latency_ms")
            if lat is not None and isinstance(lat, (int, float)):
                self.guard.set_packet_loss_override(0.0)
            status = raw_event.get("status")
            if status == "down" or raw_event.get("service_up") == 0.0:
                self.guard.emit_change_event(category="service_down", severity="high")
            return True

        # 2. Application changes from organizer
        if ev_type in ("app_restart", "app_restarted"):
            self.guard.emit_change_event(category="app_restarted", severity="info")
            return True
        elif ev_type in ("config_change", "config_changed"):
            self.guard.emit_change_event(category="config_changed", severity="info")
            return True
        elif ev_type in ("version_change", "version_changed"):
            self.guard.emit_change_event(category="version_changed", severity="info")
            return True

        # 3. Security events
        if ev_type in ("auth_failure", "login_failure"):
            user = raw_event.get("username", "user")
            ip = raw_event.get("ip", "127.0.0.1")
            self.guard.record_login(raw_username=user, raw_ip=ip, success=False)
            return True
        elif ev_type in ("auth_success", "login_success"):
            user = raw_event.get("username", "user")
            ip = raw_event.get("ip", "127.0.0.1")
            self.guard.record_login(raw_username=user, raw_ip=ip, success=True)
            return True

        return False
