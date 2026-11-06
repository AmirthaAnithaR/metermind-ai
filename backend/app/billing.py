from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional

# Configurable rates dictionary allowing tiers and adjustments
PRICING_CONFIG: Dict[str, Any] = {
    "base_rate_per_100_requests": Decimal("1.00"),
    "currency": "USD",
    # Future tiers can be configured here:
    # "tier_1": {"max_requests": 1000, "rate": Decimal("1.00")},
    # "tier_2": {"max_requests": 10000, "rate": Decimal("0.80")},
}

def calculate_bill(total_requests: int, config: Optional[Dict[str, Any]] = None) -> Decimal:
    """
    Calculate bill based on request count:
    Bill = (total_requests / 100) * 1.00 USD, rounded to 2 decimals with Decimal.
    
    Args:
        total_requests: Number of API requests made.
        config: Optional pricing configuration dictionary.
    
    Returns:
        Decimal amount rounded to 2 decimal places with ROUND_HALF_UP.
    """
    if total_requests < 0:
        raise ValueError("total_requests cannot be negative")
    
    active_config = config if config is not None else PRICING_CONFIG
    rate = active_config.get("base_rate_per_100_requests", Decimal("1.00"))
    if not isinstance(rate, Decimal):
        rate = Decimal(str(rate))
    
    requests_dec = Decimal(total_requests)
    
    # Bill = (total_requests / 100) * rate
    bill = (requests_dec / Decimal("100")) * rate
    
    return bill.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
