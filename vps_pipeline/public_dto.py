"""Whitelist projection and static rendering for the synthetic S1 public site.

Only the JSON Schema subset used by PUBLIC_SCHEMA is implemented here.
"""
import argparse
from copy import deepcopy
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def _nullable(kind):
    return {'type': [kind, 'null']}


LOCATION = _object({key: _nullable('string') for key in
                    ('raw', 'continent', 'city', 'country')})
PRICE = _object({key: _nullable(kind) for key, kind in {
    'amount': 'number', 'currency': 'string', 'billing_period_months': 'integer',
    'term_role': 'string', 'monthly_equivalent': 'number', 'price_status': 'string',
}.items()})
PLAN_FIELDS = {
    'plan_label': 'string', 'vcpu': 'integer', 'memory_mb': 'number',
    'disk_total_value': 'number', 'disk_total_unit': 'string', 'disk_type': 'string',
    'traffic_value': 'number', 'traffic_unit': 'string', 'port_speed_mbps': 'number',
}
RECORD_FIELDS = ('post_id', 'canonical_url', 'vendor_raw', 'published_date',
                 'published_tz', 'review_date', 'review_date_precision', 'tested_at_beijing')
OFFER = _object({
    'offer_id': {'type': 'string'},
    **{key: _nullable('string') for key in RECORD_FIELDS},
    'aff_url': {'type': 'null'},
    **{key: _nullable(kind) for key, kind in PLAN_FIELDS.items()},
    'location': LOCATION, 'price': PRICE,
    'observations_summary': _object({'geekbench6_single': _nullable('number')}),
    'conflict_flags': {'type': ['array', 'null'], 'items': {'type': 'string'}},
    'summary_text': _nullable('string'), 'limited_claim': _nullable('boolean'),
})
PUBLIC_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'public-dto/v1',
    **_object({'schema_version': {'type': 'string', 'const': 'public-dto/v1'},
               'offers': {'type': 'array', 'minItems': 1, 'items': OFFER}}),
}


def _validate(value, schema, path):
    kinds = schema['type']
    kinds = kinds if isinstance(kinds, list) else [kinds]
    matches = {
        'null': value is None, 'object': isinstance(value, dict),
        'array': isinstance(value, list), 'string': isinstance(value, str),
        'boolean': type(value) is bool, 'integer': type(value) is int,
        'number': type(value) in (int, float) and (
            not isinstance(value, float) or math.isfinite(value)),
    }
    if not any(matches[kind] for kind in kinds):
        raise ValueError(f'{path}: expected {kinds}')
    if 'const' in schema and value != schema['const']:
        raise ValueError(f'{path}: expected {schema["const"]!r}')
    if isinstance(value, dict):
        properties = schema['properties']
        if set(value) - properties.keys():
            raise ValueError(f'{path}: unknown properties')
        missing = set(schema['required']) - value.keys()
        if missing:
            raise ValueError(f'{path}: missing {sorted(missing)}')
        for key, item in value.items():
            _validate(item, properties[key], f'{path}.{key}')
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            raise ValueError(f'{path}: too few items')
        for index, item in enumerate(value):
            _validate(item, schema['items'], f'{path}[{index}]')


def validate_public_dto(obj: dict) -> None:
    """Reject unknown keys, missing fields and invalid JSON value types."""
    _validate(obj, PUBLIC_SCHEMA, '$')


def project_to_public_dto(internal_record: dict) -> dict:
    """Copy only explicitly approved fields; never infer missing facts."""
    offers = []
    for plan in internal_record.get('plans', []):
        plan_id = plan.get('plan_id')
        price = next((p for p in internal_record.get('prices', [])
                      if plan_id is not None and p.get('plan_id') == plan_id), {})
        score = next((o.get('value') for o in internal_record.get('observations', [])
                      if plan_id is not None and o.get('plan_id') == plan_id
                      and o.get('metric') == 'geekbench6_single'), None)
        summary = internal_record.get('summary') or {}
        location = plan.get('location') or {}
        offer = {
            'offer_id': internal_record.get('sample_id'),
            **{key: internal_record.get(key) for key in RECORD_FIELDS},
            'aff_url': None,
            **{key: plan.get(key) for key in PLAN_FIELDS},
            'location': {key: location.get(key) for key in LOCATION['properties']},
            'price': {key: price.get(key) for key in PRICE['properties']},
            'observations_summary': {'geekbench6_single': score},
            'conflict_flags': internal_record.get('conflict_flags'),
            'summary_text': summary.get('text'),
            'limited_claim': summary.get('limited_claim'),
        }
        offers.append(deepcopy(offer))
    dto = {'schema_version': 'public-dto/v1', 'offers': offers}
    validate_public_dto(dto)
    return dto


def _text(value):
    if value is None:
        return '无'
    if isinstance(value, bool):
        return '是' if value else '否'
    return escape(str(value), quote=True)


def _page(title, body, css='style.css'):
    return (f'<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{_text(title)}</title><link rel="stylesheet" href="{css}">'
            '</head><body><header class="topbar"><div class="brand">VPS 测评索引'
            '</div><span>合成样例 · 历史快照</span></header><main class="shell">'
            f'{body}<footer>人工构造，非真实帖子 · 未知值不作推断</footer>'
            '</main></body></html>\n')


def _rows(values):
    return '<dl>' + ''.join(f'<dt>{_text(label)}</dt><dd>{_text(value)}</dd>'
                           for label, value in values) + '</dl>'


def _source_link(url):
    if url is None:
        return '无'
    # Escaping alone does not make executable URL schemes safe.
    if urlsplit(url).scheme not in ('https', 'http'):
        return _text(url)
    return f'<a href="{_text(url)}" rel="noreferrer">{_text(url)}</a>'


def build_public_site(internal_record: dict, out_dir: str | Path) -> None:
    """Build a fresh output directory from validated public data only."""
    dto = project_to_public_dto(internal_record)
    out = Path(out_dir).resolve()
    protected = (ROOT / 'website/dist').resolve()
    if out == protected or protected in out.parents or out in protected.parents:
        raise ValueError('output must not overwrite website/dist')
    # S1 supports one offer; restrict filenames independently of HTML escaping.
    offers = dto['offers']
    if len(offers) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+', offers[0]['offer_id']):
        raise ValueError('S1 requires one offer with a safe filename identifier')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'offers').mkdir()
    cards = []
    for offer in offers:
        t = lambda key: _text(offer[key])
        name = f'{offer["offer_id"]} · {offer["vendor_raw"]} · {offer["plan_label"]}'
        cards.append(
            f'<article class="result-card"><h2><a href="offers/{t("offer_id")}.html">'
            f'{_text(name)}</a></h2><p>{t("vcpu")} vCPU · {t("memory_mb")} MB · '
            f'{t("disk_total_value")} {t("disk_total_unit")} {t("disk_type")}</p>'
            f'<p>{_text(offer["price"]["amount"])} {_text(offer["price"]["currency"])}</p>'
            f'<p>{t("summary_text")}</p></article>')
        labels = {
            'offer_id': '样例标识', 'post_id': '帖子编号', 'vendor_raw': '商家',
            'plan_label': '套餐', 'vcpu': 'vCPU', 'memory_mb': '内存 MB',
            'disk_total_value': '磁盘容量', 'disk_total_unit': '磁盘单位',
            'disk_type': '磁盘类型', 'traffic_value': '流量', 'traffic_unit': '流量单位',
            'port_speed_mbps': '端口 Mbps', 'published_date': '发布日期',
            'published_tz': '发布时区', 'review_date': '测评日期',
            'review_date_precision': '日期精度', 'tested_at_beijing': '测试时间（北京）',
            'limited_claim': '有限结论', 'aff_url': '推广链接',
        }
        body = '<a href="../index.html">返回列表</a>'
        body += f'<article class="result-card detail-content"><h1>{_text(name)}</h1>'
        body += _rows((label, offer[key]) for key, label in labels.items())
        body += '<h2>地点</h2>' + _rows(offer['location'].items())
        body += '<h2>价格快照</h2>' + _rows(offer['price'].items())
        body += '<h2>观测摘要</h2>' + _rows(offer['observations_summary'].items())
        body += '<h2>冲突标记</h2>' + _text(', '.join(offer['conflict_flags'] or []) or None)
        body += f'<h2>简评</h2><p>{t("summary_text")}</p><h2>原帖</h2>'
        body += _source_link(offer['canonical_url']) + '</article>'
        (out / 'offers' / f'{offer["offer_id"]}.html').write_text(
            _page(name, body, '../style.css'), encoding='utf-8')
    body = ('<div class="page-heading"><h1>套餐筛选</h1></div>'
            '<section class="searchbar"><label class="search">搜索套餐'
            '<input type="search" placeholder="商家、套餐或编号" aria-label="搜索套餐">'
            '</label></section><p>筛选界面预览 · 当前展示全部合成样例</p>'
            '<section class="results" aria-label="套餐列表">' + ''.join(cards) + '</section>')
    (out / 'index.html').write_text(_page('套餐筛选 · 合成样例', body), encoding='utf-8')
    (out / 'data.json').write_text(json.dumps(dto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    shutil.copyfile(ROOT / 'website/dist/style.css', out / 'style.css')


def main():
    parser = argparse.ArgumentParser(description='构建 public-dto/v1 静态样例站')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--input', required=True, type=Path)
    build.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    build_public_site(json.loads(args.input.read_text(encoding='utf-8')), args.out)


if __name__ == '__main__':
    main()
