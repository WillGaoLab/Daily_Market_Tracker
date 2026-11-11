import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { isMarketDay, newYorkTime, tick } from "./scheduler.mjs";

const env = { SOURCE_REPO: "owner/source", MIRROR_REPO: "owner/mirror", BRANCH: "main", GITHUB_TOKEN: "test-only-secret" };
const winter = Date.parse("2026-11-05T21:20:00Z");
const sourceCommit = "a".repeat(40), mirrorCommit = "b".repeat(40);
const historyBlob = "c".repeat(40), png = "d".repeat(40), svg = "e".repeat(40);

function mock({ source = false, mirror = false, active = false, mismatch = false, badStatus = 0, sourceSvg = true } = {}) {
  const posts = [], gets = [];
  const fetcher = async (url, options) => {
    assert.equal(options.headers.Authorization, "Bearer test-only-secret");
    assert.equal(options.redirect, "manual");
    if (badStatus) return new Response("redacted", { status: badStatus });
    if (options.method === "POST") {
      posts.push({ url, body: JSON.parse(options.body) });
      return new Response(JSON.stringify({ workflow_run_id: 123 }), { status: 200 });
    }
    gets.push(url);
    if (url.includes("git/ref/heads")) return Response.json({ object: { sha: url.includes("owner/source") ? sourceCommit : mirrorCommit } });
    if (url.includes("git/trees")) {
      const present = url.includes("owner/source") ? source : mirror;
      return Response.json({ truncated: false, tree: [
        { path: "data/history.csv", type: "blob", sha: historyBlob },
        ...(present ? [{ path: "figures/2026-11-05.png", type: "blob", sha: png }] : []),
        ...(present && (sourceSvg || url.includes("owner/mirror")) ? [{ path: "figures/2026-11-05.svg", type: "blob", sha: svg }] : []),
      ] });
    }
    if (url.includes("git/blobs")) {
      const present = url.includes("owner/source") ? source : mirror;
      return Response.json({ encoding: "base64", content: Buffer.from("date,source\n" + (present ? `2026-11-05,${mismatch && url.includes("owner/mirror") ? "different" : "Yahoo Finance"}\n` : "")).toString("base64") });
    }
    if (url.includes("/runs?")) return Response.json({ workflow_runs: active ? [{ status: "in_progress" }] : [] });
    throw new Error(`Unexpected URL ${url}`);
  };
  return { fetcher, posts, gets };
}

test("Eastern schedule survives DST; wrong hour, stale date and weekends cannot dispatch", async () => {
  assert.deepEqual(newYorkTime(Date.parse("2026-07-17T20:20:00Z")), { date: "2026-07-17", hour: 16, minute: 20 });
  assert.deepEqual(newYorkTime(winter), { date: "2026-11-05", hour: 16, minute: 20 });
  for (const timestamp of [Date.parse("2026-11-05T20:20:00Z"), Date.parse("2026-11-07T21:20:00Z")]) {
    const m = mock(); assert.equal((await tick(env, timestamp, m.fetcher, timestamp)).status, "skipped"); assert.equal(m.gets.length, 0);
  }
  const m = mock(); assert.equal((await tick(env, winter, m.fetcher, winter + 86400000)).status, "skipped");
});

test("holiday policy matches the Python pipeline across 2020–2035", () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const code = "import json,sys;sys.path.insert(0,'scripts');from fetch_data import is_us_market_holiday;from datetime import date,timedelta;d=date(2020,1,1);out=[]\nwhile d<date(2036,1,1):\n if d.weekday()>=5 or is_us_market_holiday(d):out.append(d.isoformat())\n d+=timedelta(days=1)\nprint(json.dumps(out))";
  const closed = new Set(JSON.parse(execFileSync("python3", ["-c", code], { cwd: root, encoding: "utf8" })));
  for (let d = Date.parse("2020-01-01T00:00:00Z"); d < Date.parse("2036-01-01T00:00:00Z"); d += 86400000) {
    const date = new Date(d).toISOString().slice(0, 10);
    assert.equal(isMarketDay(date), !closed.has(date), date);
  }
});

test("missing source dispatches existing workflow with explicit date; 200 response supported", async () => {
  const m = mock();
  assert.equal((await tick(env, winter, m.fetcher, winter)).status, "source_dispatched");
  assert.deepEqual(m.posts[0].body, { ref: "main", inputs: { date: "2026-11-05" } });
  assert.match(m.posts[0].url, /owner\/source\/actions\/workflows\/daily_market.yml\/dispatches$/);
});

test("a running workflow prevents duplicate dispatch; absent SVG is incomplete", async () => {
  const m = mock({ active: true, source: true, sourceSvg: false });
  assert.equal((await tick(env, winter, m.fetcher, winter)).status, "source_running");
  assert.equal(m.posts.length, 0);
});

test("complete source dispatches mirror pinned to its exact source commit", async () => {
  const m = mock({ source: true });
  assert.equal((await tick(env, winter, m.fetcher, winter)).status, "mirror_dispatched");
  assert.deepEqual(m.posts[0].body, { ref: "main", inputs: { date: "2026-11-05", source_ref: sourceCommit } });
  assert.match(m.posts[0].url, /mirror_market.yml\/dispatches$/);
});

test("success requires both target row and exact matching PNG/SVG blobs", async () => {
  const m = mock({ source: true, mirror: true });
  assert.equal((await tick(env, winter, m.fetcher, winter)).status, "complete");
  assert.equal(m.posts.length, 0);
});

test("divergent historical row is an explicit failure rather than an overwrite", async () => {
  const m = mock({ source: true, mirror: true, mismatch: true });
  await assert.rejects(tick(env, winter, m.fetcher, winter), /Mirror conflict/);
  assert.equal(m.posts.length, 0);
});

test("deadline failures and GitHub outages cannot masquerade as completion", async () => {
  const deadline = winter + 10 * 60000, m = mock();
  await assert.rejects(tick(env, deadline, m.fetcher, deadline), /Deadline missed/);
  assert.equal(m.posts.length, 1, "final deadline check still attempts recovery");
  for (const source of [true, false]) {
    const running = mock({ source, active: true });
    await assert.rejects(tick(env, deadline, running.fetcher, deadline), /Deadline missed.*still running/);
    assert.equal(running.posts.length, 0);
  }
  const unavailable = mock({ badStatus: 503 });
  await assert.rejects(tick(env, winter, unavailable.fetcher, winter), error => !error.message.includes("test-only-secret") && error.message.includes("HTTP 503"));
});

// A redirect must never be followed with the GitHub credential.
test("GitHub redirects fail closed without dispatch or credential disclosure", async () => {
  for (const status of [301, 302, 307, 308]) {
    const m = mock({ badStatus: status });
    await assert.rejects(tick(env, winter, m.fetcher, winter), error =>
      error.message.includes(`HTTP ${status}`) && !error.message.includes(env.GITHUB_TOKEN));
    assert.equal(m.posts.length, 0);
  }
});
