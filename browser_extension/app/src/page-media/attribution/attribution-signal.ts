import type {MseAttributionSignal} from "../types";

// The typed contract for the MAIN-world probe → ISOLATED-world attribution engine channel.
// Both ends import this file: the probe posts via postMediaSignal, the engine guards with
// isMediaSignal. The signal shapes live in MseAttributionSignal (./types). The probe and
// engine are bundled separately, so each carries its own copy of the key — they agree on
// the string, not on a shared runtime object.

export const MEDIA_SIGNAL_KEY = "__gdMediaSignal";

type TaggedSignal = MseAttributionSignal & { [MEDIA_SIGNAL_KEY]?: true };

// MAIN world → ISOLATED world. Swallows the throw a detached frame raises.
export function postMediaSignal(signal: MseAttributionSignal): void {
  try {
    window.postMessage({ [MEDIA_SIGNAL_KEY]: true, ...signal }, "*");
  } catch {
    // Detached frame.
  }
}

export function isMediaSignal(data: unknown): data is MseAttributionSignal {
  return (
    typeof data === "object"
    && data !== null
    && (data as TaggedSignal)[MEDIA_SIGNAL_KEY] === true
  );
}
