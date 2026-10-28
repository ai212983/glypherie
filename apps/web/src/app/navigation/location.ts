/// <reference types="vite/client" />
// Vite owns the hosting prefix; the same base is used for assets, routes and the worker.
export const appBase: string = import.meta.env?.BASE_URL ?? "/";

/** App-relative path, accepting old fragment routes until they are canonicalized. */
export function readRoutePath(): string {
  if (window.location.hash.startsWith("#/") || window.location.hash.startsWith("#family-")) return window.location.hash;
  const pathname = window.location.pathname;
  return pathname.startsWith(appBase) ? `/${pathname.slice(appBase.length)}` : pathname;
}

export function readRouteSearch(): string {
  if (window.location.hash.startsWith("#/")) {
    const query = window.location.hash.indexOf("?");
    return query < 0 ? "" : window.location.hash.slice(query + 1);
  }
  return window.location.search.replace(/^\?/, "");
}

/** Navigate from shared anchors; the app handles popstate just like browser Back. */
export function navigateTo(path: string): void {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
