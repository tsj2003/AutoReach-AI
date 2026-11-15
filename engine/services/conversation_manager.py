"""Conversation management and follow-up automation system.

This implements Gojiberry-style conversation intelligence:
- Cross-channel conversation tracking
- AI-powered follow-up suggestions
- Automatic conversation stage detection
- Reply classification and routing
- Meeting booking automation
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ConversationStage(Enum):
    """Stages in a sales conversation."""
    INITIAL_OUTREACH = "initial_outreach"
    RESPONDED = "responded"
    INTERESTED = "interested"
    QUALIFIED = "qualified"
    DEMO_SCHEDULED = "demo_scheduled"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    UNRESPONSIVE = "unresponsive"


class ReplyType(Enum):
    """Types of replies from prospects."""
    INTERESTED = "interested"
    OBJECTION = "objection"
    MORE_INFO = "more_info"
    NOT_INTERESTED = "not_interested"
    WRONG_PERSON = "wrong_person"
    AUTO_RESPONDER = "auto_responder"
    MEETING_REQUEST = "meeting_request"
    PRICING_QUESTION = "pricing_question"


@dataclass
class ConversationMessage:
    """A message in a conversation."""
    id: str
    prospect_id: str
    channel: str  # "email", "linkedin", etc.
    direction: str  # "outbound", "inbound"
    content: str
    timestamp: datetime
    reply_type: Optional[ReplyType] = None
    classification_confidence: float = 0.0
    metadata: Dict[str, Any] = None


@dataclass
class Conversation:
    """A complete conversation with a prospect."""
    prospect_id: str
    campaign_id: str
    messages: List[ConversationMessage]
    current_stage: ConversationStage
    last_activity: datetime
    status: str = "active"  # "active", "paused", "completed"
    metadata: Dict[str, Any] = None


@dataclass
class FollowUpSuggestion:
    """AI-generated follow-up suggestion."""
    suggested_message: str
    timing: str  # "immediate", "24h", "48h", "1week"
    reason: str
    confidence: float
    channel: str = "email"


class ConversationManager:
    """Manages conversations and automates follow-ups."""

    def __init__(self):
        self._conversations: Dict[str, Conversation] = {}  # prospect_id -> conversation
        self._conversation_templates: Dict[ConversationStage, List[str]] = {}
        self._reply_patterns: Dict[ReplyType, List[str]] = {}
        self._initialize_patterns()

    def _initialize_patterns(self) -> None:
        """Initialize reply patterns and conversation templates."""
        self._reply_patterns = {
            ReplyType.INTERESTED: [
                "interested", "sounds good", "let's talk", "tell me more",
                "would like to learn", "interested in learning"
            ],
            ReplyType.OBJECTION: [
                "too expensive", "not right now", "budget", "timing",
                "concerned about", "not sure"
            ],
            ReplyType.MORE_INFO: [
                "more information", "details", "how does", "pricing",
                "features", "benefits"
            ],
            ReplyType.NOT_INTERESTED: [
                "not interested", "no thanks", "remove me", "unsubscribe",
                "not looking", "pass"
            ],
            ReplyType.WRONG_PERSON: [
                "wrong person", "not the right", "forwarding", "can't help",
                "not my decision", "someone else"
            ],
            ReplyType.AUTO_RESPONDER: [
                "out of office", "auto reply", "automatic", "vacation",
                "away from desk", "limited access"
            ],
            ReplyType.MEETING_REQUEST: [
                "schedule", "meeting", "call", "demo", "book",
                "calendar", "available", "time to discuss"
            ],
            ReplyType.PRICING_QUESTION: [
                "how much", "pricing", "cost", "price", "investment",
                "budget", "afford", "expensive"
            ]
        }

        self._conversation_templates = {
            ConversationStage.INITIAL_OUTREACH: [
                "Hi {name}, I noticed {signal} and thought you might be interested in {offer}.",
                "Hey {name}, reaching out because {signal}. Would love to share how {offer} could help."
            ],
            ConversationStage.RESPONDED: [
                "Thanks for getting back to me, {name}! I'd love to {next_action}.",
                "Great to hear from you, {name}. Based on your interest in {topic}, I think {offer} could be a great fit."
            ],
            ConversationStage.INTERESTED: [
                "I'm excited about your interest, {name}. Let's {next_action} to move forward.",
                "That's great, {name}. Here's what I suggest we do next: {next_action}."
            ],
            ConversationStage.QUALIFIED: [
                "Based on our conversation, I think {offer} is a perfect fit for your needs. Let's {next_action}.",
                "You're exactly the type of customer we help, {name}. Shall we {next_action}?"
            ],
            ConversationStage.DEMO_SCHEDULED: [
                "Looking forward to our demo, {name}. I'll {preparation} before our call.",
                "Great, {name}! I'll send over {materials} before our meeting."
            ],
            ConversationStage.NEGOTIATION: [
                "I understand your concerns about {objection}. Let me address that: {response}.",
                "That's a fair point, {name}. Here's how we can work around that: {solution}."
            ]
        }

    def create_conversation(
        self,
        prospect_id: str,
        campaign_id: str,
        initial_message: ConversationMessage
    ) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            prospect_id=prospect_id,
            campaign_id=campaign_id,
            messages=[initial_message],
            current_stage=ConversationStage.INITIAL_OUTREACH,
            last_activity=initial_message.timestamp,
            metadata={}
        )
        
        self._conversations[prospect_id] = conversation
        logger.info(f"Created conversation for prospect {prospect_id}")
        
        return conversation

    def add_message(
        self,
        prospect_id: str,
        message: ConversationMessage
    ) -> Optional[Conversation]:
        """Add a message to an existing conversation."""
        if prospect_id not in self._conversations:
            logger.warning(f"No conversation found for prospect {prospect_id}")
            return None
        
        conversation = self._conversations[prospect_id]
        conversation.messages.append(message)
        conversation.last_activity = message.timestamp
        
        # Classify the reply if it's inbound
        if message.direction == "inbound":
            message.reply_type = self._classify_reply(message.content)
            message.classification_confidence = self._calculate_classification_confidence(
                message.content, message.reply_type
            )
            
            # Update conversation stage based on reply
            self._update_conversation_stage(conversation, message.reply_type)
        
        logger.info(f"Added message to conversation for prospect {prospect_id}")
        return conversation

    def _classify_reply(self, content: str) -> ReplyType:
        """Classify the type of reply using pattern matching."""
        content_lower = content.lower()
        
        # Check each reply type's patterns
        for reply_type, patterns in self._reply_patterns.items():
            for pattern in patterns:
                if pattern in content_lower:
                    return reply_type
        
        # Default to MORE_INFO if no specific pattern matches
        return ReplyType.MORE_INFO

    def _calculate_classification_confidence(self, content: str, reply_type: ReplyType) -> float:
        """Calculate confidence in the classification."""
        content_lower = content.lower()
        patterns = self._reply_patterns.get(reply_type, [])
        
        match_count = sum(1 for pattern in patterns if pattern in content_lower)
        
        # More pattern matches = higher confidence
        confidence = min(1.0, match_count / 2.0)
        return confidence

    def _update_conversation_stage(self, conversation: Conversation, reply_type: ReplyType) -> None:
        """Update conversation stage based on reply type."""
        stage_transitions = {
            ConversationStage.INITIAL_OUTREACH: {
                ReplyType.INTERESTED: ConversationStage.INTERESTED,
                ReplyType.MEETING_REQUEST: ConversationStage.DEMO_SCHEDULED,
                ReplyType.MORE_INFO: ConversationStage.RESPONDED,
                ReplyType.OBJECTION: ConversationStage.RESPONDED,
                ReplyType.NOT_INTERESTED: ConversationStage.CLOSED_LOST,
                ReplyType.WRONG_PERSON: ConversationStage.INITIAL_OUTREACH,
                ReplyType.AUTO_RESPONDER: ConversationStage.INITIAL_OUTREACH,
                ReplyType.PRICING_QUESTION: ConversationStage.RESPONDED
            },
            ConversationStage.RESPONDED: {
                ReplyType.INTERESTED: ConversationStage.INTERESTED,
                ReplyType.MEETING_REQUEST: ConversationStage.DEMO_SCHEDULED,
                ReplyType.MORE_INFO: ConversationStage.RESPONDED,
                ReplyType.OBJECTION: ConversationStage.NEGOTIATION,
                ReplyType.NOT_INTERESTED: ConversationStage.CLOSED_LOST,
                ReplyType.PRICING_QUESTION: ConversationStage.NEGOTIATION
            },
            ConversationStage.INTERESTED: {
                ReplyType.MEETING_REQUEST: ConversationStage.DEMO_SCHEDULED,
                ReplyType.MORE_INFO: ConversationStage.QUALIFIED,
                ReplyType.OBJECTION: ConversationStage.NEGOTIATION,
                ReplyType.PRICING_QUESTION: ConversationStage.NEGOTIATION
            },
            ConversationStage.QUALIFIED: {
                ReplyType.MEETING_REQUEST: ConversationStage.DEMO_SCHEDULED,
                ReplyType.OBJECTION: ConversationStage.NEGOTIATION,
                ReplyType.PRICING_QUESTION: ConversationStage.NEGOTIATION
            },
            ConversationStage.DEMO_SCHEDULED: {
                ReplyType.INTERESTED: ConversationStage.NEGOTIATION,
                ReplyType.MEETING_REQUEST: ConversationStage.DEMO_SCHEDULED,
                ReplyType.OBJECTION: ConversationStage.NEGOTIATION
            },
            ConversationStage.NEGOTIATION: {
                ReplyType.INTERESTED: ConversationStage.CLOSED_WON,
                ReplyType.MEETING_REQUEST: ConversationStage.DEMO_SCHEDULED,
                ReplyType.NOT_INTERESTED: ConversationStage.CLOSED_LOST
            }
        }
        
        current_stage = conversation.current_stage
        transitions = stage_transitions.get(current_stage, {})
        
        if reply_type in transitions:
            conversation.current_stage = transitions[reply_type]
            logger.info(f"Conversation stage updated to {conversation.current_stage.value}")

    def generate_follow_up_suggestion(
        self,
        prospect_id: str,
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> Optional[FollowUpSuggestion]:
        """Generate AI-powered follow-up suggestion."""
        if prospect_id not in self._conversations:
            return None
        
        conversation = self._conversations[prospect_id]
        stage = conversation.current_stage
        
        # Get appropriate template for current stage
        templates = self._conversation_templates.get(stage, [])
        if not templates:
            return None
        
        # Select template based on context
        template = templates[0]  # Simple selection, could be more sophisticated
        
        # Personalize template
        prospect_name = conversation_context.get("name", "there") if conversation_context else "there"
        signal = conversation_context.get("signal", "your recent activity") if conversation_context else "your recent activity"
        offer = conversation_context.get("offer", "our solution") if conversation_context else "our solution"
        
        suggested_message = template.format(
            name=prospect_name,
            signal=signal,
            offer=offer,
            next_action="schedule a quick call",
            topic="what we discussed",
            preparation="prepare a personalized demo",
            materials="some case studies",
            objection="your concern",
            response="here's why that shouldn't be an issue",
            solution="a flexible option that works for you"
        )
        
        # Determine timing based on stage
        timing_map = {
            ConversationStage.INITIAL_OUTREACH: "48h",
            ConversationStage.RESPONDED: "24h",
            ConversationStage.INTERESTED: "immediate",
            ConversationStage.QUALIFIED: "immediate",
            ConversationStage.DEMO_SCHEDULED: "1week",
            ConversationStage.NEGOTIATION: "24h"
        }
        
        timing = timing_map.get(stage, "48h")
        
        # Determine confidence based on conversation quality
        confidence = self._calculate_follow_up_confidence(conversation)
        
        return FollowUpSuggestion(
            suggested_message=suggested_message,
            timing=timing,
            reason=f"Based on conversation stage: {stage.value}",
            confidence=confidence,
            channel="email"
        )

    def _calculate_follow_up_confidence(self, conversation: Conversation) -> float:
        """Calculate confidence in the follow-up suggestion."""
        # More messages = higher confidence (more context)
        message_count = len(conversation.messages)
        base_confidence = min(0.9, 0.5 + (message_count * 0.1))
        
        # Recent activity = higher confidence
        hours_since_last = (datetime.now(timezone.utc) - conversation.last_activity).total_seconds() / 3600
        if hours_since_last < 24:
            base_confidence += 0.1
        
        return min(1.0, base_confidence)

    def get_conversation_summary(self, prospect_id: str) -> Optional[Dict[str, Any]]:
        """Get a summary of the conversation."""
        if prospect_id not in self._conversations:
            return None
        
        conversation = self._conversations[prospect_id]
        
        return {
            "prospect_id": prospect_id,
            "campaign_id": conversation.campaign_id,
            "current_stage": conversation.current_stage.value,
            "message_count": len(conversation.messages),
            "last_activity": conversation.last_activity.isoformat(),
            "status": conversation.status,
            "messages": [
                {
                    "id": msg.id,
                    "channel": msg.channel,
                    "direction": msg.direction,
                    "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "reply_type": msg.reply_type.value if msg.reply_type else None,
                    "confidence": msg.classification_confidence
                }
                for msg in conversation.messages
            ]
        }

    def get_stale_conversations(self, hours_threshold: int = 72) -> List[str]:
        """Get conversations that haven't had activity in a while."""
        stale_prospects = []
        threshold = timedelta(hours=hours_threshold)
        
        for prospect_id, conversation in self._conversations.items():
            if conversation.status != "active":
                continue
            
            time_since_activity = datetime.now(timezone.utc) - conversation.last_activity
            if time_since_activity > threshold:
                stale_prospects.append(prospect_id)
        
        return stale_prospects

    def auto_schedule_follow_ups(self, hours_threshold: int = 72) -> List[FollowUpSuggestion]:
        """Automatically generate follow-up suggestions for stale conversations."""
        stale_prospects = self.get_stale_conversations(hours_threshold)
        suggestions = []
        
        for prospect_id in stale_prospects:
            suggestion = self.generate_follow_up_suggestion(prospect_id)
            if suggestion:
                suggestions.append(suggestion)
        
        return suggestions

    def detect_conversation_stall(self, prospect_id: str) -> bool:
        """Detect if a conversation has stalled."""
        if prospect_id not in self._conversations:
            return False
        
        conversation = self._conversations[prospect_id]
        
        # Consider stalled if no inbound messages in last 48 hours
        hours_threshold = 48
        time_since_last = datetime.now(timezone.utc) - conversation.last_activity
        
        has_inbound = any(msg.direction == "inbound" for msg in conversation.messages)
        
        return has_inbound and time_since_last > timedelta(hours=hours_threshold)

    def suggest_meeting_booking(self, prospect_id: str) -> Optional[Dict[str, Any]]:
        """Suggest meeting booking when conversation reaches appropriate stage."""
        if prospect_id not in self._conversations:
            return None
        
        conversation = self._conversations[prospect_id]
        
        # Suggest meeting if in qualified or interested stage
        if conversation.current_stage in [ConversationStage.QUALIFIED, ConversationStage.INTERESTED]:
            return {
                "prospect_id": prospect_id,
                "suggested_action": "book_meeting",
                "reason": f"Conversation reached {conversation.current_stage.value} stage",
                "calendar_link": conversation.metadata.get("calendar_link", ""),
                "suggested_message": "Would you be available for a 15-minute call to discuss how we can help?"
            }
        
        return None
