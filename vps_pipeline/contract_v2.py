"""Frozen offline contract v2; public projections use explicit allowlists."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import math
import re

CONTRACT_V2_VERSION = 'contract/v2'
REVIEW_DOCUMENT_SCHEMA_VERSION = 'review-document/v2'
PUBLIC_DTO_V1_VERSION = 'public-dto/v1'
PUBLIC_DTO_V2_VERSION = 'public-dto/v2'
CAPTURE_MANIFEST_SCHEMA_VERSION = 'capture-manifest/v1'
PRICE_SEMANTICS_VERSION = 'price-semantics/v2'
ROOT = Path(__file__).resolve().parents[1]


def normalize_tested_at(tested_at_raw: str | None) -> dict:
    result = dict(tested_at_raw=tested_at_raw, tested_at_beijing=None,
                  tz_confidence='unknown', review_date=None,
                  review_date_precision=None, review_date_tz='unknown',
                  filename_date_segment='unknownDate')
    if tested_at_raw is None:
        return result
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', tested_at_raw):
        day = date.fromisoformat(tested_at_raw)
        result.update(review_date=day.isoformat(), review_date_precision='day',
                      filename_date_segment=day.strftime('%Y%m%d'))
        return result
    stamp = datetime.fromisoformat(tested_at_raw.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        result.update(review_date=stamp.date().isoformat(), review_date_precision='day',
                      filename_date_segment=stamp.strftime('%Y%m%d'))
        return result
    beijing = stamp.astimezone(timezone(timedelta(hours=8)))
    result.update(tested_at_beijing=beijing.isoformat(), tz_confidence='explicit',
                  review_date=beijing.date().isoformat(), review_date_precision='datetime',
                  review_date_tz='Asia/Shanghai', filename_date_segment=beijing.strftime('%Y%m%d'))
    return result


def monthly_equivalent(amount, billing_period_months):
    if (type(billing_period_months) is not int or billing_period_months <= 0
            or type(amount) not in (int, float) or not math.isfinite(amount)):
        return None
    return amount / billing_period_months


def price_eligible_for_range_filter(price) -> bool:
    return (isinstance(price.get('currency'), str)
            and price['currency'] not in ('', 'unknown')
            and monthly_equivalent(price.get('amount'), price.get('billing_period_months')) is not None)


def matches_review_date_filter(review_date, start, end) -> bool:
    if review_date is None:
        return False
    day = date.fromisoformat(review_date[:10])
    return ((start is None or date.fromisoformat(start[:10]) <= day)
            and (end is None or day <= date.fromisoformat(end[:10])))


def suggested_export_filename(doc) -> dict:
    plans = doc['plans']; fields = plans[0]['fields']
    location = (fields.get('location') or {}).get('city') or 'unknownLoc'
    raw = next((o.get('tested_at_raw') for o in doc['observations'] if o.get('tested_at_raw')), None)
    day = normalize_tested_at(raw)['filename_date_segment']
    if len(plans) > 1:
        base = f'MULTI_{location}_{day}'
    else:
        prices = plans[0]['prices']
        price = next((p for p in prices if p.get('term_role') == 'renewal'), prices[0] if prices else {})
        period = price.get('billing_period_months')
        price_part = 'unknownPrice'
        if price_eligible_for_range_filter(price):
            unit = 'mo' if period == 1 else 'yr' if period == 12 else f'{period}mo'
            price_part = f'{price["amount"]:g}{price["currency"]}-{unit}'
        cpu, mem, disk = (fields.get(k) for k in ('vcpu', 'memory_mb', 'disk_value'))
        cfg = (f'{cpu:g}C{mem / 1024:g}G{disk:g}G'
               if all(v is not None for v in (cpu, mem, disk)) and fields.get('disk_unit') == 'GB'
               else 'unknownCfg')
        base = f'{price_part}_{location}_{cfg}_{day}'
    suffix = doc.get('export', {}).get('collision_suffix')
    if suffix is not None:
        suffix = doc['source']['source_post_id']
        base += '__' + suffix
    return {'suggested_filename': base, 'collision_suffix': suffix}


def derive_stability_tags(observations, sample_policy) -> list:
    # No stability metric is frozen yet: sample count alone cannot establish stability.
    # Deduplication prevents copied observations from becoming independent samples.
    seen = set(); samples = []
    for obs in observations:
        run = obs.get('run_id')
        if sample_policy.get('dedupe_by_run_id', True):
            if run is None or run in seen:
                continue
            seen.add(run)
        samples.append(obs)
    if len(samples) < max(5, sample_policy.get('min_samples_for_stability_tag', 5)):
        return []
    return []


def _schema(path):
    return json.loads((ROOT / 'schemas' / path).read_text(encoding='utf-8'))


def _validate(value, schema, path='$'):
    """Small standard-library validator for the keywords in our frozen schemas."""
    if 'type' in schema:
        types = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        checks = {'object': isinstance(value, dict), 'array': isinstance(value, list),
                  'string': isinstance(value, str), 'integer': type(value) is int,
                  'number': type(value) in (int, float) and math.isfinite(value),
                  'boolean': type(value) is bool, 'null': value is None}
        if not any(checks[t] for t in types):
            raise ValueError(f'{path}: invalid type')
    if 'const' in schema and value != schema['const']:
        raise ValueError(f'{path}: invalid version/value')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}: invalid enum')
    if isinstance(value, str) and 'pattern' in schema and not re.search(schema['pattern'], value):
        raise ValueError(f'{path}: invalid pattern')
    if type(value) in (int, float) and value < schema.get('minimum', -math.inf):
        raise ValueError(f'{path}: below minimum')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - value.keys():
            raise ValueError(f'{path}: missing fields')
        if schema.get('additionalProperties') is False and value.keys() - props.keys():
            raise ValueError(f'{path}: unknown fields')
        for key, item in value.items():
            _validate(item, props.get(key, schema.get('additionalProperties', {}) if isinstance(schema.get('additionalProperties'), dict) else {}), path + '.' + key)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            raise ValueError(f'{path}: too few items')
        for item in value:
            _validate(item, schema.get('items', {}), path + '[]')
    if 'if' in schema:
        try:
            _validate(value, schema['if'], path)
        except ValueError:
            pass
        else:
            _validate(value, schema['then'], path)


def validate_review_document_v2(doc) -> None:
    schema = _schema('review-document/v2/review-document.schema.json')
    # The persisted schema describes v2; the reader explicitly also accepts offline v1.
    if not isinstance(doc, dict) or doc.get('schema_version') not in ('1.0.0-offline', REVIEW_DOCUMENT_SCHEMA_VERSION):
        raise ValueError('invalid review document version')
    _validate({**doc, 'schema_version': REVIEW_DOCUMENT_SCHEMA_VERSION}, schema)


def validate_capture_manifest(doc) -> None:
    _validate(doc, _schema('capture-manifest/v1/capture-manifest.schema.json'))
    stamp = datetime.fromisoformat(doc['captured_at'])
    if stamp.utcoffset() != timedelta(hours=8):
        raise ValueError('captured_at must use Beijing timezone')


def project_review_document_to_public_dto(doc) -> dict:
    from .public_dto import OFFER, PLAN_FIELDS, PRICE
    validate_review_document_v2(doc)
    offers = []
    for index, plan in enumerate(doc['plans']):
        fields = plan['fields']; source = doc['source']
        observations = [o for o in doc['observations'] if o['plan_id'] == plan['plan_id']]
        raw = next((o.get('tested_at_raw') for o in observations if o.get('tested_at_raw')), None)
        n = normalize_tested_at(raw)
        conflicts = [{ 'field': c['field'], 'resolution': c['resolution'],
                      'values': [{k: v.get(k) for k in ('source', 'raw', 'normalized_mb_candidate')} for v in c['values']]}
                     for o in observations for c in o.get('conflicts', [])]
        prices = plan['prices']
        selected = next((p for p in prices if p.get('term_role') == 'renewal'), prices[0] if len(prices) == 1 else {})
        price = {k: selected.get(k) for k in PRICE['properties']}
        price['monthly_equivalent'] = monthly_equivalent(price['amount'], price['billing_period_months'])
        price['price_status'] = ('known' if price_eligible_for_range_filter(price) else 'partial' if selected else 'unknown')
        loc = fields.get('location') or {}; region = loc.get('region_label')
        offer = {k: None for k in OFFER['properties']}
        offer.update({k: fields.get(k) for k in PLAN_FIELDS})
        offer.update(offer_id=doc['sample_id'] + (f'-{index + 1}' if len(doc['plans']) > 1 else ''),
                     post_id=source['source_post_id'], canonical_url=source['url'], vendor_raw=plan.get('provider_name'),
                     plan_label=plan.get('label'), disk_total_value=fields.get('disk_value'),
                     disk_total_unit=fields.get('disk_unit'), port_speed_mbps=fields.get('port_mbps'),
                     location=dict(raw=region, continent=region.split('/')[0] if region else None,
                                   city=loc.get('city'), country=loc.get('country_code')),
                     price=price, observations_summary={'geekbench6_single': None},
                     conflict_flags=[f'{c["field"]}: {c["resolution"]}' for c in conflicts], conflicts=conflicts,
                     summary_text=doc['summary']['text'], limited_claim=doc['summary']['limited_claim'],
                     **{k: n[k] for k in ('review_date', 'review_date_precision', 'review_date_tz', 'tested_at_beijing')})
        if len(doc['plans']) > 1 and plan.get('label'):
            offer['offer_id'] = doc['sample_id'] + '-' + plan['label']
        if any(c['field'] in ('memory', 'memory_mb') and c['resolution'] == 'keep_both' for c in conflicts):
            offer['memory_mb'] = None
        offers.append(offer)
    dto = {'schema_version': PUBLIC_DTO_V2_VERSION, 'offers': offers}
    validate_public_dto_compatible(dto)
    return dto


def validate_public_dto_compatible(doc) -> None:
    from .public_dto import validate_public_dto
    if isinstance(doc, dict) and doc.get('schema_version') == PUBLIC_DTO_V1_VERSION:
        validate_public_dto(doc)
    else:
        _validate(doc, _schema('public-dto/v2/public-dto.schema.json'))
