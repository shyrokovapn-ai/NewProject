import { useState } from "react";
import { saveAgenda } from "./api.js";

const blankItem = () => ({ topic: "", owner: "", minutes: "", sug: {} });
const blankAction = () => ({ task: "", owner: "", due: "", sug: {} });

export function fromSaved(agenda) {
  if (!agenda) return { items: [blankItem()], actions: [], suggestion: null };
  return {
    items: agenda.items.map((i) => ({
      topic: i.topic,
      owner: i.owner ?? "",
      minutes: i.minutes ?? "",
      sug: {},
    })),
    actions: agenda.action_items.map((a) => ({
      task: a.task,
      owner: a.owner ?? "",
      due: a.due ?? "",
      sug: {},
    })),
    suggestion: agenda.ai_suggestion,
  };
}

// Everything the model filled is marked "suggested" until the user touches it.
export function fromParsed(result) {
  const a = result.agenda;
  return {
    items: a.items.map((i) => ({
      topic: i.topic,
      owner: i.owner ?? "",
      minutes: i.minutes ?? "",
      sug: { topic: true, owner: i.owner != null, minutes: i.minutes != null },
    })),
    actions: a.action_items.map((x) => ({
      task: x.task,
      owner: x.owner ?? "",
      due: x.due ?? "",
      sug: { task: true, owner: x.owner != null, due: x.due != null },
    })),
    suggestion: { agenda: a, model: result.model, prompt_version: result.prompt_version },
  };
}

function Field({ label, value, suggested, onChange, type = "text", className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 flex items-center gap-2 text-xs font-semibold text-neutral-500">
        {label}
        {suggested && (
          <span className="rounded bg-ajax/10 px-1.5 py-0.5 text-[10px] font-bold uppercase text-ajax">
            suggested
          </span>
        )}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"
      />
    </label>
  );
}

export default function AgendaEditor({ meetingId, initial }) {
  const [items, setItems] = useState(initial.items);
  const [actions, setActions] = useState(initial.actions);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const suggested = initial.suggestion?.agenda;

  const edit = (set) => (i, key, value) =>
    set((rows) =>
      rows.map((r, j) => (j === i ? { ...r, [key]: value, sug: { ...r.sug, [key]: false } } : r)),
    );
  const editItem = edit(setItems);
  const editAction = edit(setActions);

  async function save() {
    setBusy(true);
    setStatus("");
    try {
      await saveAgenda(meetingId, {
        items: items
          .filter((r) => r.topic.trim())
          .map((r) => ({
            topic: r.topic.trim(),
            owner: r.owner.trim() || null,
            minutes: r.minutes === "" ? null : Number(r.minutes),
          })),
        action_items: actions
          .filter((r) => r.task.trim())
          .map((r) => ({ task: r.task.trim(), owner: r.owner.trim() || null, due: r.due || null })),
        ai_suggestion: initial.suggestion,
      });
      setStatus("Saved");
    } catch (e) {
      setStatus(`Could not save: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {suggested && (suggested.title || suggested.starts_at || suggested.duration_minutes) && (
        <p className="mb-3 rounded-lg bg-mist px-3 py-2 text-xs text-neutral-600">
          Model also noticed:{" "}
          {[
            suggested.title,
            suggested.starts_at,
            suggested.duration_minutes && `${suggested.duration_minutes} min`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}

      <h3 className="mb-2 text-sm font-bold">Agenda items</h3>
      {items.map((r, i) => (
        <div key={i} className="mb-2 grid grid-cols-[1fr_9rem_5rem] gap-2">
          <Field
            label="Topic"
            value={r.topic}
            suggested={r.sug.topic}
            onChange={(v) => editItem(i, "topic", v)}
          />
          <Field
            label="Owner"
            value={r.owner}
            suggested={r.sug.owner}
            onChange={(v) => editItem(i, "owner", v)}
          />
          <Field
            label="Min"
            type="number"
            value={r.minutes}
            suggested={r.sug.minutes}
            onChange={(v) => editItem(i, "minutes", v)}
          />
        </div>
      ))}
      <button
        type="button"
        onClick={() => setItems([...items, blankItem()])}
        className="text-sm font-semibold text-ajax"
      >
        + Add item
      </button>

      <h3 className="mb-2 mt-5 text-sm font-bold">Action items</h3>
      {actions.map((r, i) => (
        <div key={i} className="mb-2 grid grid-cols-[1fr_9rem_9rem] gap-2">
          <Field
            label="Task"
            value={r.task}
            suggested={r.sug.task}
            onChange={(v) => editAction(i, "task", v)}
          />
          <Field
            label="Owner"
            value={r.owner}
            suggested={r.sug.owner}
            onChange={(v) => editAction(i, "owner", v)}
          />
          <Field
            label="Due"
            type="date"
            value={r.due}
            suggested={r.sug.due}
            onChange={(v) => editAction(i, "due", v)}
          />
        </div>
      ))}
      <button
        type="button"
        onClick={() => setActions([...actions, blankAction()])}
        className="text-sm font-semibold text-ajax"
      >
        + Add action item
      </button>

      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className="rounded-lg bg-ink px-5 py-2 text-sm font-bold text-white disabled:opacity-40"
        >
          Save
        </button>
        {status && (
          <span role="status" className="text-sm text-neutral-600">
            {status}
          </span>
        )}
      </div>
    </div>
  );
}
