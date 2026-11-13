"""PHASE 1: contract constants and intentionally unimplemented interfaces."""
CONTRACT_V2_VERSION = 'contract/v2'
REVIEW_DOCUMENT_SCHEMA_VERSION = 'review-document/v2'
PUBLIC_DTO_V1_VERSION = 'public-dto/v1'
PUBLIC_DTO_V2_VERSION = 'public-dto/v2'
CAPTURE_MANIFEST_SCHEMA_VERSION = 'capture-manifest/v1'
PRICE_SEMANTICS_VERSION = 'price-semantics/v2'


def normalize_tested_at(tested_at_raw: str | None) -> dict:
    raise NotImplementedError


def suggested_export_filename(doc) -> dict:
    raise NotImplementedError


def derive_stability_tags(observations, sample_policy) -> list:
    raise NotImplementedError


def monthly_equivalent(amount, billing_period_months):
    raise NotImplementedError


def price_eligible_for_range_filter(price) -> bool:
    raise NotImplementedError


def matches_review_date_filter(review_date, start, end) -> bool:
    raise NotImplementedError


def validate_review_document_v2(doc) -> None:
    raise NotImplementedError


def validate_capture_manifest(doc) -> None:
    raise NotImplementedError


def project_review_document_to_public_dto(doc) -> dict:
    raise NotImplementedError


def validate_public_dto_compatible(doc) -> None:
    raise NotImplementedError
