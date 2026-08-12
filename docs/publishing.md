# Publishing

Tool-Semantics is published to PyPI from GitHub Releases using
[trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC).
No long-lived PyPI API token is stored in the repository.

## One-time PyPI setup

1. Create a PyPI project named `tool-semantics` (or claim the name on first publish).
2. Under **Publishing**, add a trusted publisher:
   - Owner: `askmy-stack`
   - Repository: `tool-semantics`
   - Workflow: `publish.yml`
   - Environment: leave blank

The workflow intentionally has no GitHub Environment. If an environment is added
later, add the same environment name to PyPI's trusted-publisher configuration
first; otherwise PyPI will reject the environment-scoped OIDC identity.

## Release steps

1. Bump `version` in `pyproject.toml` and `src/tool_semantics/__init__.py`.
2. Update `CHANGELOG.md` (move Unreleased notes into a dated `X.Y.Z` section).
3. Update Action pin examples in `docs/github-action.md` to `@vX.Y.Z`.
4. Tag and publish a GitHub Release (`vX.Y.Z`).
5. The `Publish to PyPI` workflow builds sdist/wheel and uploads via OIDC.
6. Verify `pip install tool-semantics==X.Y.Z` in a clean venv.

## Local dry-run

```bash
python -m pip install build
python -m build
# inspect dist/ — do not upload from developer machines by default
```
