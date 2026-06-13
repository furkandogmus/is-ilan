/**
 * Netlify Function — LinkedIn location autocomplete proxy
 * GET /.netlify/functions/typeahead?q=ista
 * Proxies LinkedIn's public guest GEO typeahead (returns JSON: [{id, type, displayName}]).
 */
const USER_AGENTS = [
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
];

exports.handler = async (event) => {
  const query = (event.queryStringParameters?.q || "").trim();

  const jsonHeaders = {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
  };

  if (query.length < 2) {
    return { statusCode: 200, headers: jsonHeaders, body: "[]" };
  }

  const params = new URLSearchParams({ query, typeaheadType: "GEO" });
  const url = `https://www.linkedin.com/jobs-guest/api/typeaheadHits?${params.toString()}`;
  const ua = USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];

  try {
    const resp = await fetch(url, { headers: { "User-Agent": ua } });
    const body = await resp.text();
    return {
      statusCode: 200,
      headers: { ...jsonHeaders, "Cache-Control": "max-age=120" },
      body,
    };
  } catch (e) {
    return {
      statusCode: 502,
      headers: jsonHeaders,
      body: JSON.stringify({ error: e.message }),
    };
  }
};
