const API = import.meta.env.VITE_API_URL ?? "";

async function request(path, options) {
  const res = await fetch(`${API}${path}`, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (res.status === 404 && options?.allow404) return null;
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export const listMeetings = () => request("/api/meetings");
export const createMeeting = (body) =>
  request("/api/meetings", { method: "POST", body: JSON.stringify(body) });
export const getAgenda = (id) => request(`/api/meetings/${id}/agenda`, { allow404: true });
export const saveAgenda = (id, body) =>
  request(`/api/meetings/${id}/agenda`, { method: "POST", body: JSON.stringify(body) });
