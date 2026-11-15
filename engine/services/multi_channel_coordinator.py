"""Multi-channel outreach coordinator for email + LinkedIn + other channels.

This implements Gojiberry-style multi-channel orchestration:
- Coordinated timing across channels
- Channel preference learning
- Cross-channel sequence optimization
- Unified conversation tracking
"""

from __future__ import annotations

import logging
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class Channel(Enum):
    """Available outreach channels."""
    EMAIL = "email"
    LINKEDIN_CONNECTION = "linkedin_connection"
    LINKEDIN_INMAIL = "linkedin_inmail"
    LINKEDIN_MESSAGE = "linkedin_message"
    TWITTER = "twitter"
    PHONE = "phone"


@dataclass
class ChannelAction:
    """A single action on a specific channel."""
    channel: Channel
    action_type: str  # "send", "connect", "message", etc.
    content: str
    scheduled_at: datetime
    status: str = "pending"  # "pending", "sent", "delivered", "opened", "replied"
    metadata: Dict[str, Any] = None


@dataclass
class OutreachSequence:
    """A coordinated multi-channel outreach sequence."""
    prospect_id: str
    actions: List[ChannelAction]
    strategy: str  # "parallel", "sequential", "adaptive"
    current_step: int = 0
    status: str = "active"  # "active", "paused", "completed", "failed"


class MultiChannelCoordinator:
    """Coordinates outreach across multiple channels."""

    def __init__(self):
        self._active_sequences: Dict[str, OutreachSequence] = {}
        self._channel_preferences: Dict[str, Dict[Channel, float]] = {}  # prospect_id -> channel effectiveness
        self._channel_adapters: Dict[Channel, Any] = {}

    def register_channel_adapter(self, channel: Channel, adapter: Any) -> None:
        """Register an adapter for a specific channel."""
        self._channel_adapters[channel] = adapter
        logger.info(f"Registered adapter for channel: {channel.value}")

    def create_multi_channel_sequence(
        self,
        prospect_id: str,
        prospect_data: Dict[str, Any],
        strategy: str = "adaptive"
    ) -> OutreachSequence:
        """Create a multi-channel outreach sequence for a prospect."""
        actions = self._generate_sequence_actions(prospect_data, strategy)
        
        sequence = OutreachSequence(
            prospect_id=prospect_id,
            actions=actions,
            strategy=strategy
        )
        
        self._active_sequences[prospect_id] = sequence
        logger.info(f"Created multi-channel sequence for prospect {prospect_id}")
        
        return sequence

    def _generate_sequence_actions(
        self,
        prospect_data: Dict[str, Any],
        strategy: str
    ) -> List[ChannelAction]:
        """Generate actions for a multi-channel sequence."""
        actions = []
        now = datetime.now(timezone.utc)
        
        email = prospect_data.get("email")
        linkedin_url = prospect_data.get("linkedin_url")
        
        if strategy == "parallel":
            # Send to both channels simultaneously
            if email:
                actions.append(ChannelAction(
                    channel=Channel.EMAIL,
                    action_type="send",
                    content=prospect_data.get("email_message", ""),
                    scheduled_at=now
                ))
            
            if linkedin_url:
                actions.append(ChannelAction(
                    channel=Channel.LINKEDIN_CONNECTION,
                    action_type="connect",
                    content=prospect_data.get("linkedin_message", ""),
                    scheduled_at=now
                ))
        
        elif strategy == "sequential":
            # LinkedIn first, then email
            if linkedin_url:
                actions.append(ChannelAction(
                    channel=Channel.LINKEDIN_CONNECTION,
                    action_type="connect",
                    content=prospect_data.get("linkedin_message", ""),
                    scheduled_at=now
                ))
            
            if email:
                actions.append(ChannelAction(
                    channel=Channel.EMAIL,
                    action_type="send",
                    content=prospect_data.get("email_message", ""),
                    scheduled_at=now + timedelta(hours=24)  # 24 hours later
                ))
        
        elif strategy == "adaptive":
            # Start with preferred channel, adapt based on response
            preferred_channel = self._get_preferred_channel(prospect_id)
            
            if preferred_channel == Channel.LINKEDIN_CONNECTION and linkedin_url:
                actions.append(ChannelAction(
                    channel=Channel.LINKEDIN_CONNECTION,
                    action_type="connect",
                    content=prospect_data.get("linkedin_message", ""),
                    scheduled_at=now
                ))
            elif preferred_channel == Channel.EMAIL and email:
                actions.append(ChannelAction(
                    channel=Channel.EMAIL,
                    action_type="send",
                    content=prospect_data.get("email_message", ""),
                    scheduled_at=now
                ))
            else:
                # Default to email
                if email:
                    actions.append(ChannelAction(
                        channel=Channel.EMAIL,
                        action_type="send",
                        content=prospect_data.get("email_message", ""),
                        scheduled_at=now
                    ))
        
        return actions

    async def execute_sequence(
        self,
        prospect_id: str,
        max_steps: int = 5
    ) -> Dict[str, Any]:
        """Execute a multi-channel outreach sequence."""
        if prospect_id not in self._active_sequences:
            return {"error": "No active sequence for this prospect"}
        
        sequence = self._active_sequences[prospect_id]
        results = []
        
        for i in range(sequence.current_step, min(len(sequence.actions), max_steps)):
            action = sequence.actions[i]
            
            if action.status != "pending":
                continue
            
            # Wait until scheduled time
            now = datetime.now(timezone.utc)
            if action.scheduled_at > now:
                wait_seconds = (action.scheduled_at - now).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
            
            # Execute the action
            result = await self._execute_channel_action(action)
            results.append(result)
            
            # Update action status
            action.status = "sent"
            sequence.current_step = i + 1
            
            # Check if we should continue based on response
            if result.get("response_received"):
                logger.info(f"Response received on {action.channel.value}, stopping sequence")
                break
        
        return {
            "prospect_id": prospect_id,
            "steps_executed": len(results),
            "results": results,
            "sequence_status": sequence.status
        }

    async def _execute_channel_action(self, action: ChannelAction) -> Dict[str, Any]:
        """Execute a single channel action."""
        adapter = self._channel_adapters.get(action.channel)
        
        if not adapter:
            logger.warning(f"No adapter registered for channel {action.channel.value}")
            return {
                "channel": action.channel.value,
                "success": False,
                "error": "No adapter available"
            }
        
        try:
            if action.channel == Channel.EMAIL:
                # Email sending logic
                result = await self._send_email(adapter, action.content, action.metadata)
            elif action.channel == Channel.LINKEDIN_CONNECTION:
                # LinkedIn connection request
                result = await self._send_linkedin_connection(adapter, action.content, action.metadata)
            elif action.channel == Channel.LINKEDIN_MESSAGE:
                # LinkedIn message
                result = await self._send_linkedin_message(adapter, action.content, action.metadata)
            else:
                result = {"success": False, "error": "Unsupported channel"}
            
            return result
        except Exception as e:
            logger.error(f"Failed to execute action on {action.channel.value}: {e}")
            return {
                "channel": action.channel.value,
                "success": False,
                "error": str(e)
            }

    async def _send_email(self, adapter: Any, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Send email via the email adapter."""
        # This would call the actual email adapter
        logger.info(f"Sending email: {content[:50]}...")
        await asyncio.sleep(0.5)
        return {"channel": "email", "success": True, "response_received": False}

    async def _send_linkedin_connection(self, adapter: Any, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Send LinkedIn connection request."""
        # This would call the LinkedIn adapter
        logger.info(f"Sending LinkedIn connection: {content[:50]}...")
        await asyncio.sleep(0.8)
        return {"channel": "linkedin_connection", "success": True, "response_received": False}

    async def _send_linkedin_message(self, adapter: Any, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Send LinkedIn message."""
        # This would call the LinkedIn adapter
        logger.info(f"Sending LinkedIn message: {content[:50]}...")
        await asyncio.sleep(0.6)
        return {"channel": "linkedin_message", "success": True, "response_received": False}

    def _get_preferred_channel(self, prospect_id: str) -> Channel:
        """Get the preferred channel for a prospect based on learning."""
        preferences = self._channel_preferences.get(prospect_id, {})
        
        if not preferences:
            return Channel.EMAIL  # Default to email
        
        # Return channel with highest effectiveness score
        return max(preferences.items(), key=lambda x: x[1])[0]

    def record_channel_response(
        self,
        prospect_id: str,
        channel: Channel,
        response_type: str,
        effectiveness: float
    ) -> None:
        """Record a response on a channel to learn preferences."""
        if prospect_id not in self._channel_preferences:
            self._channel_preferences[prospect_id] = {}
        
        # Update effectiveness score using exponential moving average
        current_score = self._channel_preferences[prospect_id].get(channel, 0.5)
        new_score = current_score * 0.7 + effectiveness * 0.3
        self._channel_preferences[prospect_id][channel] = new_score
        
        logger.info(f"Updated {channel.value} effectiveness for {prospect_id}: {new_score:.2f}")

    def get_sequence_status(self, prospect_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a prospect's outreach sequence."""
        if prospect_id not in self._active_sequences:
            return None
        
        sequence = self._active_sequences[prospect_id]
        return {
            "prospect_id": prospect_id,
            "strategy": sequence.strategy,
            "current_step": sequence.current_step,
            "total_steps": len(sequence.actions),
            "status": sequence.status,
            "actions": [
                {
                    "channel": action.channel.value,
                    "action_type": action.action_type,
                    "scheduled_at": action.scheduled_at.isoformat(),
                    "status": action.status
                }
                for action in sequence.actions
            ]
        }

    def pause_sequence(self, prospect_id: str) -> bool:
        """Pause an active outreach sequence."""
        if prospect_id in self._active_sequences:
            self._active_sequences[prospect_id].status = "paused"
            logger.info(f"Paused sequence for prospect {prospect_id}")
            return True
        return False

    def resume_sequence(self, prospect_id: str) -> bool:
        """Resume a paused outreach sequence."""
        if prospect_id in self._active_sequences:
            self._active_sequences[prospect_id].status = "active"
            logger.info(f"Resumed sequence for prospect {prospect_id}")
            return True
        return False
