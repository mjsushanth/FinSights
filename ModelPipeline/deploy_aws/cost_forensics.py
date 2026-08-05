"""
Read-only Cost Explorer forensics for the deployment account.

What this module does
---------------------
Answers three questions about AWS spend, using Cost Explorer only:

1. What did each service cost, per day, over a window?
2. Which USAGE TYPES drive each service? This is where always-on cost hides.
3. What is the recurring floor - the cost of changing nothing at all?

Why it exists
-------------
Three reasons, all learned the hard way on 2026-08-05.

1. Service-level totals are not actionable. "Amazon Virtual Private Cloud -
   $0.006" names no resource. `USE1-PublicIPv4:InUseAddress` names exactly
   what to delete. Grouping by USAGE_TYPE is the whole technique, so this
   module makes that the default rather than an extra step.

2. The 2026-07-31 deploy ledger recorded Fargate ARM pricing as UNVERIFIED
   because the AWS Pricing API returns no Fargate usage types under service
   code AmazonECS. Cost Explorer does report them, as cost divided by usage
   quantity. `unit_rates()` exists to close that specific gap, and did:
   $0.032380/vCPU-hr and $0.003560/GB-hr, matching the published rates.

3. Cost arithmetic must not be done in float. Every amount here is Decimal
   from the moment it leaves the API. A cent of drift in a $0.29 figure is a
   3% error.

Cost of running this
--------------------
Cost Explorer bills roughly $0.01 per API request. `full_report()` issues one
request per service plus one for the daily series, so a nine-service account
costs about $0.10 to analyse. Usage-type results are cached per service so no
service is queried twice. The __main__ self-test makes NO API calls by
default for exactly this reason - pass --live to hit the API.

Inputs
------
A DeployConfig (for profile name and region) via AwsSession.

Outputs
-------
Decimal-typed cost breakdowns; a logged report when run as __main__.

Usage
-----
    from deploy_aws.aws_session import AwsSession
    from deploy_aws.config import DeployConfig
    from deploy_aws.cost_forensics import CostForensics

    cf = CostForensics(AwsSession(DeployConfig.from_env()))
    cf.log_report("2026-07-01", "2026-08-06")

    # Or from the shell, offline logic check only:
    python -m deploy_aws.cost_forensics
    python -m deploy_aws.cost_forensics --live --start 2026-08-01 --end 2026-08-06
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from deploy_aws.aws_session import AwsSession
from deploy_aws.config import DeployConfig

logger = logging.getLogger(__name__)

# Usage-type substrings that bill for merely existing, with zero traffic.
# These are the charges that survive "but I turned everything off".
ALWAYS_ON_MARKERS: tuple[str, ...] = (
    "NatGateway",       # ~$0.045/hr to exist, plus per-GB processed
    "VpcEndpoint",      # PrivateLink, per endpoint per AZ
    "IdleAddress",      # unattached Elastic IP
    "PublicIPv4",       # in-use public IPv4, $0.005/hr - billed per Fargate task
    "LoadBalancer",     # ALB/NLB hourly
    "TimedStorage",     # S3 Standard, S3 Vectors, and ECR storage per GB-month
    "CW:",              # CloudWatch metrics, logs, dashboards
)

# Charge types that are not consumption and would distort a spend analysis.
_EXCLUDED_RECORD_TYPES: tuple[str, ...] = ("Credit", "Refund")


class CostForensics:
    """Read-only Cost Explorer queries. Creates and modifies nothing."""

    def __init__(self, aws: AwsSession) -> None:
        self._aws = aws
        self._usage_cache: dict[str, dict[str, Decimal]] = {}

    # -- low-level ---------------------------------------------------------

    def _query(
        self,
        start: str,
        end: str,
        group_by: str,
        granularity: str = "DAILY",
        service: str | None = None,
    ) -> list[dict[str, Any]]:
        """One GetCostAndUsage call. `end` is EXCLUSIVE, per the AWS API."""
        cost_filter: dict[str, Any] = {
            "Not": {"Dimensions": {"Key": "RECORD_TYPE",
                                   "Values": list(_EXCLUDED_RECORD_TYPES)}}
        }
        if service:
            cost_filter = {
                "And": [cost_filter,
                        {"Dimensions": {"Key": "SERVICE", "Values": [service]}}]
            }
        response = self._aws.client("ce").get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity=granularity,
            Metrics=["UnblendedCost", "UsageQuantity"],
            GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
            Filter=cost_filter,
        )
        return response["ResultsByTime"]

    # -- aggregation -------------------------------------------------------

    @staticmethod
    def totals_by_key(results: list[dict[str, Any]]) -> dict[str, Decimal]:
        """Sum UnblendedCost per group key across every time bucket."""
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for bucket in results:
            for group in bucket["Groups"]:
                amount = group["Metrics"]["UnblendedCost"]["Amount"]
                totals[group["Keys"][0]] += Decimal(amount)
        return dict(totals)

    @staticmethod
    def daily_totals(results: list[dict[str, Any]]) -> dict[str, Decimal]:
        """Sum UnblendedCost per day across all groups.

        The shape of this series is the single most diagnostic thing in cost
        analysis: flat means infrastructure billing for existing, spiky means
        something was invoked.
        """
        series: dict[str, Decimal] = {}
        for bucket in results:
            series[bucket["TimePeriod"]["Start"]] = sum(
                (Decimal(g["Metrics"]["UnblendedCost"]["Amount"])
                 for g in bucket["Groups"]),
                Decimal(0),
            )
        return series

    @staticmethod
    def is_always_on(usage_type: str) -> bool:
        """True if this usage type bills with no traffic at all."""
        return any(marker in usage_type for marker in ALWAYS_ON_MARKERS)

    # -- public API --------------------------------------------------------

    def by_service(self, start: str, end: str) -> dict[str, Decimal]:
        """Total cost per service over the window."""
        return self.totals_by_key(self._query(start, end, "SERVICE"))

    def by_usage_type(self, start: str, end: str, service: str) -> dict[str, Decimal]:
        """Usage-type breakdown for one service. Cached - one API call each."""
        if service not in self._usage_cache:
            self._usage_cache[service] = self.totals_by_key(
                self._query(start, end, "USAGE_TYPE",
                            granularity="MONTHLY", service=service)
            )
        return self._usage_cache[service]

    def unit_rates(self, start: str, end: str, service: str) -> dict[str, Decimal]:
        """Derive $/unit per usage type as cost divided by usage quantity.

        This is how to price a resource the Pricing API will not quote - and
        how to project a monthly run rate from a few hours of history.
        Usage types with zero quantity are omitted rather than dividing by zero.
        """
        rates: dict[str, Decimal] = {}
        for bucket in self._query(start, end, "USAGE_TYPE",
                                  granularity="MONTHLY", service=service):
            for group in bucket["Groups"]:
                quantity = Decimal(group["Metrics"]["UsageQuantity"]["Amount"])
                if quantity == 0:
                    continue
                cost = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                rates[group["Keys"][0]] = cost / quantity
        return rates

    def idle_floor(self, day: str) -> tuple[Decimal, dict[str, Decimal]]:
        """Cost of a single day, and its always-on subset.

        Pick a day with no activity and this is the true recurring floor -
        measured rather than estimated. Averaging across a longer window
        understates it whenever resources were created partway through, which
        is exactly how a $0.29/month floor got reported as $0.02.
        """
        next_day = date.fromisoformat(day).toordinal() + 1
        results = self._query(day, date.fromordinal(next_day).isoformat(),
                              "USAGE_TYPE", granularity="DAILY")
        totals = self.totals_by_key(results)
        always_on = {k: v for k, v in totals.items() if self.is_always_on(k)}
        return sum(totals.values(), Decimal(0)), always_on

    # -- reporting ---------------------------------------------------------

    def log_report(self, start: str, end: str, threshold: Decimal = Decimal("0.0001")) -> None:
        """Log the full breakdown. One API call per service, plus one."""
        service_results = self._query(start, end, "SERVICE")
        services = self.totals_by_key(service_results)
        grand = sum(services.values(), Decimal(0))

        logger.info("account=%s window=%s -> %s (end exclusive)",
                    self._aws.account_id, start, end)
        logger.info("--- per-service totals ---")
        for name, amount in sorted(services.items(), key=lambda kv: -kv[1]):
            if amount >= threshold:
                share = (amount / grand * 100) if grand else Decimal(0)
                logger.info("  $%.6f  %5.1f%%  %s", amount, share, name)
        logger.info("  $%.6f  100.0%%  TOTAL", grand)

        logger.info("--- daily total (flat=always-on, spiky=invoked) ---")
        for day, amount in sorted(self.daily_totals(service_results).items()):
            logger.info("  %s  $%.6f", day, amount)

        logger.info("--- usage types ([ALWAYS-ON] bills with zero traffic) ---")
        recurring = Decimal(0)
        for name, amount in sorted(services.items(), key=lambda kv: -kv[1]):
            if amount < threshold:
                continue
            logger.info("  %s ($%.6f)", name, amount)
            for utype, uamount in sorted(self.by_usage_type(start, end, name).items(),
                                         key=lambda kv: -kv[1]):
                if uamount < threshold:
                    continue
                tag = "[ALWAYS-ON] " if self.is_always_on(utype) else ""
                logger.info("      $%.6f  %s%s", uamount, tag, utype)
                if self.is_always_on(utype):
                    recurring += uamount

        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        logger.info("--- recurring floor ---")
        logger.info("  always-on over %dd: $%.6f", days, recurring)
        if days:
            logger.info("  per 30d: $%.4f", recurring / days * 30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Read-only AWS cost forensics.")
    parser.add_argument("--live", action="store_true",
                        help="hit Cost Explorer (~$0.01 per request); off by default")
    parser.add_argument("--start", default="2026-08-01")
    parser.add_argument("--end", default="2026-08-06", help="EXCLUSIVE")
    args = parser.parse_args()

    # Offline self-test. Makes no API calls and creates nothing, matching the
    # convention every other module in this package follows.
    assert CostForensics.is_always_on("USE1-PublicIPv4:InUseAddress")
    assert CostForensics.is_always_on("Vectors-TimedStorage-ByteHrs")
    assert CostForensics.is_always_on("USE1-NatGateway-Hours")
    assert not CostForensics.is_always_on("USE1-Fargate-ARM-vCPU-Hours:perCPU")
    assert not CostForensics.is_always_on("USE1-MP:USE1_InputTokenCount-Units")
    logger.info("always-on classification: OK")

    synthetic = [{
        "TimePeriod": {"Start": "2026-08-03"},
        "Groups": [
            {"Keys": ["A"], "Metrics": {"UnblendedCost": {"Amount": "0.0048410"}}},
            {"Keys": ["B"], "Metrics": {"UnblendedCost": {"Amount": "0.0049531"}}},
        ],
    }]
    assert CostForensics.daily_totals(synthetic)["2026-08-03"] == Decimal("0.0097941")
    assert CostForensics.totals_by_key(synthetic)["A"] == Decimal("0.0048410")
    logger.info("Decimal aggregation: OK (no float drift)")

    if args.live:
        logger.info("--live: querying Cost Explorer, this costs about $0.01 per request")
        CostForensics(AwsSession(DeployConfig.from_env())).log_report(args.start, args.end)
    else:
        logger.info("offline self-test passed; pass --live to query Cost Explorer")
