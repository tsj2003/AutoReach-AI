"""Real-time intent signal detection improvements.

This implements Gojiberry-style real-time intent detection:
- Continuous signal monitoring
- Multi-source signal aggregation
- Real-time signal scoring
- Alert system for high-intent prospects
- Signal freshness tracking
"""

from __future__ import annotations

import logging
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Types of intent signals."""
    FUNDING = "funding"
    HIRING = "hiring"
    JOB_CHANGE = "job_change"
    TECHNOLOGY_ADOPTION = "technology_adoption"
    EXECUTIVE_CHANGE = "executive_change"
    EXPANSION = "expansion"
    PARTNERSHIP = "partnership"
    PRODUCT_LAUNCH = "product_launch"
    AWARDS = "awards"
    NEWS_MENTION = "news_mention"


class SignalStrength(Enum):
    """Strength levels of intent signals."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class IntentSignal:
    """Real-time intent signal."""
    id: str
    signal_type: SignalType
    company_domain: str
    strength: SignalStrength
    timestamp: datetime
    source: str  # "linkedin", "news", "crunchbase", "web", etc.
    confidence: float  # 0-1
    metadata: Dict[str, Any]
    processed: bool = False


@dataclass
class SignalAlert:
    """Alert for high-intent signals."""
    alert_id: str
    company_domain: str
    signal_count: int
    combined_score: float
    top_signals: List[IntentSignal]
    recommended_action: str
    timestamp: datetime


class RealTimeIntentDetector:
    """Real-time intent signal detection and monitoring."""

    def __init__(self):
        self._signals: Dict[str, List[IntentSignal]] = defaultdict(list)  # company_domain -> signals
        self._signal_sources: List[str] = ["linkedin", "news", "crunchbase", "web", "twitter"]
        self._alerts: List[SignalAlert] = []
        self._monitoring_active = False
        self._signal_thresholds = {
            SignalStrength.LOW: 0.3,
            SignalStrength.MEDIUM: 0.5,
            SignalStrength.HIGH: 0.7,
            SignalStrength.CRITICAL: 0.9
        }

    async def start_monitoring(
        self,
        companies: List[str],
        check_interval: int = 3600
    ) -> None:
        """Start real-time monitoring for specified companies."""
        self._monitoring_active = True
        logger.info(f"Starting real-time monitoring for {len(companies)} companies")
        
        while self._monitoring_active:
            for company_domain in companies:
                await self._check_company_signals(company_domain)
            
            # Wait for next check
            await asyncio.sleep(check_interval)

    async def stop_monitoring(self) -> None:
        """Stop real-time monitoring."""
        self._monitoring_active = False
        logger.info("Stopped real-time monitoring")

    async def _check_company_signals(self, company_domain: str) -> None:
        """Check for new signals for a specific company."""
        # In a real implementation, this would query actual data sources
        # For now, we'll simulate signal detection
        
        new_signals = await self._fetch_signals_from_sources(company_domain)
        
        for signal in new_signals:
            self._signals[company_domain].append(signal)
            logger.info(f"New signal detected for {company_domain}: {signal.signal_type.value}")
        
        # Check if we should generate an alert
        await self._evaluate_company_alert(company_domain)

    async def _fetch_signals_from_sources(self, company_domain: str) -> List[IntentSignal]:
        """Fetch signals from all configured sources."""
        all_signals = []
        
        for source in self._signal_sources:
            try:
                source_signals = await self._fetch_from_source(company_domain, source)
                all_signals.extend(source_signals)
            except Exception as e:
                logger.error(f"Failed to fetch signals from {source} for {company_domain}: {e}")
        
        return all_signals

    async def _fetch_from_source(self, company_domain: str, source: str) -> List[IntentSignal]:
        """Fetch signals from a specific source."""
        # Simulated signal fetching - in production this would be real API calls
        await asyncio.sleep(0.1)  # Simulate network delay
        
        # Return simulated signals
        return [
            IntentSignal(
                id=f"sig_{source}_{company_domain}_{datetime.now(timezone.utc).timestamp()}",
                signal_type=SignalType.HIRING,
                company_domain=company_domain,
                strength=SignalStrength.MEDIUM,
                timestamp=datetime.now(timezone.utc),
                source=source,
                confidence=0.7,
                metadata={"position": "Software Engineer", "location": "Remote"}
            )
        ]

    async def _evaluate_company_alert(self, company_domain: str) -> None:
        """Evaluate if company signals warrant an alert."""
        signals = self._signals[company_domain]
        
        if not signals:
            return
        
        # Filter for recent signals (last 7 days)
        recent_signals = [
            s for s in signals
            if (datetime.now(timezone.utc) - s.timestamp).total_seconds() < 604800
        ]
        
        if len(recent_signals) < 2:
            return  # Need at least 2 signals for alert
        
        # Calculate combined score
        combined_score = self._calculate_combined_signal_score(recent_signals)
        
        # Generate alert if score is high enough
        if combined_score >= 0.7:
            alert = SignalAlert(
                alert_id=f"alert_{company_domain}_{datetime.now(timezone.utc).timestamp()}",
                company_domain=company_domain,
                signal_count=len(recent_signals),
                combined_score=combined_score,
                top_signals=sorted(recent_signals, key=lambda x: x.confidence, reverse=True)[:3],
                recommended_action=self._generate_alert_recommendation(recent_signals),
                timestamp=datetime.now(timezone.utc)
            )
            
            self._alerts.append(alert)
            logger.info(f"Generated alert for {company_domain} with score {combined_score:.2f}")

    def _calculate_combined_signal_score(self, signals: List[IntentSignal]) -> float:
        """Calculate combined signal score from multiple signals."""
        if not signals:
            return 0.0
        
        # Weight signals by strength and recency
        now = datetime.now(timezone.utc)
        total_score = 0.0
        total_weight = 0.0
        
        for signal in signals:
            # Strength weight
            strength_weight = self._signal_thresholds.get(signal.strength, 0.5)
            
            # Recency weight (more recent = higher weight)
            hours_ago = (now - signal.timestamp).total_seconds() / 3600
            recency_weight = max(0.1, 1.0 - (hours_ago / 168))  # Decay over 7 days
            
            # Confidence weight
            confidence_weight = signal.confidence
            
            # Combined weight
            combined_weight = strength_weight * recency_weight * confidence_weight
            total_score += combined_weight
            total_weight += 1.0
        
        return min(1.0, total_score / total_weight if total_weight > 0 else 0.0)

    def _generate_alert_recommendation(self, signals: List[IntentSignal]) -> str:
        """Generate recommended action based on signals."""
        signal_types = [s.signal_type for s in signals]
        
        if SignalType.FUNDING in signal_types:
            return "Immediate outreach - company recently funded"
        elif SignalType.HIRING in signal_types:
            return "High priority - company is actively hiring"
        elif SignalType.EXPANSION in signal_types:
            return "Good opportunity - company is expanding"
        elif SignalType.EXECUTIVE_CHANGE in signal_types:
            return "Time-sensitive - new executive may be open to solutions"
        else:
            return "Consider outreach - multiple positive signals detected"

    def get_company_signals(
        self,
        company_domain: str,
        hours_back: int = 168
    ) -> List[IntentSignal]:
        """Get signals for a company within a time window."""
        if company_domain not in self._signals:
            return []
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        return [
            s for s in self._signals[company_domain]
            if s.timestamp >= cutoff_time
        ]

    def get_high_intent_companies(
        self,
        min_score: float = 0.7,
        hours_back: int = 168
    ) -> List[Dict[str, Any]]:
        """Get companies with high intent scores."""
        high_intent = []
        
        for company_domain, signals in self._signals.items():
            recent_signals = [
                s for s in signals
                if (datetime.now(timezone.utc) - s.timestamp).total_seconds() < hours_back * 3600
            ]
            
            if not recent_signals:
                continue
            
            score = self._calculate_combined_signal_score(recent_signals)
            
            if score >= min_score:
                high_intent.append({
                    "company_domain": company_domain,
                    "score": score,
                    "signal_count": len(recent_signals),
                    "top_signals": sorted(recent_signals, key=lambda x: x.confidence, reverse=True)[:3]
                })
        
        # Sort by score
        high_intent.sort(key=lambda x: x["score"], reverse=True)
        
        return high_intent

    def get_signal_freshness_report(self, company_domain: str) -> Dict[str, Any]:
        """Get a report on signal freshness for a company."""
        signals = self._signals.get(company_domain, [])
        
        if not signals:
            return {
                "company_domain": company_domain,
                "total_signals": 0,
                "fresh_signals": 0,
                "stale_signals": 0,
                "average_age_hours": 0
            }
        
        now = datetime.now(timezone.utc)
        fresh_count = 0
        stale_count = 0
        total_age = 0
        
        for signal in signals:
            age_hours = (now - signal.timestamp).total_seconds() / 3600
            total_age += age_hours
            
            if age_hours < 24:
                fresh_count += 1
            elif age_hours > 168:  # 7 days
                stale_count += 1
        
        return {
            "company_domain": company_domain,
            "total_signals": len(signals),
            "fresh_signals": fresh_count,
            "stale_signals": stale_count,
            "average_age_hours": total_age / len(signals) if signals else 0,
            "most_recent_signal": max(signals, key=lambda s: s.timestamp).timestamp.isoformat() if signals else None
        }

    def add_manual_signal(
        self,
        company_domain: str,
        signal_type: SignalType,
        strength: SignalStrength,
        metadata: Dict[str, Any]
    ) -> IntentSignal:
        """Manually add a signal (e.g., from sales team input)."""
        signal = IntentSignal(
            id=f"manual_{company_domain}_{datetime.now(timezone.utc).timestamp()}",
            signal_type=signal_type,
            company_domain=company_domain,
            strength=strength,
            timestamp=datetime.now(timezone.utc),
            source="manual",
            confidence=1.0,  # Manual signals have high confidence
            metadata=metadata
        )
        
        self._signals[company_domain].append(signal)
        logger.info(f"Manual signal added for {company_domain}: {signal_type.value}")
        
        return signal

    def get_recent_alerts(self, hours_back: int = 24) -> List[SignalAlert]:
        """Get recent high-intent alerts."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        return [
            alert for alert in self._alerts
            if alert.timestamp >= cutoff_time
        ]

    def cleanup_old_signals(self, days_to_keep: int = 30) -> int:
        """Remove signals older than specified days."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        removed_count = 0
        
        for company_domain in list(self._signals.keys()):
            original_count = len(self._signals[company_domain])
            self._signals[company_domain] = [
                s for s in self._signals[company_domain]
                if s.timestamp >= cutoff_time
            ]
            removed_count += original_count - len(self._signals[company_domain])
            
            # Remove empty lists
            if not self._signals[company_domain]:
                del self._signals[company_domain]
        
        logger.info(f"Cleaned up {removed_count} old signals")
        return removed_count
