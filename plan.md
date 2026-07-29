# Apple-inspired LLM Report Card site

## Summary

Build a static React + TypeScript GitHub Pages site that turns `LLM_REPORT_CARD.md` into a public, searchable model gallery. The Markdown file remains the single source of truth; every deployment regenerates the displayed data from it.

## Key changes

- Create a Vite React app with a build-time Markdown parser that extracts provider, model, aspect, Pros, and Cons into typed site data; fail the build with a useful error if the report-card structure is invalid.
- Make the landing page a responsive model gallery with provider and aspect filters plus client-side search. Selecting a model opens an accessible detail view containing its complete Pros/Cons table and a shareable URL fragment.
- Apply the Apple-design approach: system typography, deliberate hierarchy, subtle translucent navigation, immediate press feedback, restrained transform/opacity transitions, light/dark appearance, and reduced-motion/reduced-transparency fallbacks. Avoid decorative or auto-playing motion.
- Add clear public-facing context: this is a personal, continuously updated record of observed model behavior—not benchmark data or universal advice.
- Configure Vite for the `/llm-skills/` project-site base path and add a GitHub Actions workflow that builds, validates, and deploys the static artifact to GitHub Pages on `main` and on manual dispatch. Set the repository’s Pages source to GitHub Actions.

## Public interfaces

- `LLM_REPORT_CARD.md` stays the authoring interface and retains its provider → model → aspect table convention.
- The generated in-browser data model exposes provider, model, aspect, pros, and cons; no backend, accounts, editing, analytics, or external API calls.

## Test plan

- Unit-test parsing against the current report card and malformed heading/table fixtures.
- Test filtering, search, selected-model deep links, empty results, keyboard navigation, and reduced-motion behavior.
- Run production build and verify the deployed site works at the GitHub Pages project path on desktop and narrow mobile layouts.

## Assumptions

- Defaults adopted for the unanswered choices: comparison-first purpose, static React implementation, and model-gallery landing view.
- The launch audience is public, with filter/search enabled; side-by-side comparison is deferred.
- The site will be deployed from the existing `main` branch without a custom domain.
