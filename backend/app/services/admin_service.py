from typing import List
from datetime import datetime
from app.models.schemas import UserData, AnalyticsData, AuditLog


class AdminService:
    """Service layer for admin operations."""

    def get_users(self) -> List[UserData]:
        """
        Get list of all users.

        Returns:
            List of UserData objects
        """
        users = [
            UserData(
                user_id=1,
                name="John Doe",
                email="john@example.com",
                role="admin",
                created_at=datetime(2024, 1, 15)
            ),
            UserData(
                user_id=2,
                name="Jane Smith",
                email="jane@example.com",
                role="doctor",
                created_at=datetime(2024, 1, 20)
            ),
            UserData(
                user_id=3,
                name="Bob Johnson",
                email="bob@example.com",
                role="user",
                created_at=datetime(2024, 2, 1)
            ),
            UserData(
                user_id=4,
                name="Alice Williams",
                email="alice@example.com",
                role="doctor",
                created_at=datetime(2024, 2, 10)
            ),
        ]
        return users

    def get_analytics(self) -> AnalyticsData:
        """
        Get system analytics data.

        Returns:
            AnalyticsData with system statistics
        """
        analytics = AnalyticsData(
            total_users=4,
            total_documents=12,
            total_queries=156
        )
        return analytics

    def get_audit_logs(self, limit: int = 10) -> List[AuditLog]:
        """
        Get audit logs.

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of AuditLog objects
        """
        logs = [
            AuditLog(
                log_id="log_001",
                action="user_login",
                user_id=1,
                timestamp=datetime(2024, 3, 20, 10, 30),
                details="User logged in from IP 192.168.1.1"
            ),
            AuditLog(
                log_id="log_002",
                action="document_uploaded",
                user_id=2,
                timestamp=datetime(2024, 3, 20, 11, 15),
                details="Uploaded document: clinical_guidelines.pdf"
            ),
            AuditLog(
                log_id="log_003",
                action="query_executed",
                user_id=3,
                timestamp=datetime(2024, 3, 20, 12, 0),
                details="Executed RAG query with top_k=5"
            ),
            AuditLog(
                log_id="log_004",
                action="user_login",
                user_id=4,
                timestamp=datetime(2024, 3, 20, 13, 45),
                details="User logged in from IP 192.168.1.5"
            ),
            AuditLog(
                log_id="log_005",
                action="document_search",
                user_id=1,
                timestamp=datetime(2024, 3, 20, 14, 20),
                details="Searched for documents with query: diabetes treatment"
            ),
            AuditLog(
                log_id="log_006",
                action="user_logout",
                user_id=2,
                timestamp=datetime(2024, 3, 20, 15, 0),
                details="User logged out"
            ),
        ]
        return logs[:limit]

