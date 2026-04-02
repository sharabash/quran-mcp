# Deploy to Production

Deploy the current master to Hetzner production via GitHub release + Actions workflow.

## Steps

1. **Bump version** — grep for `version=` across `server.py`, `pyproject.toml`, and all tool/resource files under `src/quran_mcp/mcp/`. Update them all to the new version.

2. **Commit the version bump**:
   ```
   git add -u && git commit -m "chore: Bump version to vX.Y.Z"
   ```

3. **Tag and push**:
   ```
   git tag vX.Y.Z && git push origin master --tags
   ```

4. **Create GitHub release**:
   ```
   gh release create vX.Y.Z \
     --repo quran/quran-mcp \
     --title "vX.Y.Z — <brief description>" \
     --notes "<release notes>"
   ```
   The deploy workflow fires automatically on release publish.
   Note: Database dumps are not attached to releases while data distribution is being finalized.

5. **Verify deployment**:
   ```
   gh run list --repo quran/quran-mcp --limit 1
   ```
   Wait for the run to complete, then:
   ```
   ssh hetzner "curl -sf http://localhost:8088/.health | python3 -m json.tool"
   ```

## Notes

- The deploy workflow (`deploy.yml`) triggers on `release: published` or manual `workflow_dispatch`
- If you need to deploy without a release, use: Actions → Deploy to Hetzner → Run workflow → enter a ref
- Production data is managed separately and is not part of the release artifacts.
