# Daily scheduler

This scheduled-only Cloudflare Worker starts the existing GitHub Actions
Python pipeline at 16:20 America/New_York on U.S. trading days, checks again
at 16:25, and verifies the result at 16:30. A final recovery attempt is made
when the deadline is missed; a failed scheduled invocation is logged rather
than reporting success. An already-running job is not dispatched twice.

Cloudflare cron expressions use UTC. The one configured expression fires at
both possible Eastern offsets; the handler accepts only the correct New York
hour and rejects stale invocations. Its holiday policy is checked against the
Python collector across 2020–2035 in the test suite. Half days retain the
16:30 readiness target. Unexpected exchange closures remain visible failures,
matching the existing pipeline.

The Worker creates no HTTP route, database, queue or storage binding. Its six
weekday cron invocations fit Workers Free. Standard Ubuntu Actions runners
remain free because both repositories are public. No paid plan is required;
do not upgrade a Cloudflare subscription for this component. Shared account
quotas and provider availability still apply; this is not a guaranteed deadline.

## Authentication and deployment

Use a dedicated GitHub credential, not an existing personal CLI login token.
It must be able to read contents and dispatch Actions in both
`PeidongGao/Daily_Market_Tracker` and `WillGaoLab/Daily_Market_Tracker`.
Because these are owned by different personal accounts, a dedicated classic
PAT with only `public_repo` scope is one option. Its access covers the public
repositories the issuing account can write; it does not grant private-repository
access. An expiring token requires rotation before expiry. Alternatively use
separate suitably scoped credentials as `SOURCE_GITHUB_TOKEN` and
`MIRROR_GITHUB_TOKEN`. GitHub Apps can also provide these permissions.

Never paste credentials into chat, commit them, put them in configuration, or
reuse the human `gh` OAuth token in the Worker. Enter the dedicated token in
Wrangler's secure prompt:

```sh
cd automation/scheduler
npm ci --ignore-scripts
npm test
npm run test:runtime
npm run check
npx wrangler secret put GITHUB_TOKEN
npm run deploy
```

Only a successful dispatch is not completion: each tick checks an exact
canonical commit, the target CSV row and both figure blobs. Once the source
is complete, the mirror workflow is dispatched with that exact source commit.
Completion requires the mirror's target row and PNG/SVG Git blob hashes to
match the source. Existing different historical rows fail visibly and are
never overwritten; only future new dates automatically converge.

The native source schedule remains a secondary recovery path. The mirror
uses `mirror_market.yml` to copy the canonical outputs with its own built-in
`GITHUB_TOKEN`; no cross-repository publishing credential is needed in Actions.
The old independent mirror collector is manual-only.

## Read-only smoke checks

An existing canonical date can test source dispatch without changing its row:

```sh
gh workflow run daily_market.yml --repo PeidongGao/Daily_Market_Tracker \
  --ref main -f date=2026-11-04
gh workflow run mirror_market.yml --repo WillGaoLab/Daily_Market_Tracker \
  --ref main -f date=2026-11-04 -f verify_only=true
```

Use the latest fully present canonical date for future tests. Do not replay a
conflicting historical date into the mirror without a separately reviewed data
correction. Logs contain outcome/date/commit identifiers, not tokens or response
bodies. Use the Cloudflare dashboard's scheduled invocation status to inspect
deadline failures; this component does not send email or other messages.

## Runtime regression coverage

The scheduler uses `redirect: "manual"` and rejects non-2xx responses, including
redirects, without following them or forwarding credentials. Cloudflare workerd
does not support `redirect: "error"`; Node-only mocks previously missed this
runtime failure. CI now also runs the native workerd fetch path with intercepted
GitHub responses, covering successful dispatch and rejection of redirects.
