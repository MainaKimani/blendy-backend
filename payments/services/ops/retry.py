from datetime import timedelta

from django.utils import timezone


def get_backoff_delay_minutes(
    retry_count: int, base_minutes: int = 5, max_minutes: int = 12 * 60
) -> int:
    """Exponential backoff with cap: base * 2^retry_count."""
    return min(base_minutes * (2**retry_count), max_minutes)


def schedule_next_retry(payment) -> None:
    payment.retry_count += 1
    payment.last_retry_at = timezone.now()
    delay_minutes = get_backoff_delay_minutes(payment.retry_count)
    payment.next_retry_at = timezone.now() + timedelta(minutes=delay_minutes)
    payment.save(
        update_fields=["retry_count", "last_retry_at", "next_retry_at", "updated_at"]
    )
