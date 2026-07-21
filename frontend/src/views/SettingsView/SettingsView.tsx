import { Outlet } from "react-router";

import { SettingsNav } from "./components/SettingsNav";

/**
 * Settings layout: a titled single column with the sub-navigation and the routed
 * section below it. Each section (Account, Connected agents, Archive & Trash,
 * Data) is a nested route rendered through `<Outlet/>`. The panels own their own
 * data and destructive-action confirmation; this shell only composes them.
 */
export function SettingsView() {
  return (
    <section className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account, connected agents, archived items, and data.
        </p>
      </header>
      <SettingsNav />
      <Outlet />
    </section>
  );
}
