
import logging
import time
from typing import Dict, Any, Optional
from app.db.session import AsyncSessionLocal
from app.db.models import UsageMetric

logger = logging.getLogger(__name__)

class MetricsService:
    @staticmethod
    async def record_usage(
        session_id: str,
        user_id: str,
        user_role: str,
        feature: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        status: str = "ok"
    ):
        """
        Asynchronously save usage metrics to the database.
        """
        try:
            async with AsyncSessionLocal() as session:
                metric = UsageMetric(
                    session_id=session_id,
                    user_id=user_id,
                    user_role=user_role,
                    feature=feature,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    status=status
                )
                session.add(metric)
                await session.commit()
                # logger.info(f"Recorded usage metric: {feature} by {user_role} ({user_id})")
        except Exception as e:
            logger.error(f"Failed to record usage metric: {e}")

    @staticmethod
    async def get_aggregates(hours_back: float = 1):
        """
        Retrieve basic aggregates for the dashboard with time-range filtering.
        """
        from sqlalchemy import func, select, text, case
        from datetime import datetime, timedelta, timezone
        
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        async with AsyncSessionLocal() as session:
            # 1. Token usage by Role
            role_stmt = select(
                UsageMetric.user_role,
                func.sum(UsageMetric.tokens_in).label("total_in"),
                func.sum(UsageMetric.tokens_out).label("total_out")
            ).where(UsageMetric.timestamp >= since).group_by(UsageMetric.user_role)
            
            role_res = await session.execute(role_stmt)
            role_data = [{"role": r[0], "total_in": r[1], "total_out": r[2]} for r in role_res.all()]
            
            # 2. Feature popularity
            feat_stmt = select(
                UsageMetric.feature,
                func.count(UsageMetric.id).label("count")
            ).where(UsageMetric.timestamp >= since).group_by(UsageMetric.feature)
            
            feat_res = await session.execute(feat_stmt)
            feat_data = [{"feature": f[0], "count": f[1]} for f in feat_res.all()]
            
            # 3. Per-User Usage Table
            user_stmt = select(
                UsageMetric.user_id,
                UsageMetric.user_role,
                func.sum(UsageMetric.tokens_in).label("total_in"),
                func.sum(UsageMetric.tokens_out).label("total_out"),
                func.max(UsageMetric.timestamp).label("last_seen")
            ).where(UsageMetric.timestamp >= since).group_by(UsageMetric.user_id, UsageMetric.user_role)
            
            user_res = await session.execute(user_stmt)
            user_data = [
                {
                    "user_id": r[0], 
                    "role": r[1], 
                    "total_in": r[2], 
                    "total_out": r[3],
                    "total_tokens": r[2] + r[3],
                    "last_seen": r[4].strftime("%Y-%m-%d %H:%M:%S") if r[4] else "N/A"
                } 
                for r in user_res.all()
            ]
            
            # 4. Raw Interaction Log (Last 100 in range)
            log_stmt = select(
                UsageMetric.timestamp,
                UsageMetric.user_id,
                UsageMetric.user_role,
                UsageMetric.feature,
                UsageMetric.tokens_in,
                UsageMetric.tokens_out,
                UsageMetric.latency_ms,
                UsageMetric.status
            ).where(UsageMetric.timestamp >= since).order_by(UsageMetric.timestamp.desc()).limit(100)
            
            log_res = await session.execute(log_stmt)
            log_data = [
                {
                    "timestamp": r[0].strftime("%Y-%m-%d %H:%M:%S"),
                    "user_id": r[1],
                    "role": r[2],
                    "feature": r[3],
                    "tokens_in": r[4],
                    "tokens_out": r[5],
                    "latency_ms": round(r[6], 2),
                    "status": r[7]
                }
                for r in log_res.all()
            ]
            
            # 5. Time Series (Buceted in range)
            ts_stmt = select(
                func.date_format(UsageMetric.timestamp, "%Y-%m-%d %H:%i:00").label("minute"),
                func.count(UsageMetric.id).label("req_count"),
                func.sum(UsageMetric.tokens_in).label("total_in"),
                func.sum(UsageMetric.tokens_out).label("total_out"),
                func.sum(case((UsageMetric.status == 'ok', 1), else_=0)).label("status_200"),
                func.sum(case((UsageMetric.status != 'ok', 1), else_=0)).label("status_err")
            ).where(UsageMetric.timestamp >= since).group_by(text("minute")).order_by(text("minute"))
            
            ts_res = await session.execute(ts_stmt)
            ts_data = [
                {
                    "minute": r[0],
                    "requests": r[1],
                    "tokens_in": int(r[2] or 0),
                    "tokens_out": int(r[3] or 0),
                    "tokens_total": int((r[2] or 0) + (r[3] or 0)),
                    "status_200": int(r[4] or 0),
                    "status_err": int(r[5] or 0)
                }
                for r in ts_res.all()
            ]

            # 6. Average Latency (in range)
            lat_stmt = select(func.avg(UsageMetric.latency_ms)).where(UsageMetric.timestamp >= since)
            lat_res = await session.execute(lat_stmt)
            avg_lat = lat_res.scalar() or 0

            # 7. Health Score (in range)
            health_stmt = select(
                func.sum(case((UsageMetric.status == 'ok', 1), else_=0)).label("ok_count"),
                func.count(UsageMetric.id).label("total_count")
            ).where(UsageMetric.timestamp >= since)
            health_res = await session.execute(health_stmt)
            h_row = health_res.one()
            health_score = round((h_row[0] / h_row[1] * 100), 2) if h_row[1] > 0 else 100

            # 8. Heatmap Data (Requests by Hour of Day in range)
            heatmap_stmt = select(
                func.hour(UsageMetric.timestamp).label("hour"),
                func.count(UsageMetric.id).label("count")
            ).where(UsageMetric.timestamp >= since).group_by(text("hour")).order_by(text("hour"))
            heatmap_res = await session.execute(heatmap_stmt)
            heatmap_data = [{"hour": r[0], "count": r[1]} for r in heatmap_res.all()]

            # 9. Slow SQL Queries (in range)
            slow_sql_stmt = select(
                UsageMetric.session_id,
                UsageMetric.latency_ms,
                UsageMetric.tokens_out,
                UsageMetric.timestamp
            ).where((UsageMetric.feature == 'sql') & (UsageMetric.timestamp >= since)).order_by(UsageMetric.latency_ms.desc()).limit(5)
            slow_sql_res = await session.execute(slow_sql_stmt)
            slow_queries = [
                {"session": r[0], "latency": round(r[1], 2), "tokens": r[2], "time": r[3].strftime("%H:%M:%S")} 
                for r in slow_sql_res.all()
            ]

            # 10. Cost Estimation ($ per 1M tokens) - Llama 3.1 8B Groq-style pricing
            # $0.05 / 1M input, $0.08 / 1M output
            total_in = sum(float(r['total_in'] or 0) for r in role_data)
            total_out = sum(float(r['total_out'] or 0) for r in role_data)
            estimated_cost = round(((total_in * 0.05) + (total_out * 0.08)) / 1_000_000, 6)

            return {
                "roles": role_data,
                "features": feat_data,
                "users": user_data,
                "logs": log_data,
                "time_series": ts_data,
                "avg_latency": round(avg_lat, 2),
                "health_score": health_score,
                "heatmap": heatmap_data,
                "slow_queries": slow_queries,
                "estimated_cost_usd": estimated_cost
            }
