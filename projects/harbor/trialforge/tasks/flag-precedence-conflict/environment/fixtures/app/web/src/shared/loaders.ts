import { isEnabled } from "./flags";

export function skeletonRows(count: number): HTMLElement[] {
  if (!isEnabled("web.skeleton_loaders", true)) {
    return [];
  }
  return Array.from({ length: count }, () => {
    const el = document.createElement("li");
    el.className = "skeleton";
    return el;
  });
}
