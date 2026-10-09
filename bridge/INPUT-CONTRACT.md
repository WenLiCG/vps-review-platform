# Incremental review import

This adapter is a separate website bridge. It does not replace or modify either installed skill.

Input index must contain batchId, batchDate, sourceCommit, and entries. Each entry must be explicitly selected from the verified review-category page, new relative to the baseline, and have:

- postId and canonical sourceUrl
- reviewComplete: true, confirmed objectCount
- manifestPath to the actual captured archive
- publicLabel without author, giveaway language, or IP fragments
- objects: [{itemId, entryKind, publicLabel, product (optional), analysisPath}]
- entryKind from measured_vps, advertised_plan, review_configuration_version or measured_host
- For multiple objects: objectMappingConfirmed: true and distinct, individually reviewed analysis files. Reusing one analysis for multiple machines is rejected.

Information-only posts are held for a separate post-level path; no VPS is manufactured to accommodate a post.

The builder validates real file hashes and finalized analyses, stages output outside the Site, retains the previous posts/objects/reviews unchanged, and writes public provenance hashes. It never fetches, pushes, publishes or uploads raw materials. A second run with an already-imported post is rejected, preventing duplicate insertion.
