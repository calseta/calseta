# Contributing to Calseta

Thanks for your interest in contributing. Calseta is currently in pre-MVP development — the codebase is being actively built and the project is not yet ready for external contributions.

**This will change.** Once the initial MVP is shipped, contributions will be open and actively welcomed. The areas we expect to need the most community involvement are alert source integrations, enrichment providers, and example agents.

---

## What You Can Do Right Now

**Open an issue** if you have feedback on the API design, the data model, or the architecture. This is the most valuable contribution at this stage — decisions are still being made and outside perspective is useful.

**Star or watch the repo** to get notified when the project reaches a state where contributions are welcome.

**Read the design docs** — `PLATFORM_DESIGN.md` covers the architecture and key decisions. If you're planning to contribute later, this is the right place to start.

---

## When Contributions Open

Once MVP ships, we'll update this file with full contribution guidelines. The general shape of what we'll be looking for:

- **Alert source integrations** — new `AlertSourceBase` implementations for additional SIEMs and security tools
- **Enrichment providers** — new `EnrichmentProviderBase` implementations for additional threat intel and identity providers
- **Example agents** — additions to the `/examples` directory showing how to build on top of Calseta
- **Bug fixes and API improvements** — issues labeled `good first issue` will be the right entry point

All contributions will require: passing CI (ruff, mypy, pytest), documentation for any new extension point, and alignment with the design philosophy in `PLATFORM_DESIGN.md`.

---

## Questions

Open a GitHub Discussion if you have questions about the project direction, use cases, or how you're planning to use Calseta. We (humans + AI agents) read everything.