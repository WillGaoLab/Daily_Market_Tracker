import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

// Exercise native workerd fetch/Request construction, not Node's mocked fetch.
// All network requests are intercepted; no real credential or GitHub writes.
const scheduler = readFileSync(new URL("scheduler.mjs", import.meta.url), "utf8");
const script = scheduler.replace("export default {", "const scheduledHandler = {") + `
export default {
  async fetch() {
    const timestamp = Date.parse("2026-11-05T21:20:00Z");
    try {
      return Response.json(await tick({SOURCE_REPO:"owner/source", MIRROR_REPO:"owner/mirror",
        GITHUB_TOKEN:"runtime-test-only"}, timestamp, fetch, timestamp));
    } catch (error) { return Response.json({error:error.message}, {status:500}); }
  }
};`;

test("workerd can reach GitHub and dispatch; redirects never forward credentials", async () => {
  let redirect = false;
  const requests = [];
  const mf = new Miniflare(convertV4MiniflareOptions({
    modules: true, script, compatibilityDate: "2026-11-05", compatibilityFlags: ["nodejs_compat"],
    outboundService: async request => {
      requests.push({ url: request.url, method: request.method });
      assert.equal(new URL(request.url).hostname, "api.github.com");
      assert.equal(request.headers.get("Authorization"), "Bearer runtime-test-only");
      if (redirect) return new Response(null, {status:302, headers:{Location:"https://untrusted.invalid/"}});
      if (request.method === "POST") {
        assert.match(request.url, /daily_market.yml\/dispatches$/);
        assert.deepEqual(await request.json(), {ref:"main",inputs:{date:"2026-11-05"}});
        return new Response(null, {status:204});
      }
      if (request.url.includes("git/ref/")) return Response.json({object:{sha:"a".repeat(40)}});
      if (request.url.includes("git/trees/")) return Response.json({tree:[{path:"data/history.csv",type:"blob",sha:"b".repeat(40)}]});
      if (request.url.includes("git/blobs/")) return Response.json({encoding:"base64",content:Buffer.from("date,source\n").toString("base64")});
      if (request.url.includes("/runs?")) return Response.json({workflow_runs:[]});
      throw new Error("Unexpected request");
    },
  }));
  try {
    const response = await mf.dispatchFetch("http://localhost/");
    assert.equal(response.status, 200, await response.clone().text());
    assert.equal((await response.json()).status, "source_dispatched");
    assert.equal(requests.filter(r => r.method === "POST").length, 1);
    requests.length = 0; redirect = true;
    const rejected = await mf.dispatchFetch("http://localhost/");
    assert.equal(rejected.status, 500);
    assert.match((await rejected.json()).error, /HTTP 302/);
    assert.equal(requests.length, 1, "must not follow Location or dispatch");
  } finally { await mf.dispose(); }
});
