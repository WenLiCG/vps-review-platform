"""Pure helpers for the offline review contract.

This module does not replace ``vps-analysis/1``, does not read the network,
and does not invent affiliate links. Callers pass already extracted fields.
Synthetic fixtures live under ``tests/fixtures/offline-spec``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from statistics import median


SHANGHAI = timezone(timedelta(hours=8))
SCHEMA = "1.0.0-offline"
STABILITY_TAGS = frozenset({"#线路稳定", "线路稳定"})
PERIOD_LABELS = {1: "mo", 3: "qtr", 6: "sem", 12: "yr", 24: "2yr", 36: "3yr"}
# vps-analysis/1 stores one current value per field, and a new post maps to one
# reviewed object. These fixture behaviors do not fit that shape.
UNADAPTED = {
    "FX-002": "一帖两个套餐。vps-analysis/1 每个字段只有一个当前值，新帖目录映射也只接受一个核读对象。不从两个套餐里挑一个当成整帖。",
    "FX-003": "正文与图片冲突要求 keep_both。vps-analysis/1 的 conflict 只能把该字段留空，不能同时保留两个候选和 resolution。不选 2GB 或 4GiB。",
}
# Fixture expected files convert a date-only string into Beijing midnight.
# This module does not: inferred_weak is not an explicit offset.
INFERRED_TIME_CASES = frozenset({"FX-008A", "FX-008B", "FX-011"})
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_MISSING_CURRENCY_RE = re.compile(r"(?:未写|没有|缺)币种|默认\s*(?:USD|美元)")
_EXPLICIT_OFFSET_RE = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$", re.I)
_BEIJING_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?\s*(?:[（(]北京时间[）)]|北京时间)$"
)
_UTC_WORD_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?\s*(?:UTC|GMT)$", re.I
)
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GIA_RE = re.compile(r"CN2[\s_]*GIA|CTG[\s_]*GIA", re.I)


def unspecified_currency(currency, note="") -> bool:
    """True when a currency was absent or only filled by the old USD default."""
    text = note or ""
    if currency is None or (isinstance(currency, str) and not currency.strip()):
        return True
    return _MISSING_CURRENCY_RE.search(text) is not None


def normalize_price(price: dict) -> dict:
    """Keep an explicit ISO currency. Missing currency stays null, never USD."""
    if not isinstance(price, dict):
        raise TypeError("price must be an object")
    note = price.get("note") or price.get("currency_basis") or ""
    amount = price.get("amount")
    months = price.get("billing_period_months")
    role = price.get("term_role") if price.get("term_role") in {"first_term", "renewal", "unknown"} else "unknown"
    currency = price.get("currency")
    if unspecified_currency(currency, note):
        return {
            "currency": None, "amount": amount, "billing_period_months": months,
            "term_role": role, "monthly_equivalent": None, "status": "unknown",
        }
    code = str(currency).upper()
    if _CURRENCY_RE.fullmatch(code) is None:
        return {
            "currency": None, "amount": amount, "billing_period_months": months,
            "term_role": role, "monthly_equivalent": None, "status": "unknown",
        }
    monthly = None
    if isinstance(amount, (int, float)) and not isinstance(amount, bool) and isinstance(months, int) and months > 0:
        monthly = amount / months
        if isinstance(monthly, float) and monthly.is_integer():
            monthly = int(monthly)
    return {
        "currency": code, "amount": amount, "billing_period_months": months,
        "term_role": role, "monthly_equivalent": monthly, "status": "reported",
    }


def retain_unit(value, unit):
    """Return the original magnitude and unit. GB and GiB are not converted."""
    allowed = {None, "GB", "GiB", "MB", "MiB", "TB", "TiB"}
    if unit not in allowed:
        raise ValueError("unsupported capacity unit")
    return {"value": value, "unit": unit}


def resolve_tested_at(raw, published_at=None) -> dict:
    """Convert to Asia/Shanghai only when the source itself has an explicit zone.

    ``published_at`` is accepted so callers can prove it is ignored. A date
    with no offset, or an ambiguous CST label, stays unconverted.
    """
    del published_at
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {"tested_at_raw": None if raw is None else raw, "tested_at_beijing": None,
                "tz_confidence": "unknown"}
    text = str(raw).strip()
    ambiguous = re.search(r"\bCST\b|中国标准时间", text) and not (
        _EXPLICIT_OFFSET_RE.search(text) or "北京时间" in text or re.search(r"\b(?:UTC|GMT)\b", text)
    )
    if ambiguous:
        return {"tested_at_raw": text, "tested_at_beijing": None, "tz_confidence": "inferred_weak"}
    beijing_match = _BEIJING_RE.fullmatch(text)
    if beijing_match:
        second = beijing_match.group(3) or "00"
        moment = datetime.fromisoformat(f"{beijing_match.group(1)}T{beijing_match.group(2)}:{second}+08:00")
        return {"tested_at_raw": text, "tested_at_beijing": _shanghai(moment), "tz_confidence": "explicit"}
    utc_match = _UTC_WORD_RE.fullmatch(text)
    if utc_match:
        second = utc_match.group(3) or "00"
        moment = datetime.fromisoformat(f"{utc_match.group(1)}T{utc_match.group(2)}:{second}+00:00")
        return {"tested_at_raw": text, "tested_at_beijing": _shanghai(moment), "tz_confidence": "explicit"}
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    if _EXPLICIT_OFFSET_RE.search(text) or text.endswith(("Z", "z")):
        moment = datetime.fromisoformat(iso)
        if moment.utcoffset() is None:
            return {"tested_at_raw": text, "tested_at_beijing": None, "tz_confidence": "inferred_weak"}
        return {"tested_at_raw": text, "tested_at_beijing": _shanghai(moment), "tz_confidence": "explicit"}
    if _DATE_ONLY_RE.fullmatch(text):
        return {"tested_at_raw": text, "tested_at_beijing": None, "tz_confidence": "inferred_weak"}
    return {"tested_at_raw": text, "tested_at_beijing": None, "tz_confidence": "unknown"}


def derive_route_tags(asn_path, stated_labels) -> list:
    """Keep labels the source actually stated. AS4809 alone is not CN2 GIA."""
    path = [int(item) for item in (asn_path or [])]
    tags = []
    for label in stated_labels or []:
        if not isinstance(label, str) or not label.strip():
            continue
        tags.append(label.strip())
    if 4809 in path and not any(_GIA_RE.search(label) for label in tags):
        tags = [label for label in tags if _GIA_RE.search(label) is None]
    return tags


def derive_samples(observations, minimum: int = 5) -> dict:
    """Count Geekbench 6 single-core by run_id. One run is one sample.

    A stability tag is omitted below ``minimum`` independent runs. Median stays
    null for a single raw row; repeated rows inside one run still count once.
    """
    if not isinstance(minimum, int) or minimum < 1:
        raise ValueError("minimum sample count must be a positive integer")
    runs: dict[str, list] = {}
    raw_rows = 0
    for observation in observations or []:
        run_id = observation.get("run_id")
        for bench in observation.get("benchmarks") or []:
            if bench.get("suite") == "geekbench" and bench.get("version_major") == 6 and bench.get("metric") == "single_core":
                raw_rows += 1
                runs.setdefault(run_id, []).append(bench.get("score"))
    per_run = [median(scores) for scores in runs.values() if scores]
    sample_count = len(runs)
    if sample_count == 0 or raw_rows < 2:
        gb6_median = None
    else:
        gb6_median = median(per_run)
        if isinstance(gb6_median, float) and gb6_median.is_integer():
            gb6_median = int(gb6_median)
    # route_stability stays null: one observed route is not a stability finding,
    # and this batch does not synthesize a label once `minimum` is reached either.
    return {
        "tags": [],
        "aggregates": {
            "route_stability": None,
            "gb6_single_median": gb6_median,
            "gb6_single_samples": sample_count,
        },
        "sample_policy": {"min_samples_for_stability_tag": minimum, "dedupe_by_run_id": True},
    }


def benchmark_buckets(observations) -> dict:
    """Group scores by suite, major version and metric. Versions are not merged."""
    buckets: dict[tuple, list] = {}
    for observation in observations or []:
        for bench in observation.get("benchmarks") or []:
            key = (bench.get("suite"), bench.get("version_major"), bench.get("metric"))
            buckets.setdefault(key, []).append(bench.get("score"))
    return buckets


def affiliate_url(config=None):
    """Operator-supplied purchase link. The shipped config is empty."""
    if not isinstance(config, dict):
        return None
    value = config.get("affiliate_url")
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith("https://") or re.search(r"\s", value):
        return None
    parsed_userinfo = "://" in value and "@" in value.split("://", 1)[1].split("/", 1)[0]
    if parsed_userinfo:
        return None
    return value


def affiliate_from_source(source_text, config=None):
    """Source text is never mined for a purchase link."""
    del source_text
    return affiliate_url(config)


def apply_explicit_times(document) -> dict:
    """Copy a normalized document, replacing test times with the strict resolver."""
    import copy
    cloned = copy.deepcopy(document)
    published = (cloned.get("source") or {}).get("published_at")
    for observation in cloned.get("observations") or []:
        resolved = resolve_tested_at(observation.get("tested_at_raw"), published_at=published)
        observation["tested_at_beijing"] = resolved["tested_at_beijing"]
        observation["tz_confidence"] = resolved["tz_confidence"]
    return cloned


def suggest_filenames(documents) -> dict:
    """Build ``{post_id: filename}`` for one batch.

    A missing test date, or two documents with the same base name, appends
    ``__{source_post_id}``. Renewal price is used; a first-term price is not.
    """
    prepared = [apply_explicit_times(document) for document in documents]
    bases = [_base_name(document) for document in prepared]
    counts: dict[str, int] = {}
    for base in bases:
        counts[base] = counts.get(base, 0) + 1
    names = {}
    for document, base in zip(prepared, bases):
        post_id = document["source"]["source_post_id"]
        if "unknownDate" in base or counts[base] > 1:
            names[post_id] = f"{base}__{post_id}"
        else:
            names[post_id] = base
    return names


def vps_analysis_adaptation(case_id: str) -> dict:
    """Say whether this fixture can live in the existing single-value analysis."""
    if case_id in UNADAPTED:
        return {
            "adapted": False, "target_schema": "vps-analysis/1", "case_id": case_id,
            "reason": UNADAPTED[case_id], "selected_plan_id": None,
            "monthly_price": None, "memory_mb": None,
        }
    return {
        "adapted": True, "target_schema": "vps-analysis/1", "case_id": case_id,
        "reason": "单套餐字段可以用离线函数核对，不改写 vps-analysis/1。",
    }


def _shanghai(moment: datetime) -> str:
    return moment.astimezone(SHANGHAI).replace(microsecond=0).isoformat()


def _number_token(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return format(value, "g")


def _price_token(prices) -> str:
    normalized = [normalize_price(price) for price in prices or []]
    renewals = [price for price in normalized if price["status"] == "reported" and price["term_role"] == "renewal"]
    monthly = [price for price in renewals if price["billing_period_months"] == 1]
    if len(monthly) == 1:
        chosen = monthly[0]
    elif len(monthly) > 1:
        usd = [price for price in monthly if price["currency"] == "USD"]
        if len(usd) != 1:
            return "unknownPrice"
        chosen = usd[0]
    elif len(renewals) == 1:
        chosen = renewals[0]
    else:
        return "unknownPrice"
    months = chosen["billing_period_months"]
    period = PERIOD_LABELS.get(months, f"{months}mo")
    return f"{_number_token(chosen['amount'])}{chosen['currency']}-{period}"


def _location_token(plans) -> str:
    cities = []
    for plan in plans:
        location = (plan.get("fields") or {}).get("location")
        city = location.get("city") if isinstance(location, dict) else None
        if city and city not in cities:
            cities.append(city)
    if len(cities) == 1:
        return cities[0]
    return "unknownLoc"


def _disk_token(fields) -> str | None:
    value, unit = fields.get("disk_value"), fields.get("disk_unit")
    kept = retain_unit(value, unit)
    if kept["value"] is None or kept["unit"] is None:
        return None
    if kept["unit"] == "GB":
        return f"{_number_token(kept['value'])}G"
    if kept["unit"] == "GiB":
        return f"{_number_token(kept['value'])}GiB"
    return f"{_number_token(kept['value'])}{kept['unit']}"


def _memory_token(fields) -> str | None:
    memory = fields.get("memory_mb")
    if memory is None:
        return None
    if isinstance(memory, int) and memory % 1024 == 0:
        return f"{memory // 1024}G"
    return None


def _config_token(fields) -> str:
    cpu, memory, disk = fields.get("vcpu"), _memory_token(fields), _disk_token(fields)
    if cpu is None and memory is None and disk is None:
        return "unknownCfg"
    if cpu is None and memory is None and disk is not None:
        return f"unknownC{disk}"
    token = f"{_number_token(cpu)}C" if cpu is not None else "unknownC"
    if memory is not None:
        token += memory
    if disk is not None:
        token += disk
    return token


def _date_token(observations) -> str:
    dates = []
    for observation in observations or []:
        if observation.get("tz_confidence") != "explicit":
            continue
        beijing = observation.get("tested_at_beijing")
        if isinstance(beijing, str) and re.match(r"\d{4}-\d{2}-\d{2}", beijing):
            dates.append(beijing[:10].replace("-", ""))
    if not dates:
        return "unknownDate"
    return sorted(dates)[0]


def _base_name(document) -> str:
    plans = document["plans"]
    date = _date_token(document.get("observations") or [])
    if len(plans) > 1:
        return f"MULTI_{_location_token(plans)}_{date}"
    plan = plans[0]
    return f"{_price_token(plan.get('prices') or [])}_{_location_token(plans)}_{_config_token(plan['fields'])}_{date}"
