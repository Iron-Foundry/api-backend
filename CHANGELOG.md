# Changelog

All notable changes to api-backend are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`pyproject.toml` holds the version; `app/version.py` reads it, and both
`GET /version` and the OpenAPI `info` block report it. Never hardcode it
anywhere else. Bump with `uv version --bump patch|minor` (or `alpha|beta|rc` for a
prerelease, `stable` to drop the tag). A MAJOR bump is the maintainer's call
and is never made automatically.

## [1.0.0] - 2026-07-28

First versioned release. The service has been in production; this establishes
1.0.0 as the baseline rather than describing everything built before it.

### Added

- `GET /version`, reporting the package version plus the commit and build
  timestamp baked into the container image as build arguments.
- `GET /health` moved under the new `meta` tag; the path is unchanged.
- OpenAPI `info.description`, per-tag sidebar descriptions, `x-tagGroups`
  sections, and declared production and local servers.
- Declared security schemes: `DiscordJWT` (bearer), `MemberApiKey` and
  `MetricsApiKey` (both the `verification-code` header). The API reference can
  now authenticate and issue live requests.
- Reusable error responses in `app/docs/responses.py`, attached per router, so
  401, 403, 404, 502 and 503 appear in the reference instead of only 200.
- A docstring on every one of the 279 documented operations.
- Branding on the Scalar reference page: clan palette, favicon, dark default,
  and persisted auth between reloads.

### Changed

- Missing credentials now return `401` instead of FastAPI's `422`. Previously
  the credential was an ordinary required header, so its absence was reported
  as a validation error. Invalid and revoked credentials returned `401` before
  and still do.
- `/reference` operations no longer carry a duplicated `reference` tag.
