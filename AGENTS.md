# Working on Cultivatinator

- Read README.md and docs/ before editing. Preserve existing functionality and LICENSE.
- Follow the FastAPI / SQLAlchemy / Alembic backend and React / TypeScript frontend architecture.
- Keep changes incremental; avoid unnecessary rewrites, dependencies, infrastructure, or unapproved features.
- Preserve the Industrial Monitoring Console visual language, reusable components, accessibility, and responsive layouts.
- Use Alembic migrations for schema changes. Never use create_all as a migration substitute.
- Add meaningful tests for changed behavior. Keep documentation synchronized.
- Run backend tests, frontend tests, and the production build. Report failures and unrun checks honestly; never fabricate results.
- Do not automatically deploy to production or merge into main.
- Each cloud task is already isolated: use the existing checkout; do not create worktrees unless requested.
