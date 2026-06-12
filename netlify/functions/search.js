/**
 * Netlify Function — LinkedIn job search proxy
 * GET /.netlify/functions/search?keywords=devops&location=Turkey&hours=24&start=0
 */
const USER_AGENTS = [
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
];

function isBlocked(html) {
  const signals = ["challenge-platform", "captcha", "please verify you're not a robot", "too many requests"];
  return signals.some(s => html.toLowerCase().includes(s));
}

exports.handler = async (event) => {
  const params = new URLSearchParams(event.queryStringParameters || {});
  const keywords = params.get("keywords") || "devops";
  const start = params.get("start") || "0";
  const hours = params.get("hours");
  const remote = params.get("remote");
  const location = params.get("location");

  const hoursNum = parseInt(hours, 10);
  if (hours && (isNaN(hoursNum) || hoursNum < 1 || hoursNum > 720)) {
    return { statusCode: 400, body: "Invalid hours parameter" };
  }

  const linkedinParams = new URLSearchParams({ keywords, start });
  if (hours) linkedinParams.set("f_TPR", `r${hoursNum * 3600}`);
  if (remote === "1") linkedinParams.set("f_WT", "2");
  else if (location) linkedinParams.set("location", location);

  const url = `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?${linkedinParams.toString()}`;

  const ua = USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const resp = await fetch(url, {
        headers: { "User-Agent": ua },
      });
      const body = await resp.text();
      if (isBlocked(body)) {
        return {
          statusCode: 429,
          headers: { "Access-Control-Allow-Origin": "*" },
          body: "LinkedIn isteği engelledi (rate limit / captcha)",
        };
      }
      return {
        statusCode: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Access-Control-Allow-Origin": "*",
        },
        body,
      };
    } catch (e) {
      if (attempt < 2) {
        await new Promise(r => setTimeout(r, 3000 * Math.pow(2, attempt)));
        continue;
      }
      return {
        statusCode: 502,
        headers: { "Access-Control-Allow-Origin": "*" },
        body: `Proxy error: ${e.message}`,
      };
    }
  }
};
