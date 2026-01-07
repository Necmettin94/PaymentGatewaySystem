from dataclasses import dataclass

from app.config import settings


@dataclass
class RateLimitRule:
    pattern: str
    method: str
    limit_attr: str
    window_seconds: int
    description: str = ""

    def get_limit(self) -> int:
        return getattr(settings, self.limit_attr)


class RateLimitConfig:
    RULES = [
        RateLimitRule(
            pattern="/api/v1/users/me/balance",
            method="GET",
            limit_attr="rate_limit_per_user_balance",
            window_seconds=60,
            description="balance check",
        ),
        RateLimitRule(
            pattern="/api/v1/users/me/transactions",
            method="GET",
            limit_attr="rate_limit_per_user_transactions",
            window_seconds=60,
            description="transaction list",
        ),
        # deposit/withdrawal endpoints are protected by idempotency, not by rate limiting (tasks.md)
    ]

    @classmethod
    def get_rule_for_request(cls, path: str, method: str) -> RateLimitRule | None:
        for rule in cls.RULES:
            if cls._matches_pattern(path, rule.pattern) and method == rule.method:
                return rule
        return None

    @staticmethod
    def _matches_pattern(path: str, pattern: str) -> bool:
        if "{" in pattern:  # regex or manuel check? later
            pattern_prefix = pattern.split("{")[0].rstrip("/")
            return path.startswith(pattern_prefix)

        return path == pattern or path.startswith(pattern)
