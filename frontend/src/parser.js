const PARSER_URL = import.meta.env.VITE_PARSER_URL;

const MESSAGES = {
  401: "Please sign in again.",
  413: "The text is too long (max 10,000 characters).",
  422: "The model could not find an agenda in this text. Type it by hand.",
  429: "The service is busy. Try again in a minute.",
};

export async function parseAgenda(text, token, signal) {
  let res;
  try {
    res = await fetch(PARSER_URL, {
      method: "POST",
      signal,
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify({
        text,
        today: new Date().toLocaleDateString("sv"), // YYYY-MM-DD in the user's time zone
        tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }),
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("Network error. Check your connection and try again.");
  }
  if (!res.ok) {
    const err = new Error(MESSAGES[res.status] ?? "Parsing failed. Type the agenda by hand.");
    err.status = res.status;
    throw err;
  }
  return res.json(); // { agenda, model, prompt_version }
}
