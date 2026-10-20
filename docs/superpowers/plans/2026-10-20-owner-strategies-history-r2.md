# Owner Strategies historical compatibility projection

`GET /api/owner/v1/strategies?view=all` failed when preserved retired Events
predating Product Compatibility had no mapping. The current-version query
remained valid. This is a display-query consistency defect, not permission to
install historical Events or fabricate product authority.

The read projection now retains those Events with `product_family=null` and
`product_compatibility_unavailable_reason=historical_product_compatibility_not_recorded`.
This exception applies only when both Event and StrategyVersion are retired,
the version is not the group's current pointer, and neither enabled Owner
scope nor active/warming Universe exists for that Event (including empty
Universes). The DTO forbids unknown compatibility with live authority fields.
All other missing mappings still raise the normal facts contradiction/409.
No migrations, production data repair, strategy changes or Kernel rollout.

Verification includes a red real-PostgreSQL historical read, current-pointer
and nonretired-Event failures, explicit-gap DTO negative cases, the existing
Owner read repository regression, and exact official Owner API R2 certification.
Generated client types reflect the nullable historical metadata. The release
is based on the deployed API session-timeout commit, preserving auth behavior.

Deployment uses only the official Owner API release path. It restarts the
Owner API, so existing process-local Web sessions may require login again;
Kernel Workers and trading protection remain resident. Compare their identity,
PIDs/restarts, controls and research settings before/after. Validate both
current/all projections against fresh read-only production facts after release.
