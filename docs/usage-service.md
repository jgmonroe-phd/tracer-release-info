# Launch and installation counts

GitHub Pages serves static files; requesting `version.json` cannot atomically increment a repository counter. This change includes a separate Python standard-library HTTP/SQLite service. It is **not deployed by this pull request**. `usage_endpoint` remains `null`, so no count collection is falsely advertised. Deploy it on operator-controlled infrastructure, then enable its HTTPS URL through a policy change.

## What is counted

The service counts accepted application launch events and distinct random installation IDs within a rolling retention window, **90 days by default**. Counts are self-reported estimates, not audited licensing or unique people. One person on two computers or two OS profiles can create multiple IDs; a shared profile can combine multiple people; deleting configuration creates another ID. Accurate distinct-user counts require authenticated user accounts or SSO, which this service does not add.

A persistent random UUID4 identifies an installation/profile. A new random UUID4 identifies each application launch. Reuse the same launch ID for a retry. A batch of reports within one launch remains one launch. A counter outage loses that best-effort event unless the client retries it; it must not prevent a permitted review. These counts are not completed reports, successful reviews, or GenAI requests.

No document contents, paths, filenames, credentials, email, username, hostname, hardware identifiers, client timestamps, or IP addresses belong in the event. The service rejects extra fields and does not log requests. Persistent random IDs are pseudonymous, not a guarantee of anonymity. Tell users about collection in the application privacy notice. Reverse proxies necessarily observe network addresses; configure short operational retention or disable access logs as appropriate, never log bodies or Authorization headers, and disclose any retained proxy data.

## API contract

`POST /v1/launches`, `Content-Type: application/json`, maximum 1024 bytes:

```json
{
  "schema_version": 1,
  "event": "launch",
  "launch_id": "00e73e20-89c6-45ee-8406-4b917264baab",
  "installation_id": "05d602db-182b-4a78-b9f4-4d134cad8756",
  "version": "0.9.11"
}
```

IDs must be lowercase canonical UUID4 values. Versions are numeric `major.minor.patch`, at most 32 characters. The first event returns `202 {"accepted":true,"duplicate":false}`. An identical retry returns `200` with `duplicate:true`; reusing the launch ID with different data returns `409`. Invalid data returns `400`, oversized bodies `413`, and wrong content type `415`. Bodies and identifiers are not echoed in errors. The server assigns the receipt timestamp.

`GET /v1/summary` requires `Authorization: Bearer <TRACER_USAGE_ADMIN_TOKEN>`. It returns only aggregate `launches`, `distinct_installations`, counts by version, `window_start`, `generated_at`, and `retention_days`. Distinct installations across versions overlap: do not sum those per-version counts. There is no raw-event read API. The token stays on the server/admin workstation, never in Git, the client, or `version.json`.

The ingestion endpoint is public and has no embedded client secret. A secret distributed in an executable would not authenticate a real installation. Attackers can fabricate IDs and inflate counts, so require proxy rate limits, quotas, monitoring, and authenticated ingestion if accurate enforcement becomes necessary. Do not treat these estimates as billing or license evidence.

## Deployment

Use Python 3.10 or newer on a patched host. The bundled service binds only to `127.0.0.1`; **do not expose the standard-library HTTP server directly to the internet**. Put a supported HTTPS reverse proxy in front of it with a valid certificate, request and connection rate limits, a 1 KiB body limit, request buffering, short header/body timeouts, an absolute request deadline, and a maximum number of concurrent connections. Run as a dedicated unprivileged service account with a private, persistent data directory. Keep the database and all backups outside the repository and static web root. Do not run multiple host replicas against one SQLite file on a network filesystem.

1. Copy the repository to the managed host and run the tests.
2. Create a private data directory with mode `0700`, owned by the service account. Create a random admin token of at least 32 bytes using a secret manager or `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Supply it through the service environment as `TRACER_USAGE_ADMIN_TOKEN`; do not commit it or paste it into issue/PR text.
3. Launch under your service manager with restart and resource limits:

   ```bash
   python3 service/usage_server.py \
     --database /var/lib/tracer-usage/usage.sqlite3 \
     --port 8765 --retention-days 90
   ```

4. Configure the HTTPS proxy to forward only `/v1/launches` to `http://127.0.0.1:8765/v1/launches`. Protect `/v1/summary` through a private administrative path or private network in addition to the bearer token. Deny other paths and methods. Disable caching, redirects, and request/body/header logging. Example starting limits: 30 launch requests per minute per source address, burst 10, plus a global connection/throughput limit sized for the host. Adjust deliberately for shared institutional NATs; enforce limits before forwarding to Python. The server itself caps connections at 32, permits at most 5 seconds of socket inactivity, and closes each connection after an absolute 10-second deadline even if bytes keep arriving. Shutdown waits for active workers and cancels/joins their deadline timers before reporting completion; slow request trickles cannot hold a worker indefinitely.
5. Restrict filesystem permissions and encrypt the volume/backups under your normal host policy. Set a disk quota and alerts: a public counter can be flooded even with valid event syntax. Keep production tokens separate from test tokens.
6. Schedule the following daily with the same service identity and secret environment so old events are pruned even if no requests arrive:

   ```bash
   python3 service/usage_server.py \
     --database /var/lib/tracer-usage/usage.sqlite3 \
     --retention-days 90 --prune
   ```

7. Test a first launch, identical replay, conflicting replay, an unauthenticated summary refusal, and an authenticated aggregate response over the actual HTTPS path. Confirm access logs do not retain event bodies/IDs/tokens, monitor health privately, and rehearse database backup/restore. Tests in this repository verify local behavior; they do not certify an undeployed proxy or host.
8. Only then set `usage_endpoint` to `"https://YOUR-OPERATED-HOST/v1/launches"`, validate and merge, and verify the published manifest. `YOUR-OPERATED-HOST` is documentation, not a configured service. Do not point GitHub Pages at this Python file; Pages cannot run it.

SQLite serializes writes and enforces unique launch IDs transactionally, including concurrent retries. Events outside the window are logically deleted; replay protection expires with them, so replaying a very old event can count again. Clients should send a launch once promptly, with at most a short bounded retry, not replay old queues. Summaries cover retained records, not lifetime totals. Use a consistent retention configuration for the server and prune job.

Retention applies to primary database records; configure backup expiration, WAL/checkpoint maintenance, disk encryption, and host deletion procedures too. Deletion is not a promise of forensic erasure from storage snapshots. Back up using SQLite's online backup facility rather than copying an active database without its transaction state. Changing retention can irreversibly remove historical counts; document changes.

To disable collection, set `usage_endpoint` back to null and redeploy policy. Keep mandatory version/internet and GenAI checks active.

## Export aggregates for a repository report

On an administrator workstation with `TRACER_USAGE_ADMIN_TOKEN` supplied securely, export a new file:

```bash
python3 scripts/export_usage_summary.py \
  https://YOUR-OPERATED-HOST/v1/summary \
  --output usage-summary-2026-09-29.json
```

The exporter accepts only the documented aggregate fields, rejects redirects and identifier fields, and refuses to overwrite an existing file. Review the result before committing it to a statistics branch or sharing it. A separately authorized scheduled job could publish reviewed aggregate snapshots later; this change does not install one, expose live admin data, or commit raw events. Do not store the admin token in a workflow file; use the host/CI secret store if that automation is later enabled.
