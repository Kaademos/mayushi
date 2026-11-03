# ADR-0003: Run CI on CircleCI instead of GitHub Actions

- Status: Accepted (supersedes the CI row of ADR-0001)
- Date: 2026-11-02

## Context

The project's GitHub Actions usage hit the account's included-minutes limit, and upgrading the plan is not an option.

## Decision

Run CI on CircleCI with `.circleci/config.yml`. Jobs mirror the original plan: lint, type-check, test and compose build. Lightweight jobs use the `cimg/base` Docker executor; the compose build uses a pinned `ubuntu-2404` machine image so Docker Compose runs natively. No orbs are used, so the config is self-contained and validates offline with `circleci config validate`.

## Consequences

- The GitHub repository must be connected to a CircleCI project for pipelines to run.
- Workflow linting moves from actionlint to `circleci config validate` (`make lint`).
- Free-tier credits still apply; jobs use the smallest resource classes that work.
