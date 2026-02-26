# Known Operational Issues

**Rule for Claude**: Before debugging any deployment/infra error, GREP this file first:
```bash
grep -i "SYMPTOM_KEYWORD" docs/ops/known-issues.md
```

---

## Railway CLI `railway up` Fails on Initialization

**Date discovered**: 2026-02-26
**Symptom**: `railway up` fails with "Deployment failed" on Initialization step. Build/Deploy/Post-deploy show "Not started".
**Error in logs**: `Could not find root directory: /service`

**Root cause**: Railway dashboard configured with Root Directory = `/service`. CLI must be run from project root, not from `/service` folder.

**Solution A** (preferred): Deploy via git push:
```bash
cd /Users/evgenyq/Projects/atlantisplus
git add -A && git commit -m "message" && git push origin main
```

**Solution B**: Run CLI from project ROOT (not from /service):
```bash
cd /Users/evgenyq/Projects/atlantisplus  # NOT /service!
railway up
```

**DO NOT**: Run `railway up` from `/service` folder — it will fail.

---

## JWT Verification Fails: "alg value is not allowed"

**Date discovered**: 2026-02-26
**Symptom**: All authenticated API calls return 401. Logs show `JWT verification failed: The specified alg value is not allowed`

**Root cause**: (investigating)

**Solution**: (to be determined)

---

## Template for New Issues

```markdown
## [Short Title]

**Date discovered**: YYYY-MM-DD
**Symptom**: What you see (error message, behavior)
**Root cause**: Why it happens
**Solution**: How to fix
**DO NOT**: Common wrong approaches that waste time
```
