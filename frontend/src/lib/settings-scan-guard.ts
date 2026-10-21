const owners = new Set<symbol>();
const listeners = new Set<() => void>();
export const settingsScanBlocked = () => owners.size > 0;
export const subscribeSettingsScanGuard = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };

// A pending save outlives the Settings page; an abandoned, unsent draft does not.
export function createSettingsScanGuard() {
  const id = Symbol("settings roots");
  let active = true, draft = false, saving = false;
  const publish = () => {
    const before = settingsScanBlocked();
    if ((active && draft) || saving) owners.add(id); else owners.delete(id);
    if (before !== settingsScanBlocked()) for (const listener of listeners) listener();
  };
  return {
    acquire: () => { active = true; publish(); },
    release: () => { active = false; publish(); },
    setDraft: (value: boolean) => { draft = value; publish(); },
    setSaving: (value: boolean) => { saving = value; publish(); },
  };
}
