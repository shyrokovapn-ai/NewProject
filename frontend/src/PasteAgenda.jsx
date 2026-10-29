import { useRef, useState } from "react";
import { getToken, signIn, signOut } from "./auth.js";
import { parseAgenda } from "./parser.js";

const MAX_CHARS = 10_000;

export default function PasteAgenda({ onParsed }) {
  const [text, setText] = useState("");
  const [token, setToken] = useState(getToken());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef(null);

  if (!import.meta.env.VITE_PARSER_URL) {
    return <p className="text-sm text-neutral-500">Paste an agenda is not configured here.</p>;
  }
  if (!token) return <SignIn onSignedIn={setToken} />;

  async function parse() {
    setError("");
    setBusy(true);
    abortRef.current = new AbortController();
    try {
      onParsed(await parseAgenda(text, token, abortRef.current.signal));
    } catch (e) {
      if (e.name === "AbortError") return;
      if (e.status === 401) {
        signOut();
        setToken(null);
      }
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="Paste an email, a chat message or a few lines of notes…"
        className="w-full rounded-lg border border-line bg-white p-3 text-sm"
      />
      <div className="mt-2 flex items-center gap-3">
        {busy ? (
          <>
            <span className="text-sm text-neutral-600" role="status">
              Reading your text… this takes a few seconds
            </span>
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="rounded-lg border border-line px-3 py-2 text-sm font-semibold"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={parse}
            disabled={!text.trim() || text.length > MAX_CHARS}
            className="rounded-lg bg-ajax px-4 py-2 text-sm font-bold text-white disabled:opacity-40"
          >
            Parse
          </button>
        )}
        <span className="ml-auto text-xs text-neutral-400">
          {text.length}/{MAX_CHARS}
        </span>
        <button
          type="button"
          onClick={() => {
            signOut();
            setToken(null);
          }}
          className="text-xs text-neutral-400 underline"
        >
          Sign out
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-ajax-dark">
          {error}
        </p>
      )}
    </div>
  );
}

function SignIn({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      onSignedIn(await signIn(email, password));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <p className="w-full text-sm text-neutral-600">Sign in to paste an agenda.</p>
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
      />
      <input
        type="password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
      />
      <button className="rounded-lg bg-ink px-4 py-2 text-sm font-bold text-white">Sign in</button>
      {error && (
        <p role="alert" className="w-full text-sm text-ajax-dark">
          {error}
        </p>
      )}
    </form>
  );
}
