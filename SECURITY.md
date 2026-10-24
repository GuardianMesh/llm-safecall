# Security policy

Use [GitHub's private vulnerability reporting form](https://github.com/GuardianMesh/llm-safecall/security/advisories/new)
for suspected vulnerabilities. If private reporting is unavailable, open an
issue asking a maintainer for a private contact, without exploit details or
sensitive data. There is no guaranteed response time.

Include the package version, a minimal reproduction, and the expected impact.
Report provider or SDK vulnerabilities to their maintainers unless the issue is
specific to this wrapper.

The package checks known patterns and validates schemas. It does not provide
process isolation, tool authorization, or complete prompt-injection prevention.
Applications remain responsible for handling model output and protecting the
credentials, files, and network access available to their tools.
