export type BypassShortcut = {
  code: string;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  metaKey: boolean;
};

export const DEFAULT_BYPASS_SHORTCUT: BypassShortcut = {
  code: "", ctrlKey: false, altKey: true, shiftKey: false, metaKey: false,
};

export function parseBypassShortcut(stored: unknown): BypassShortcut {
  if (stored && typeof stored === "object" && typeof (stored as BypassShortcut).code === "string") {
    return stored as BypassShortcut;
  }
  return DEFAULT_BYPASS_SHORTCUT;
}

export function toBypassShortcut(event: KeyboardEvent): BypassShortcut {
  const isModifier = ["Control", "Alt", "Shift", "Meta"].includes(event.key);
  return {
    code: isModifier ? "" : event.code,
    ctrlKey: event.ctrlKey,
    altKey: event.altKey,
    shiftKey: event.shiftKey,
    metaKey: event.metaKey,
  };
}

export function toShortcutLabel(shortcut: BypassShortcut): string {
  const parts: string[] = [];
  if (shortcut.ctrlKey) parts.push("Ctrl");
  if (shortcut.altKey) parts.push("Alt");
  if (shortcut.shiftKey) parts.push("Shift");
  if (shortcut.metaKey) parts.push("Meta");
  if (shortcut.code) parts.push(toKeyLabel(shortcut.code));
  return parts.join(" + ") || "—";
}

function toKeyLabel(code: string): string {
  if (code.startsWith("Key")) return code.slice(3);
  if (code.startsWith("Digit")) return code.slice(5);
  if (code.startsWith("Numpad")) return "Num" + code.slice(6);
  return code;
}
