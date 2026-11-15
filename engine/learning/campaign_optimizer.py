"""Learning system for campaign optimization similar to Gojiberry.

This system learns from campaign performance to optimize:
- Which buyers convert
- Which signals matter
- Which messages get replies
- Which actions create revenue
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Campaign performance metric."""
    metric_name: str
    value: float
    trend: str  # "improving", "declining", "stable"
    confidence: float  # 0-1


@dataclass
class OptimizationRecommendation:
    """AI-generated optimization recommendation."""
    category: str  # "messaging", "timing", "audience", "channel"
    recommendation: str
    expected_improvement: float  # percentage
    confidence: float  # 0-1
    action_items: List[str]


class CampaignLearningEngine:
    """Learning engine that analyzes campaign performance and generates insights."""

    def __init__(self):
        self._performance_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._conversion_patterns: Dict[str, Any] = {}
        self._signal_effectiveness: Dict[str, float] = defaultdict(float)
        self._message_performance: Dict[str, Dict[str, float]] = defaultdict(dict)

    def record_campaign_performance(
        self,
        campaign_id: str,
        performance_data: Dict[str, Any]
    ) -> None:
        """Record campaign performance data for learning."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        record = {
            "timestamp": timestamp,
            "campaign_id": campaign_id,
            "metrics": performance_data
        }
        
        self._performance_history[campaign_id].append(record)
        logger.info(f"Recorded performance data for campaign {campaign_id}")

    def analyze_campaign_performance(
        self,
        campaign_id: str
    ) -> List[PerformanceMetric]:
        """Analyze campaign performance and identify trends."""
        if campaign_id not in self._performance_history:
            return []
        
        history = self._performance_history[campaign_id]
        if len(history) < 2:
            return []
        
        metrics = []
        
        # Analyze reply rate trend
        reply_rates = [h["metrics"].get("reply_rate", 0) for h in history]
        if len(reply_rates) >= 2:
            trend = self._calculate_trend(reply_rates)
            confidence = self._calculate_confidence(reply_rates)
            metrics.append(PerformanceMetric(
                metric_name="reply_rate",
                value=reply_rates[-1],
                trend=trend,
                confidence=confidence
            ))
        
        # Analyze conversion rate trend
        conversion_rates = [h["metrics"].get("conversion_rate", 0) for h in history]
        if len(conversion_rates) >= 2:
            trend = self._calculate_trend(conversion_rates)
            confidence = self._calculate_confidence(conversion_rates)
            metrics.append(PerformanceMetric(
                metric_name="conversion_rate",
                value=conversion_rates[-1],
                trend=trend,
                confidence=confidence
            ))
        
        # Analyze engagement quality
        engagement_scores = [h["metrics"].get("engagement_score", 0) for h in history]
        if len(engagement_scores) >= 2:
            trend = self._calculate_trend(engagement_scores)
            confidence = self._calculate_confidence(engagement_scores)
            metrics.append(PerformanceMetric(
                metric_name="engagement_score",
                value=engagement_scores[-1],
                trend=trend,
                confidence=confidence
            ))
        
        return metrics

    def generate_optimization_recommendations(
        self,
        campaign_id: str,
        tenant_industry: Optional[str] = None
    ) -> List[OptimizationRecommendation]:
        """Generate AI-powered optimization recommendations."""
        recommendations = []
        
        if campaign_id not in self._performance_history:
            return recommendations
        
        performance_data = self._performance_history[campaign_id][-1]["metrics"]
        
        # Analyze messaging performance
        if performance_data.get("reply_rate", 0) < 0.05:
            recommendations.append(OptimizationRecommendation(
                category="messaging",
                recommendation="Improve subject line personalization and reduce AI fingerprint",
                expected_improvement=25.0,
                confidence=0.7,
                action_items=[
                    "Use signal-specific subject lines",
                    "Reduce cliché phrases like 'I hope this finds you well'",
                    "Increase grounding in actual buying signals"
                ]
            ))
        
        # Analyze timing optimization
        if performance_data.get("best_send_time", "unknown") == "unknown":
            recommendations.append(OptimizationRecommendation(
                category="timing",
                recommendation="Implement send time optimization based on prospect timezone",
                expected_improvement=15.0,
                confidence=0.6,
                action_items=[
                    "Track prospect time zones",
                    "A/B test different send times",
                    "Focus on business hours in prospect's timezone"
                ]
            ))
        
        # Analyze audience targeting
        if performance_data.get("icp_match_rate", 0) < 0.6:
            recommendations.append(OptimizationRecommendation(
                category="audience",
                recommendation="Refine ICP definition based on converting prospects",
                expected_improvement=30.0,
                confidence=0.8,
                action_items=[
                    "Analyze characteristics of converting prospects",
                    "Update ICP criteria with successful patterns",
                    "Remove criteria that don't correlate with conversion"
                ]
            ))
        
        # Analyze channel strategy
        if performance_data.get("single_channel_only", True):
            recommendations.append(OptimizationRecommendation(
                category="channel",
                recommendation="Implement multi-channel outreach (email + LinkedIn)",
                expected_improvement=40.0,
                confidence=0.75,
                action_items=[
                    "Add LinkedIn connection requests to sequence",
                    "Coordinate email and LinkedIn timing",
                    "Use LinkedIn for high-value prospects"
                ]
            ))
        
        # Industry-specific recommendations
        if tenant_industry:
            industry_rec = self._get_industry_recommendation(tenant_industry)
            if industry_rec:
                recommendations.append(industry_rec)
        
        return recommendations

    def learn_from_conversions(
        self,
        campaign_id: str,
        conversion_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Learn from successful conversions to improve future targeting."""
        insights = {
            "successful_patterns": [],
            "signal_effectiveness": {},
            "message_insights": {},
            "timing_insights": {}
        }
        
        if not conversion_data:
            return insights
        
        # Analyze common patterns in conversions
        patterns = self._extract_conversion_patterns(conversion_data)
        insights["successful_patterns"] = patterns
        
        # Analyze which signals led to conversions
        signal_analysis = self._analyze_signal_effectiveness(conversion_data)
        insights["signal_effectiveness"] = signal_analysis
        
        # Analyze message characteristics
        message_analysis = self._analyze_message_performance(conversion_data)
        insights["message_insights"] = message_analysis
        
        # Analyze timing patterns
        timing_analysis = self._analyze_timing_patterns(conversion_data)
        insights["timing_insights"] = timing_analysis
        
        # Update learning models
        self._update_learning_models(insights)
        
        return insights

    def get_cross_campaign_insights(
        self,
        tenant_id: str,
        industry: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate insights across multiple campaigns for the tenant."""
        insights = {
            "best_performing_campaigns": [],
            "industry_benchmarks": {},
            "improvement_opportunities": [],
            "roi_analysis": {}
        }
        
        # Get all campaigns for the tenant
        tenant_campaigns = [
            campaign_id for campaign_id in self._performance_history.keys()
            # In real implementation, filter by tenant_id
        ]
        
        # Analyze best performing campaigns
        for campaign_id in tenant_campaigns[:5]:  # Top 5
            if campaign_id in self._performance_history:
                latest_metrics = self._performance_history[campaign_id][-1]["metrics"]
                insights["best_performing_campaigns"].append({
                    "campaign_id": campaign_id,
                    "reply_rate": latest_metrics.get("reply_rate", 0),
                    "conversion_rate": latest_metrics.get("conversion_rate", 0),
                    "roi": latest_metrics.get("roi", 0)
                })
        
        # Industry benchmarks
        if industry:
            insights["industry_benchmarks"] = self._get_industry_benchmarks(industry)
        
        # ROI analysis
        insights["roi_analysis"] = self._calculate_roi_analysis(tenant_campaigns)
        
        return insights

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend from a series of values."""
        if len(values) < 2:
            return "stable"
        
        recent_avg = sum(values[-3:]) / min(3, len(values))
        earlier_avg = sum(values[:-3]) / max(1, len(values) - 3)
        
        if recent_avg > earlier_avg * 1.1:
            return "improving"
        elif recent_avg < earlier_avg * 0.9:
            return "declining"
        else:
            return "stable"

    def _calculate_confidence(self, values: List[float]) -> float:
        """Calculate confidence in trend based on data consistency."""
        if len(values) < 3:
            return 0.3
        
        variance = sum((x - sum(values)/len(values))**2 for x in values) / len(values)
        # Lower variance = higher confidence
        confidence = max(0.1, min(0.9, 1.0 - (variance / (sum(values)/len(values) + 1))))
        return confidence

    def _extract_conversion_patterns(self, conversion_data: List[Dict[str, Any]]) -> List[str]:
        """Extract common patterns from successful conversions."""
        patterns = []
        
        # Look for common company sizes
        company_sizes = [c.get("company_size") for c in conversion_data if c.get("company_size")]
        if company_sizes:
            most_common = max(set(company_sizes), key=company_sizes.count)
            patterns.append(f"Most successful with companies of size: {most_common}")
        
        # Look for common industries
        industries = [c.get("industry") for c in conversion_data if c.get("industry")]
        if industries:
            most_common = max(set(industries), key=industries.count)
            patterns.append(f"Strong performance in: {most_common}")
        
        # Look for common job titles
        titles = [c.get("title") for c in conversion_data if c.get("title")]
        if titles:
            most_common = max(set(titles), key=titles.count)
            patterns.append(f"High conversion from: {most_common}")
        
        return patterns

    def _analyze_signal_effectiveness(self, conversion_data: List[Dict[str, Any]]) -> Dict[str, float]:
        """Analyze which intent signals are most effective."""
        signal_effectiveness = defaultdict(int)
        
        for conversion in conversion_data:
            signals = conversion.get("intent_signals", [])
            for signal in signals:
                signal_type = signal.get("type", "unknown")
                signal_effectiveness[signal_type] += 1
        
        # Normalize to 0-1 scale
        total = sum(signal_effectiveness.values()) or 1
        return {k: v/total for k, v in signal_effectiveness.items()}

    def _analyze_message_performance(self, conversion_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze message characteristics that led to conversions."""
        return {
            "avg_length": sum(c.get("message_length", 0) for c in conversion_data) / max(1, len(conversion_data)),
            "personalization_level": "high" if sum(c.get("personalized", False) for c in conversion_data) / len(conversion_data) > 0.7 else "medium",
            "grounding_frequency": sum(c.get("grounded", False) for c in conversion_data) / max(1, len(conversion_data))
        }

    def _analyze_timing_patterns(self, conversion_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze timing patterns in successful conversions."""
        send_hours = [c.get("send_hour", 12) for c in conversion_data if c.get("send_hour")]
        
        if not send_hours:
            return {"best_time_range": "unknown"}
        
        # Find most common time range
        hour_counts = defaultdict(int)
        for hour in send_hours:
            if 9 <= hour < 12:
                hour_counts["morning"] += 1
            elif 12 <= hour < 17:
                hour_counts["afternoon"] += 1
            else:
                hour_counts["other"] += 1
        
        best_time = max(hour_counts.items(), key=lambda x: x[1])[0]
        return {"best_time_range": best_time}

    def _update_learning_models(self, insights: Dict[str, Any]) -> None:
        """Update internal learning models with new insights."""
        # Update signal effectiveness
        for signal, effectiveness in insights.get("signal_effectiveness", {}).items():
            self._signal_effectiveness[signal] = (
                self._signal_effectiveness[signal] * 0.7 + effectiveness * 0.3
            )

    def _get_industry_recommendation(self, industry: str) -> Optional[OptimizationRecommendation]:
        """Get industry-specific optimization recommendation."""
        industry_recommendations = {
            "technology": OptimizationRecommendation(
                category="messaging",
                recommendation="Focus on technical decision-makers and ROI-focused messaging",
                expected_improvement=20.0,
                confidence=0.65,
                action_items=[
                    "Target CTOs, VPs of Engineering",
                    "Emphasize technical integration benefits",
                    "Include case studies with similar tech stacks"
                ]
            ),
            "healthcare": OptimizationRecommendation(
                category="compliance",
                recommendation="Ensure messaging compliance and focus on patient outcomes",
                expected_improvement=15.0,
                confidence=0.7,
                action_items=[
                    "Highlight compliance and security",
                    "Focus on patient care improvements",
                    "Include relevant certifications"
                ]
            ),
            "finance": OptimizationRecommendation(
                category="messaging",
                recommendation="Emphasize risk reduction and regulatory compliance",
                expected_improvement=18.0,
                confidence=0.68,
                action_items=[
                    "Focus on risk mitigation",
                    "Include compliance features",
                    "Target CFOs and compliance officers"
                ]
            )
        }
        
        return industry_recommendations.get(industry.lower())

    def _get_industry_benchmarks(self, industry: str) -> Dict[str, float]:
        """Get industry benchmark metrics."""
        benchmarks = {
            "technology": {"avg_reply_rate": 0.08, "avg_conversion_rate": 0.15},
            "healthcare": {"avg_reply_rate": 0.06, "avg_conversion_rate": 0.12},
            "finance": {"avg_reply_rate": 0.07, "avg_conversion_rate": 0.14},
            "retail": {"avg_reply_rate": 0.05, "avg_conversion_rate": 0.10}
        }
        
        return benchmarks.get(industry.lower(), {"avg_reply_rate": 0.05, "avg_conversion_rate": 0.12})

    def _calculate_roi_analysis(self, campaign_ids: List[str]) -> Dict[str, Any]:
        """Calculate ROI analysis across campaigns."""
        total_spend = 0
        total_revenue = 0
        total_conversions = 0
        
        for campaign_id in campaign_ids:
            if campaign_id in self._performance_history:
                metrics = self._performance_history[campaign_id][-1]["metrics"]
                total_spend += metrics.get("spend", 0)
                total_revenue += metrics.get("revenue", 0)
                total_conversions += metrics.get("conversions", 0)
        
        roi = ((total_revenue - total_spend) / total_spend * 100) if total_spend > 0 else 0
        
        return {
            "total_spend": total_spend,
            "total_revenue": total_revenue,
            "total_conversions": total_conversions,
            "roi_percentage": roi,
            "cost_per_conversion": total_spend / total_conversions if total_conversions > 0 else 0
        }


class CampaignOptimizer:
    """High-level optimizer that uses the learning engine to improve campaigns."""

    def __init__(self):
        self._learning_engine = CampaignLearningEngine()

    def optimize_campaign(
        self,
        campaign_id: str,
        current_config: Dict[str, Any],
        tenant_industry: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate optimized campaign configuration."""
        # Get current performance analysis
        performance_metrics = self._learning_engine.analyze_campaign_performance(campaign_id)
        
        # Get optimization recommendations
        recommendations = self._learning_engine.generate_optimization_recommendations(
            campaign_id, tenant_industry
        )
        
        # Apply recommendations to current config
        optimized_config = self._apply_recommendations(current_config, recommendations)
        
        return {
            "current_performance": performance_metrics,
            "recommendations": recommendations,
            "optimized_config": optimized_config,
            "expected_improvement": self._estimate_improvement(recommendations)
        }

    def _apply_recommendations(
        self,
        current_config: Dict[str, Any],
        recommendations: List[OptimizationRecommendation]
    ) -> Dict[str, Any]:
        """Apply optimization recommendations to campaign configuration."""
        optimized = dict(current_config)
        
        for rec in recommendations:
            if rec.category == "messaging":
                optimized["personalization_enabled"] = True
                optimized["deliverability_preflight"] = {
                    "ai_fingerprint_check": True,
                    "grounding_required": True
                }
            elif rec.category == "timing":
                optimized["send_optimization"] = True
                optimized["optimal_send_windows"] = ["09:00-11:00", "14:00-16:00"]
            elif rec.category == "audience":
                optimized["icp_refinement"] = True
                optimized["auto_icp_update"] = True
            elif rec.category == "channel":
                optimized["multi_channel"] = True
                optimized["channels"] = ["email", "linkedin"]
        
        return optimized

    def _estimate_improvement(self, recommendations: List[OptimizationRecommendation]) -> float:
        """Estimate overall improvement from recommendations."""
        if not recommendations:
            return 0.0
        
        weighted_improvement = sum(
            rec.expected_improvement * rec.confidence 
            for rec in recommendations
        )
        total_confidence = sum(rec.confidence for rec in recommendations)
        
        return weighted_improvement / total_confidence if total_confidence > 0 else 0.0
