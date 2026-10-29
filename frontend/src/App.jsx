import { useEffect, useState } from "react";
import AgendaEditor, { fromParsed, fromSaved } from "./AgendaEditor.jsx";
import PasteAgenda from "./PasteAgenda.jsx";
import { createMeeting, getAgenda, listMeetings } from "./api.js";

const fmt = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

export default function App() {
  const [meetings, setMeetings] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  const load = () =>
    listMeetings()
      .then(setMeetings)
      .catch(() => setError("Could not load meetings."));
  useEffect(() => {
    load();
  }, []);

  return (
    <div className="min-h-screen">
      <header className="bg-panel px-6 py-4 text-xl font-extrabold text-white">
        Spry <span className="text-ajax">·</span> meetings
      </header>
      <main className="mx-auto grid max-w-5xl gap-6 p-6 md:grid-cols-[18rem_1fr]">
        <aside>
          <NewMeeting
            onCreated={(m) => {
              load();
              setSelected(m);
            }}
          />
          {error && <p className="mt-3 text-sm text-ajax-dark">{error}</p>}
          <ul className="mt-4 space-y-2">
            {meetings.map((m) => (
              <li key={m.id}>
                <button
                  onClick={() => setSelected(m)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                    selected?.id === m.id ? "border-ajax bg-white" : "border-line bg-white"
                  }`}
                >
                  <div className="font-semibold">{m.title}</div>
                  <div className="text-xs text-neutral-500">{fmt(m.starts_at)}</div>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <section className="rounded-2xl bg-white p-6">
          {selected ? (
            <MeetingPage key={selected.id} meeting={selected} />
          ) : (
            <p className="text-neutral-500">Pick a meeting or create one.</p>
          )}
        </section>
      </main>
    </div>
  );
}

function MeetingPage({ meeting }) {
  const [form, setForm] = useState(null); // { items, actions, suggestion, version }

  useEffect(() => {
    getAgenda(meeting.id)
      .then((a) => setForm({ ...fromSaved(a), version: 0 }))
      .catch(() => setForm({ ...fromSaved(null), version: 0 }));
  }, [meeting.id]);

  return (
    <div>
      <h2 className="text-xl font-extrabold">{meeting.title}</h2>
      <p className="mb-5 text-sm text-neutral-500">{fmt(meeting.starts_at)}</p>

      <h3 className="mb-2 text-sm font-bold">Paste an agenda</h3>
      <PasteAgenda
        onParsed={(r) => setForm((f) => ({ ...fromParsed(r), version: f.version + 1 }))}
      />

      <hr className="my-6 border-line" />
      {form && <AgendaEditor key={form.version} meetingId={meeting.id} initial={form} />}
    </div>
  );
}

function NewMeeting({ onCreated }) {
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const m = await createMeeting({
        title,
        starts_at: new Date(start).toISOString(),
        ends_at: new Date(end).toISOString(),
      });
      setTitle("");
      onCreated(m);
    } catch {
      setError("Check the title and that the end is after the start.");
    }
  }

  const input = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm";
  return (
    <form onSubmit={submit} className="space-y-2 rounded-2xl bg-white p-4">
      <h2 className="text-sm font-bold">New meeting</h2>
      <input
        required
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        className={input}
      />
      <input
        required
        type="datetime-local"
        value={start}
        onChange={(e) => setStart(e.target.value)}
        className={input}
        aria-label="Starts"
      />
      <input
        required
        type="datetime-local"
        value={end}
        onChange={(e) => setEnd(e.target.value)}
        className={input}
        aria-label="Ends"
      />
      <button className="w-full rounded-lg bg-ajax px-4 py-2 text-sm font-bold text-white">
        Create
      </button>
      {error && <p className="text-xs text-ajax-dark">{error}</p>}
    </form>
  );
}
