const USER_AGENTS = [
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
];

exports.handler = async (event) => {
  const idsParam = event.queryStringParameters?.ids || "";
  const jobIds = idsParam.split(",").map(s => s.trim()).filter(Boolean);

  if (jobIds.length > 50) {
    return { statusCode: 400, body: JSON.stringify({ error: "Too many IDs (max 50)" }) };
  }

  const fetchCount = async (jobId) => {
    const ua = USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const resp = await fetch(`https://www.linkedin.com/jobs/view/${jobId}`, {
          headers: { "User-Agent": ua },
        });
        const html = await resp.text();
        const m = html.match(/(\d+)\s*applicants?/i);
        if (m) return parseInt(m[1], 10);
        if (html.includes("Be the first") || html.includes("İlk başvuran")) return 0;
        return null;
      } catch {
        if (attempt < 2) await new Promise(r => setTimeout(r, 2000));
        continue;
      }
    }
    return null;
  };

  const counts = {};
  for (let i = 0; i < jobIds.length; i += 5) {
    const chunk = jobIds.slice(i, i + 5);
    const results = await Promise.allSettled(chunk.map(id => fetchCount(id)));
    results.forEach((res, idx) => {
      counts[chunk[idx]] = res.status === "fulfilled" ? res.value : null;
    });
  }

  return {
    statusCode: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
    body: JSON.stringify(counts),
  };
};
