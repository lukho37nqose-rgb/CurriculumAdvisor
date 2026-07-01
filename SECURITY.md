# Security policy and deployment controls

## Supported release

The public release on the `main` branch is the supported version. Security changes should be merged only after the GitHub Actions public-release checks pass.

## Reporting a vulnerability

Do not include real student transcripts or personal data in a vulnerability report. Report the affected endpoint, the minimum reproduction steps using synthetic data, expected behaviour, observed behaviour, and impact to the project maintainer through the repository's private security-reporting channel.

## Production checklist

- Deploy from a reviewed commit whose CI checks pass.
- Keep one application instance unless rate limiting is moved to a shared edge/store.
- Leave `ALLOWED_ORIGINS` empty for the bundled same-origin frontend.
- Keep `RATE_LIMIT_ENABLED=true`.
- Use HTTPS and confirm HSTS is present on the public response.
- Configure the platform health check to `/health` and separately monitor `/ready`.
- Restrict production log access and define a retention period.
- Do not enable request-body logging or upload capture in the hosting platform.
- Configure a platform/WAF body cap slightly above 10 MB where supported.
- Set a monthly spend alert and resource ceiling.
- Review dependency-audit failures before deployment.
- Back up catalogue source and build inputs, not student uploads; the service stores none.

## Deliberate boundaries

- The application does not provide authentication because it stores no student account or transcript history.
- The in-memory rate limiter is intended for one process/instance.
- The service accepts only PDF transcript uploads through the public upload endpoint.
- Clinical, professional, discretionary, live offering, capacity, timetable, and concession decisions remain outside deterministic automation.
