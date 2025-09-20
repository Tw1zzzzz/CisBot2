"""
Comprehensive Performance Monitoring System for CisBot2

This module provides real-time performance monitoring, intelligent alerting,
and automated configuration tuning based on usage patterns.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Set
import statistics
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class Alert:
    """Performance alert with severity and context"""
    level: AlertLevel
    message: str
    timestamp: datetime
    metric_name: str
    current_value: float
    threshold: float
    suggested_actions: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'level': self.level.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'metric_name': self.metric_name,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'suggested_actions': self.suggested_actions
        }


@dataclass
class ConfigRecommendation:
    """Configuration tuning recommendation"""
    parameter_name: str
    current_value: Any
    recommended_value: Any
    reason: str
    expected_impact: str
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'parameter_name': self.parameter_name,
            'current_value': self.current_value,
            'recommended_value': self.recommended_value,
            'reason': self.reason,
            'expected_impact': self.expected_impact,
            'confidence': self.confidence
        }


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics container"""
    # API Response Times
    api_response_times: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    api_success_rates: Dict[str, List[bool]] = field(default_factory=lambda: defaultdict(list))
    api_timeout_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Cache Metrics
    cache_hit_ratio: float = 0.0
    cache_miss_ratio: float = 0.0
    cache_size_mb: float = 0.0
    cache_efficiency: float = 0.0
    cache_warming_effectiveness: float = 0.0
    
    # Background Processor Metrics
    bg_queue_size: int = 0
    bg_processing_times: List[float] = field(default_factory=list)
    bg_failure_rate: float = 0.0
    bg_worker_efficiency: float = 0.0
    
    # System Health Indicators
    system_health_score: float = 1.0
    connectivity_status: bool = True
    memory_usage_mb: float = 0.0
    
    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)


class PerformanceMonitor:
    """Comprehensive performance monitoring and alerting system"""
    
    def __init__(self, config):
        self.config = config
        self.metrics_history: deque = deque(maxlen=10000)  # Keep last 10k metrics
        self.current_metrics = PerformanceMetrics()
        
        # Alert management
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.alert_suppression: Dict[str, datetime] = {}
        
        # Configuration recommendations
        self.config_recommendations: List[ConfigRecommendation] = []
        
        # Performance analysis data
        self.performance_baselines: Dict[str, float] = {}
        self.usage_patterns: Dict[str, Any] = {}
        
        # Monitoring tasks
        self.monitoring_tasks: List[asyncio.Task] = []
        self.is_running = False
        
        # Component references
        self.faceit_analyzer = None
        self.cache_manager = None
        self.background_processor = None
        self.health_monitor = None
        
        logger.info("PerformanceMonitor initialized")
    
    async def start_monitoring(self):
        """Start all performance monitoring tasks"""
        if self.is_running:
            logger.warning("Performance monitoring already running")
            return
        
        self.is_running = True
        
        # Start monitoring tasks
        tasks = [
            self._metrics_collection_task(),
            self._performance_analysis_task(),
            self._alerting_task(),
            self._config_tuning_task(),
            self._cleanup_task()
        ]
        
        self.monitoring_tasks = [asyncio.create_task(task) for task in tasks]
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop all performance monitoring tasks"""
        self.is_running = False
        
        for task in self.monitoring_tasks:
            task.cancel()
        
        await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        self.monitoring_tasks.clear()
        
        # Generate final report
        await self._generate_final_report()
        logger.info("Performance monitoring stopped")
    
    def set_component_references(self, faceit_analyzer=None, cache_manager=None, 
                                background_processor=None, health_monitor=None):
        """Set references to monitored components"""
        if faceit_analyzer:
            self.faceit_analyzer = faceit_analyzer
        if cache_manager:
            self.cache_manager = cache_manager
        if background_processor:
            self.background_processor = background_processor
        if health_monitor:
            self.health_monitor = health_monitor
    
    # API Response Time Tracking
    def record_api_response(self, endpoint: str, duration: float, success: bool):
        """Record API response time and success status"""
        try:
            # Store response time
            if len(self.current_metrics.api_response_times[endpoint]) >= 1000:
                self.current_metrics.api_response_times[endpoint].pop(0)
            self.current_metrics.api_response_times[endpoint].append(duration)
            
            # Store success status
            if len(self.current_metrics.api_success_rates[endpoint]) >= 1000:
                self.current_metrics.api_success_rates[endpoint].pop(0)
            self.current_metrics.api_success_rates[endpoint].append(success)
            
            # Track timeouts
            if duration > getattr(self.config, 'API_TIMEOUT_THRESHOLD', 30.0):
                self.current_metrics.api_timeout_counts[endpoint] += 1
            
            logger.debug(f"Recorded API response: {endpoint}, {duration:.3f}s, success: {success}")
            
        except Exception as e:
            logger.error(f"Error recording API response: {e}")
    
    def get_response_time_stats(self, endpoint: str = None, window_seconds: int = 3600) -> Dict[str, Any]:
        """Get response time statistics for endpoint or all endpoints"""
        try:
            cutoff_time = datetime.now() - timedelta(seconds=window_seconds)
            stats = {}
            
            endpoints = [endpoint] if endpoint else self.current_metrics.api_response_times.keys()
            
            for ep in endpoints:
                response_times = self.current_metrics.api_response_times.get(ep, [])
                if not response_times:
                    continue
                
                # Calculate percentiles
                sorted_times = sorted(response_times)
                n = len(sorted_times)
                
                if n > 0:
                    stats[ep] = {
                        'count': n,
                        'avg': statistics.mean(sorted_times),
                        'min': min(sorted_times),
                        'max': max(sorted_times),
                        'p50': sorted_times[int(n * 0.5)],
                        'p90': sorted_times[int(n * 0.9)],
                        'p95': sorted_times[int(n * 0.95)],
                        'p99': sorted_times[int(n * 0.99)] if n > 1 else sorted_times[0]
                    }
                    
                    # Success rate
                    success_rates = self.current_metrics.api_success_rates.get(ep, [])
                    if success_rates:
                        stats[ep]['success_rate'] = sum(success_rates) / len(success_rates)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating response time stats: {e}")
            return {}
    
    def get_endpoint_performance(self) -> Dict[str, Any]:
        """Get detailed performance breakdown by endpoint"""
        try:
            performance = {}
            
            for endpoint in self.current_metrics.api_response_times.keys():
                stats = self.get_response_time_stats(endpoint)
                if endpoint in stats:
                    perf_data = stats[endpoint].copy()
                    
                    # Add performance categorization
                    avg_time = perf_data['avg']
                    if avg_time < 1.0:
                        perf_data['category'] = 'fast'
                    elif avg_time < 3.0:
                        perf_data['category'] = 'normal'
                    elif avg_time < 5.0:
                        perf_data['category'] = 'slow'
                    else:
                        perf_data['category'] = 'very_slow'
                    
                    # Add timeout count
                    perf_data['timeout_count'] = self.current_metrics.api_timeout_counts.get(endpoint, 0)
                    
                    performance[endpoint] = perf_data
            
            return performance
            
        except Exception as e:
            logger.error(f"Error getting endpoint performance: {e}")
            return {}
    
    # Cache Performance Monitoring
    def update_cache_metrics(self, hit_ratio: float, miss_ratio: float, size_mb: float, 
                           efficiency: float, warming_effectiveness: float = None):
        """Update cache performance metrics"""
        try:
            self.current_metrics.cache_hit_ratio = hit_ratio
            self.current_metrics.cache_miss_ratio = miss_ratio
            self.current_metrics.cache_size_mb = size_mb
            self.current_metrics.cache_efficiency = efficiency
            
            if warming_effectiveness is not None:
                self.current_metrics.cache_warming_effectiveness = warming_effectiveness
            
            logger.debug(f"Updated cache metrics: hit_ratio={hit_ratio:.3f}, size={size_mb:.1f}MB")
            
        except Exception as e:
            logger.error(f"Error updating cache metrics: {e}")
    
    def analyze_cache_performance(self) -> Dict[str, Any]:
        """Analyze cache performance and generate recommendations"""
        try:
            analysis = {
                'current_metrics': {
                    'hit_ratio': self.current_metrics.cache_hit_ratio,
                    'miss_ratio': self.current_metrics.cache_miss_ratio,
                    'size_mb': self.current_metrics.cache_size_mb,
                    'efficiency': self.current_metrics.cache_efficiency,
                    'warming_effectiveness': self.current_metrics.cache_warming_effectiveness
                },
                'recommendations': []
            }
            
            # Analyze hit ratio
            if self.current_metrics.cache_hit_ratio < 0.7:
                analysis['recommendations'].append({
                    'type': 'hit_ratio_improvement',
                    'message': 'Cache hit ratio is below optimal threshold',
                    'suggestions': [
                        'Increase cache size',
                        'Optimize cache warming strategy',
                        'Review TTL settings'
                    ]
                })
            
            # Analyze cache size
            max_size = getattr(self.config, 'CACHE_MAX_SIZE_MB', 100)
            if self.current_metrics.cache_size_mb > max_size * 0.8:
                analysis['recommendations'].append({
                    'type': 'size_optimization',
                    'message': 'Cache size approaching limit',
                    'suggestions': [
                        'Implement more aggressive eviction',
                        'Optimize data storage efficiency',
                        'Consider increasing cache size limit'
                    ]
                })
            
            # Analyze warming effectiveness
            if self.current_metrics.cache_warming_effectiveness < 0.3:
                analysis['recommendations'].append({
                    'type': 'warming_optimization',
                    'message': 'Cache warming effectiveness is low',
                    'suggestions': [
                        'Review warming patterns',
                        'Prioritize high-value data',
                        'Adjust warming frequency'
                    ]
                })
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing cache performance: {e}")
            return {}
    
    # Background Processor Monitoring
    def collect_bg_processor_metrics(self, queue_size: int, processing_times: List[float], 
                                   failure_rate: float, worker_efficiency: float = None):
        """Collect background processor performance metrics"""
        try:
            self.current_metrics.bg_queue_size = queue_size
            self.current_metrics.bg_processing_times = processing_times[-100:]  # Keep last 100
            self.current_metrics.bg_failure_rate = failure_rate
            
            if worker_efficiency is not None:
                self.current_metrics.bg_worker_efficiency = worker_efficiency
            
            logger.debug(f"Updated BG processor metrics: queue={queue_size}, failure_rate={failure_rate:.3f}")
            
        except Exception as e:
            logger.error(f"Error collecting BG processor metrics: {e}")
    
    # Health Monitoring Integration
    def collect_health_metrics(self, connectivity_status: bool, health_score: float):
        """Collect health monitoring metrics"""
        try:
            self.current_metrics.connectivity_status = connectivity_status
            self.current_metrics.system_health_score = health_score
            
            logger.debug(f"Updated health metrics: connectivity={connectivity_status}, score={health_score:.3f}")
            
        except Exception as e:
            logger.error(f"Error collecting health metrics: {e}")
    
    # Intelligent Alerting System
    def check_performance_thresholds(self) -> List[Alert]:
        """Check all performance metrics against thresholds"""
        alerts = []
        
        try:
            # API Response Time Alerts
            for endpoint, times in self.current_metrics.api_response_times.items():
                if not times:
                    continue
                
                avg_time = statistics.mean(times)
                warning_threshold = getattr(self.config, 'API_RESPONSE_TIME_ALERT_THRESHOLD', 5.0)
                critical_threshold = getattr(self.config, 'API_RESPONSE_TIME_CRITICAL_THRESHOLD', 10.0)
                
                if avg_time > critical_threshold:
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL,
                        message=f"API endpoint {endpoint} response time critically high",
                        timestamp=datetime.now(),
                        metric_name=f"api_response_time_{endpoint}",
                        current_value=avg_time,
                        threshold=critical_threshold,
                        suggested_actions=[
                            "Check API service health",
                            "Review network connectivity",
                            "Consider circuit breaker activation"
                        ]
                    ))
                elif avg_time > warning_threshold:
                    alerts.append(Alert(
                        level=AlertLevel.WARNING,
                        message=f"API endpoint {endpoint} response time elevated",
                        timestamp=datetime.now(),
                        metric_name=f"api_response_time_{endpoint}",
                        current_value=avg_time,
                        threshold=warning_threshold,
                        suggested_actions=[
                            "Monitor API performance",
                            "Check for rate limiting",
                            "Review caching strategy"
                        ]
                    ))
            
            # Cache Performance Alerts
            hit_ratio_warning = getattr(self.config, 'CACHE_HIT_RATIO_WARNING_THRESHOLD', 0.7)
            hit_ratio_critical = getattr(self.config, 'CACHE_HIT_RATIO_CRITICAL_THRESHOLD', 0.5)
            
            if self.current_metrics.cache_hit_ratio < hit_ratio_critical:
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    message="Cache hit ratio critically low",
                    timestamp=datetime.now(),
                    metric_name="cache_hit_ratio",
                    current_value=self.current_metrics.cache_hit_ratio,
                    threshold=hit_ratio_critical,
                    suggested_actions=[
                        "Increase cache size",
                        "Review cache warming strategy",
                        "Optimize TTL settings"
                    ]
                ))
            elif self.current_metrics.cache_hit_ratio < hit_ratio_warning:
                alerts.append(Alert(
                    level=AlertLevel.WARNING,
                    message="Cache hit ratio below optimal",
                    timestamp=datetime.now(),
                    metric_name="cache_hit_ratio",
                    current_value=self.current_metrics.cache_hit_ratio,
                    threshold=hit_ratio_warning,
                    suggested_actions=[
                        "Monitor cache performance",
                        "Consider cache optimization",
                        "Review access patterns"
                    ]
                ))
            
            # Background Processor Alerts
            queue_warning = getattr(self.config, 'BG_QUEUE_SIZE_WARNING_THRESHOLD', 100)
            queue_critical = getattr(self.config, 'BG_QUEUE_SIZE_CRITICAL_THRESHOLD', 500)
            
            if self.current_metrics.bg_queue_size > queue_critical:
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    message="Background processor queue critically full",
                    timestamp=datetime.now(),
                    metric_name="bg_queue_size",
                    current_value=self.current_metrics.bg_queue_size,
                    threshold=queue_critical,
                    suggested_actions=[
                        "Scale up background workers",
                        "Review task processing efficiency",
                        "Check for processing bottlenecks"
                    ]
                ))
            elif self.current_metrics.bg_queue_size > queue_warning:
                alerts.append(Alert(
                    level=AlertLevel.WARNING,
                    message="Background processor queue size elevated",
                    timestamp=datetime.now(),
                    metric_name="bg_queue_size",
                    current_value=self.current_metrics.bg_queue_size,
                    threshold=queue_warning,
                    suggested_actions=[
                        "Monitor queue trends",
                        "Consider worker optimization",
                        "Review task priorities"
                    ]
                ))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error checking performance thresholds: {e}")
            return []
    
    def generate_alerts(self, alerts: List[Alert]) -> List[Alert]:
        """Process and filter alerts with suppression logic"""
        filtered_alerts = []
        
        try:
            suppression_window = getattr(self.config, 'ALERT_SUPPRESSION_WINDOW', 300)
            
            for alert in alerts:
                # Check suppression
                if alert.metric_name in self.alert_suppression:
                    last_alert_time = self.alert_suppression[alert.metric_name]
                    if (datetime.now() - last_alert_time).total_seconds() < suppression_window:
                        continue
                
                # Add to active alerts
                self.active_alerts[alert.metric_name] = alert
                self.alert_suppression[alert.metric_name] = datetime.now()
                filtered_alerts.append(alert)
            
            # Add to history
            self.alert_history.extend(filtered_alerts)
            
            return filtered_alerts
            
        except Exception as e:
            logger.error(f"Error generating alerts: {e}")
            return []
    
    async def send_alert(self, alert: Alert):
        """Send alert through configured channels"""
        try:
            # Log alert
            log_level = getattr(logging, alert.level.value.upper(), logging.WARNING)
            logger.log(log_level, f"PERFORMANCE ALERT: {alert.message} "
                      f"(Current: {alert.current_value:.3f}, Threshold: {alert.threshold:.3f})")
            
            # TODO: Add external webhook support
            webhook_url = getattr(self.config, 'ALERT_EXTERNAL_WEBHOOK_URL', None)
            if webhook_url:
                # Implement webhook notification
                pass
                
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
    
    # Configuration Tuning Engine
    def analyze_usage_patterns(self) -> Dict[str, Any]:
        """Analyze usage patterns for optimization opportunities"""
        try:
            patterns = {
                'api_usage': {},
                'cache_patterns': {},
                'processing_patterns': {},
                'optimization_opportunities': []
            }
            
            # Analyze API usage patterns
            for endpoint, times in self.current_metrics.api_response_times.items():
                if times:
                    patterns['api_usage'][endpoint] = {
                        'call_frequency': len(times),
                        'avg_response_time': statistics.mean(times),
                        'usage_trend': 'stable'  # TODO: Implement trend analysis
                    }
            
            # Analyze cache patterns
            patterns['cache_patterns'] = {
                'hit_ratio_trend': 'stable',  # TODO: Implement trend analysis
                'size_growth_rate': 0.0,     # TODO: Calculate growth rate
                'efficiency_trend': 'stable'  # TODO: Implement trend analysis
            }
            
            # Identify optimization opportunities
            if self.current_metrics.cache_hit_ratio < 0.8:
                patterns['optimization_opportunities'].append({
                    'type': 'cache_optimization',
                    'priority': 'high',
                    'description': 'Cache hit ratio can be improved'
                })
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing usage patterns: {e}")
            return {}
    
    def generate_config_recommendations(self) -> List[ConfigRecommendation]:
        """Generate configuration tuning recommendations"""
        recommendations = []
        
        try:
            # Cache size recommendations
            if self.current_metrics.cache_hit_ratio < 0.7:
                current_size = getattr(self.config, 'CACHE_MAX_SIZE_MB', 100)
                recommended_size = min(current_size * 1.5, 500)  # Cap at 500MB
                
                recommendations.append(ConfigRecommendation(
                    parameter_name='CACHE_MAX_SIZE_MB',
                    current_value=current_size,
                    recommended_value=recommended_size,
                    reason='Low cache hit ratio indicates insufficient cache size',
                    expected_impact='Improved cache hit ratio, reduced API calls',
                    confidence=0.8
                ))
            
            # API timeout recommendations
            api_stats = self.get_response_time_stats()
            for endpoint, stats in api_stats.items():
                if stats.get('p95', 0) > 5.0:
                    current_timeout = getattr(self.config, 'API_TIMEOUT', 30.0)
                    recommended_timeout = max(stats['p95'] * 2, current_timeout)
                    
                    recommendations.append(ConfigRecommendation(
                        parameter_name='API_TIMEOUT',
                        current_value=current_timeout,
                        recommended_value=recommended_timeout,
                        reason=f'95th percentile response time for {endpoint} is high',
                        expected_impact='Reduced timeout errors, improved reliability',
                        confidence=0.7
                    ))
            
            # Background processor recommendations
            if self.current_metrics.bg_queue_size > 50:
                recommendations.append(ConfigRecommendation(
                    parameter_name='BG_WORKER_COUNT',
                    current_value=getattr(self.config, 'BG_WORKER_COUNT', 3),
                    recommended_value=getattr(self.config, 'BG_WORKER_COUNT', 3) + 2,
                    reason='Background queue size consistently elevated',
                    expected_impact='Faster task processing, reduced queue buildup',
                    confidence=0.9
                ))
            
            self.config_recommendations = recommendations
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating config recommendations: {e}")
            return []
    
    def validate_recommendations(self, recommendations: List[ConfigRecommendation]) -> List[ConfigRecommendation]:
        """Validate and filter recommendations for safety"""
        validated = []
        
        try:
            max_change_percent = getattr(self.config, 'CONFIG_TUNING_MAX_CHANGE_PERCENT', 0.2)
            min_confidence = getattr(self.config, 'CONFIG_TUNING_CONFIDENCE_THRESHOLD', 0.8)
            
            for rec in recommendations:
                # Check confidence threshold
                if rec.confidence < min_confidence:
                    continue
                
                # Check change magnitude
                if isinstance(rec.current_value, (int, float)) and isinstance(rec.recommended_value, (int, float)):
                    change_percent = abs(rec.recommended_value - rec.current_value) / rec.current_value
                    if change_percent > max_change_percent:
                        continue
                
                validated.append(rec)
            
            return validated
            
        except Exception as e:
            logger.error(f"Error validating recommendations: {e}")
            return []
    
    # Reporting and Visualization
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'system_health_score': self.current_metrics.system_health_score,
                    'api_performance': self.get_endpoint_performance(),
                    'cache_performance': {
                        'hit_ratio': self.current_metrics.cache_hit_ratio,
                        'size_mb': self.current_metrics.cache_size_mb,
                        'efficiency': self.current_metrics.cache_efficiency
                    },
                    'background_processing': {
                        'queue_size': self.current_metrics.bg_queue_size,
                        'failure_rate': self.current_metrics.bg_failure_rate,
                        'worker_efficiency': self.current_metrics.bg_worker_efficiency
                    }
                },
                'alerts': {
                    'active_count': len(self.active_alerts),
                    'recent_alerts': [alert.to_dict() for alert in list(self.alert_history)[-10:]]
                },
                'recommendations': [rec.to_dict() for rec in self.config_recommendations],
                'usage_patterns': self.analyze_usage_patterns()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {}
    
    def get_performance_dashboard(self) -> Dict[str, Any]:
        """Get real-time performance dashboard data"""
        try:
            dashboard = {
                'timestamp': datetime.now().isoformat(),
                'health_score': self.current_metrics.system_health_score,
                'api_metrics': {
                    'total_endpoints': len(self.current_metrics.api_response_times),
                    'avg_response_time': self._calculate_overall_api_avg(),
                    'success_rate': self._calculate_overall_success_rate(),
                    'slow_endpoints': self._get_slow_endpoints()
                },
                'cache_metrics': {
                    'hit_ratio': self.current_metrics.cache_hit_ratio,
                    'size_mb': self.current_metrics.cache_size_mb,
                    'efficiency': self.current_metrics.cache_efficiency,
                    'warming_effectiveness': self.current_metrics.cache_warming_effectiveness
                },
                'background_metrics': {
                    'queue_size': self.current_metrics.bg_queue_size,
                    'failure_rate': self.current_metrics.bg_failure_rate,
                    'worker_efficiency': self.current_metrics.bg_worker_efficiency
                },
                'active_alerts': len(self.active_alerts),
                'recommendations_count': len(self.config_recommendations)
            }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Error getting performance dashboard: {e}")
            return {}
    
    # Background Monitoring Tasks
    async def _metrics_collection_task(self):
        """Background task for collecting metrics from components"""
        while self.is_running:
            try:
                # Collect from cache manager
                if self.cache_manager and hasattr(self.cache_manager, 'get_statistics'):
                    cache_stats = await self.cache_manager.get_statistics()
                    if cache_stats:
                        self.update_cache_metrics(
                            hit_ratio=cache_stats.get('hit_ratio', 0.0),
                            miss_ratio=cache_stats.get('miss_ratio', 0.0),
                            size_mb=cache_stats.get('size_mb', 0.0),
                            efficiency=cache_stats.get('efficiency', 0.0)
                        )
                
                # Collect from background processor
                if self.background_processor and hasattr(self.background_processor, 'get_statistics'):
                    bg_stats = await self.background_processor.get_statistics()
                    if bg_stats:
                        self.collect_bg_processor_metrics(
                            queue_size=bg_stats.get('queue_size', 0),
                            processing_times=bg_stats.get('processing_times', []),
                            failure_rate=bg_stats.get('failure_rate', 0.0)
                        )
                
                # Collect from health monitor
                if self.health_monitor and hasattr(self.health_monitor, 'get_health_status'):
                    health_status = await self.health_monitor.get_health_status()
                    if health_status:
                        self.collect_health_metrics(
                            connectivity_status=health_status.get('connected', True),
                            health_score=health_status.get('score', 1.0)
                        )
                
                # Store current metrics in history
                self.metrics_history.append(self.current_metrics)
                
                await asyncio.sleep(getattr(self.config, 'PERFORMANCE_COLLECTION_INTERVAL', 60))
                
            except Exception as e:
                logger.error(f"Error in metrics collection task: {e}")
                await asyncio.sleep(10)
    
    async def _performance_analysis_task(self):
        """Background task for performance analysis and alerting"""
        while self.is_running:
            try:
                # Check thresholds and generate alerts
                threshold_alerts = self.check_performance_thresholds()
                if threshold_alerts:
                    filtered_alerts = self.generate_alerts(threshold_alerts)
                    for alert in filtered_alerts:
                        await self.send_alert(alert)
                
                await asyncio.sleep(getattr(self.config, 'PERFORMANCE_ANALYSIS_INTERVAL', 300))
                
            except Exception as e:
                logger.error(f"Error in performance analysis task: {e}")
                await asyncio.sleep(30)
    
    async def _alerting_task(self):
        """Background task for alert management"""
        while self.is_running:
            try:
                # Clean up resolved alerts
                current_time = datetime.now()
                recovery_time = getattr(self.config, 'ALERT_RECOVERY_CONFIRMATION_TIME', 180)
                
                resolved_alerts = []
                for metric_name, alert in self.active_alerts.items():
                    if (current_time - alert.timestamp).total_seconds() > recovery_time:
                        # Check if condition is still present
                        if not self._is_alert_condition_active(alert):
                            resolved_alerts.append(metric_name)
                
                for metric_name in resolved_alerts:
                    del self.active_alerts[metric_name]
                    logger.info(f"Alert resolved for metric: {metric_name}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in alerting task: {e}")
                await asyncio.sleep(30)
    
    async def _config_tuning_task(self):
        """Background task for configuration tuning analysis"""
        while self.is_running:
            try:
                if getattr(self.config, 'CONFIG_TUNING_ENABLED', True):
                    # Analyze usage patterns
                    self.usage_patterns = self.analyze_usage_patterns()
                    
                    # Generate recommendations
                    recommendations = self.generate_config_recommendations()
                    validated_recommendations = self.validate_recommendations(recommendations)
                    
                    if validated_recommendations:
                        logger.info(f"Generated {len(validated_recommendations)} configuration recommendations")
                        for rec in validated_recommendations:
                            logger.info(f"Recommendation: {rec.parameter_name} -> {rec.recommended_value} "
                                      f"(confidence: {rec.confidence:.2f})")
                
                await asyncio.sleep(getattr(self.config, 'CONFIG_TUNING_ANALYSIS_WINDOW', 3600))
                
            except Exception as e:
                logger.error(f"Error in config tuning task: {e}")
                await asyncio.sleep(300)
    
    async def _cleanup_task(self):
        """Background task for cleaning up old data"""
        while self.is_running:
            try:
                # Clean up old metrics
                retention_days = getattr(self.config, 'PERFORMANCE_METRICS_RETENTION_DAYS', 30)
                cutoff_time = datetime.now() - timedelta(days=retention_days)
                
                # Clean up alert history
                self.alert_history = deque([
                    alert for alert in self.alert_history 
                    if alert.timestamp > cutoff_time
                ], maxlen=1000)
                
                # Clean up alert suppression
                self.alert_suppression = {
                    metric: timestamp for metric, timestamp in self.alert_suppression.items()
                    if timestamp > cutoff_time
                }
                
                await asyncio.sleep(getattr(self.config, 'PERFORMANCE_DATA_CLEANUP_INTERVAL', 86400))
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(3600)
    
    # Helper Methods
    def _calculate_overall_api_avg(self) -> float:
        """Calculate overall average API response time"""
        try:
            all_times = []
            for times in self.current_metrics.api_response_times.values():
                all_times.extend(times)
            
            return statistics.mean(all_times) if all_times else 0.0
            
        except Exception:
            return 0.0
    
    def _calculate_overall_success_rate(self) -> float:
        """Calculate overall API success rate"""
        try:
            all_results = []
            for results in self.current_metrics.api_success_rates.values():
                all_results.extend(results)
            
            return sum(all_results) / len(all_results) if all_results else 1.0
            
        except Exception:
            return 1.0
    
    def _get_slow_endpoints(self) -> List[str]:
        """Get list of slow endpoints"""
        try:
            slow_endpoints = []
            threshold = getattr(self.config, 'API_SLOW_ENDPOINT_THRESHOLD', 3.0)
            
            for endpoint, times in self.current_metrics.api_response_times.items():
                if times and statistics.mean(times) > threshold:
                    slow_endpoints.append(endpoint)
            
            return slow_endpoints
            
        except Exception:
            return []
    
    def _is_alert_condition_active(self, alert: Alert) -> bool:
        """Check if alert condition is still active"""
        try:
            # This would need specific logic for each metric type
            # For now, assume condition is resolved if we haven't seen it recently
            return False
            
        except Exception:
            return False
    
    async def _generate_final_report(self):
        """Generate final performance report on shutdown"""
        try:
            final_report = self.generate_performance_report()
            logger.info("=== FINAL PERFORMANCE REPORT ===")
            logger.info(f"System Health Score: {final_report['summary']['system_health_score']:.3f}")
            logger.info(f"Total API Endpoints Monitored: {len(final_report['summary']['api_performance'])}")
            logger.info(f"Cache Hit Ratio: {final_report['summary']['cache_performance']['hit_ratio']:.3f}")
            logger.info(f"Active Alerts: {final_report['alerts']['active_count']}")
            logger.info(f"Configuration Recommendations: {len(final_report['recommendations'])}")
            
        except Exception as e:
            logger.error(f"Error generating final report: {e}")
