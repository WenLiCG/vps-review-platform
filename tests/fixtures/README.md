# Synthetic offline archive fixtures

Every file in this directory is synthetic. The post ID, author, package details,
report links and values are test data, not a real NodeSeek review or VPS result.
No fixture URL is requested by the tests or the archive module.

- `nodeseek_first_post.html` includes an explicit `div#0 article.post-content`,
  sidebar material and a reply so tests can prove that only the first post is kept.
- `nodeseek_no_marker.html` and `nodeseek_duplicate_marker.html` are invalid
  evidence identity fixtures and must be rejected.
- `synthetic-report.txt` tests report preservation without inventing observations.
- The one-pixel PNG is constructed from a documented base64 literal in
  `tests/test_archive.py`; it has not received visual AI interpretation.

The selector and `vps-archive/1` contract were checked read-only against local
`vps-review-download/SKILL.md` and `scripts/download.py` on 2026-10-09.
The module is an independent implementation and does not modify those references.

Reference SHA-256 values:

- `SKILL.md`: `2e2a2b4eca754bad923e08c46cba12867c7bee341a6dde390c3a62931c528c7b`
- `scripts/download.py`: `0c93d2bedc2af45385c0b2c654acb475e1386a4511a597508defe54dc6414eb0`
