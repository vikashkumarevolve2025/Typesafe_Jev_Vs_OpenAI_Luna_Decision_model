import type { MoveRequest, MoveResponse, PlayerInfo } from "./types";

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body?.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function fetchPlayers(): Promise<PlayerInfo[]> {
  return asJson<PlayerInfo[]>(await fetch("/api/players", { cache: "no-store" }));
}

const MOVE_ATTEMPTS = 3;

// /api/move is stateless (the whole move list is sent each time), so a dropped connection or a
// 5xx from the proxy — e.g. the backend reloading mid-request — is safe to retry.
export async function requestMove(body: MoveRequest, signal?: AbortSignal): Promise<MoveResponse> {
  for (let attempt = 1; ; attempt++) {
    let res: Response;
    try {
      res = await fetch("/api/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
    } catch (e) {
      if (signal?.aborted || attempt >= MOVE_ATTEMPTS) throw e;
      await new Promise((r) => setTimeout(r, 1000 * attempt));
      continue;
    }
    if (res.status >= 500 && attempt < MOVE_ATTEMPTS && !signal?.aborted) {
      await new Promise((r) => setTimeout(r, 1000 * attempt));
      continue;
    }
    return asJson<MoveResponse>(res);
  }
}
