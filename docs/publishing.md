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
   - Environment: `pypi`
3. In GitHub, create an Environment named `pypi` (optional protection rules).

## Release steps

1. Bump `version` in `pyproject.toml` and `src/tool_semantics/__init__.py`.
2. Update `CHANGELOG.md`.
3. Tag and publish a GitHub Release (`vX.Y.Z`).
4. The `Publish to PyPI` workflow builds sdist/wheel and uploads via OIDC.

## Local dry-run

```bash
python -m pip install build
python -m build
# inspect dist/ — do not upload from developer machines by default
```
