// One stateless, scheduled-only Worker: no storage, paid bindings or HTTP route.
const API = "https://api.github.com";
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const NY = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export function newYorkTime(timestamp) {
  const parts = Object.fromEntries(NY.formatToParts(timestamp).map(p => [p.type, p.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, hour: Number(parts.hour), minute: Number(parts.minute) };
}

function day(year, month, date) { return new Date(Date.UTC(year, month - 1, date)); }
function iso(value) { return value.toISOString().slice(0, 10); }
function observed(value) {
  const result = new Date(value);
  if (result.getUTCDay() === 6) result.setUTCDate(result.getUTCDate() - 1);
  if (result.getUTCDay() === 0) result.setUTCDate(result.getUTCDate() + 1);
  return iso(result);
}
function nth(year, month, weekday, occurrence) {
  const first = day(year, month, 1);
  return iso(day(year, month, 1 + (weekday - first.getUTCDay() + 7) % 7 + 7 * (occurrence - 1)));
}
function easter(year) {
  const a = year % 19, b = Math.floor(year / 100), c = year % 100;
  const d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
  return day(year, Math.floor((h + l - 7 * m + 114) / 31), (h + l - 7 * m + 114) % 31 + 1);
}

// Matches scripts/fetch_data.py's regular NYSE full-day holiday policy.
export function isMarketDay(date) {
  const value = new Date(`${date}T00:00:00Z`), year = value.getUTCFullYear();
  if ([0, 6].includes(value.getUTCDay())) return false;
  const goodFriday = easter(year); goodFriday.setUTCDate(goodFriday.getUTCDate() - 2);
  const memorial = day(year, 6, 0); memorial.setUTCDate(memorial.getUTCDate() - (memorial.getUTCDay() + 6) % 7);
  const holidays = new Set([
    observed(day(year, 1, 1)), nth(year, 1, 1, 3), nth(year, 2, 1, 3), iso(goodFriday), iso(memorial),
    observed(day(year, 7, 4)), nth(year, 9, 1, 1), nth(year, 11, 4, 4), observed(day(year, 12, 25)),
    observed(day(year + 1, 1, 1)),
  ]);
  if (year >= 2022) holidays.add(observed(day(year, 6, 19)));
  return !holidays.has(date);
}

async function readJson(response) {
  if (Number(response.headers.get("content-length")) > MAX_BODY_BYTES) throw new Error("GitHub response too large");
  const reader = response.body.getReader();
  const chunks = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) throw new Error("GitHub response too large");
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return JSON.parse(new TextDecoder().decode(bytes));
}

function github(token, fetcher) {
  return async (path, body) => {
    const response = await fetcher(`${API}${path}`, {
      method: body ? "POST" : "GET",
      headers: {
        Accept: "application/vnd.github+json", Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "daily-market-scheduler",
        "Cache-Control": "no-cache", ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      // Workers rejects redirect: "error" before sending the request.
      // Manual mode prevents forwarding the credential; !ok rejects every 3xx.
      signal: AbortSignal.timeout(15000), redirect: "manual",
    });
    if (!response.ok) {
      await response.body?.cancel();
      // Do not log response bodies, headers or credentials.
      throw new Error(`GitHub ${body ? "POST" : "GET"} ${path}: HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    return readJson(response);
  };
}

export async function snapshot(api, repo, branch, date) {
  const ref = await api(`/repos/${repo}/git/ref/heads/${encodeURIComponent(branch)}`);
  const commit = ref.object?.sha;
  if (!/^[a-f0-9]{40}$/.test(commit ?? "")) throw new Error("Invalid GitHub branch reference");
  const tree = await api(`/repos/${repo}/git/trees/${commit}?recursive=1`);
  if (tree.truncated || !Array.isArray(tree.tree)) throw new Error("Incomplete GitHub tree");
  const files = new Map(tree.tree.filter(x => x.type === "blob").map(x => [x.path, x.sha]));
  const historySha = files.get("data/history.csv");
  if (!historySha) throw new Error(`Missing history.csv in ${repo}`);
  const blob = await api(`/repos/${repo}/git/blobs/${historySha}`);
  if (blob.encoding !== "base64" || typeof blob.content !== "string") throw new Error("Invalid history blob");
  const csv = atob(blob.content.replace(/\s/g, ""));
  const rows = csv.split(/\r?\n/).filter(line => line.startsWith(`${date},`) || line.startsWith(`"${date}",`));
  if (rows.length > 1) throw new Error(`Duplicate target date in ${repo}`);
  const png = files.get(`figures/${date}.png`), svg = files.get(`figures/${date}.svg`);
  return { commit, row: rows[0] ?? null, png, svg, complete: rows.length === 1 && Boolean(png && svg) };
}

async function hasActiveRun(api, repo, workflow, branch) {
  const result = await api(`/repos/${repo}/actions/workflows/${workflow}/runs?branch=${encodeURIComponent(branch)}&per_page=10`);
  if (!Array.isArray(result.workflow_runs)) throw new Error("Invalid workflow run list");
  return result.workflow_runs.some(run => ["queued", "in_progress", "waiting", "pending", "requested"].includes(run.status));
}

export async function tick(env, timestamp, fetcher = fetch, now = Date.now()) {
  const when = newYorkTime(timestamp), current = newYorkTime(now);
  if (when.date !== current.date || when.hour !== 16 || ![20, 25, 30].includes(when.minute) || !isMarketDay(when.date)) {
    return { status: "skipped", date: when.date };
  }
  const sourceToken = env.SOURCE_GITHUB_TOKEN || env.GITHUB_TOKEN;
  const mirrorToken = env.MIRROR_GITHUB_TOKEN || env.GITHUB_TOKEN;
  if (!sourceToken || !mirrorToken) throw new Error("Missing GitHub scheduler secrets");
  const sourceApi = github(sourceToken, fetcher), mirrorApi = github(mirrorToken, fetcher);
  const branch = env.BRANCH || "main", date = when.date;
  const source = await snapshot(sourceApi, env.SOURCE_REPO, branch, date);
  if (!source.complete) {
    if (await hasActiveRun(sourceApi, env.SOURCE_REPO, "daily_market.yml", branch)) {
      if (when.minute === 30) throw new Error(`Deadline missed: canonical ${date} workflow still running`);
      return { status: "source_running", date };
    }
    await sourceApi(`/repos/${env.SOURCE_REPO}/actions/workflows/daily_market.yml/dispatches`, { ref: branch, inputs: { date } });
    if (when.minute === 30) throw new Error(`Deadline missed: canonical ${date} incomplete; final recovery dispatched`);
    return { status: "source_dispatched", date };
  }
  const mirror = await snapshot(mirrorApi, env.MIRROR_REPO, branch, date);
  if (mirror.complete && mirror.row === source.row && mirror.png === source.png && mirror.svg === source.svg) {
    return { status: "complete", date, source_commit: source.commit, mirror_commit: mirror.commit };
  }
  if (mirror.row && mirror.row !== source.row) throw new Error(`Mirror conflict for ${date}; historical rows will not be overwritten`);
  if (await hasActiveRun(mirrorApi, env.MIRROR_REPO, "mirror_market.yml", branch)) {
    if (when.minute === 30) throw new Error(`Deadline missed: mirror ${date} workflow still running`);
    return { status: "mirror_running", date };
  }
  await mirrorApi(`/repos/${env.MIRROR_REPO}/actions/workflows/mirror_market.yml/dispatches`, {
    ref: branch, inputs: { date, source_ref: source.commit },
  });
  if (when.minute === 30) throw new Error(`Deadline missed: mirror ${date} incomplete; final recovery dispatched`);
  return { status: "mirror_dispatched", date, source_commit: source.commit };
}

export default {
  async scheduled(controller, env) {
    try {
      const result = await tick(env, controller.scheduledTime);
      console.log(JSON.stringify(result));
    } catch (error) {
      console.error(JSON.stringify({ status: "failed", error: error.message }));
      throw error;
    }
  },
};
