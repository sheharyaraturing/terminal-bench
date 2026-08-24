import { isEnabled } from "./shared/flags";
import { navItems } from "./nav";
import { mountExpressLane } from "./checkout/expressLane";

export function boot(root: HTMLElement): void {
  renderNav(root, navItems());
  mountExpressLane(root);
  if (isEnabled("identity.passkey_enrolment")) {
    promptPasskey(root);
  }
  if (isEnabled("web.new_nav")) {
    root.classList.add("nav-next");
  }
  if (!isEnabled("identity.session_pinning", true)) {
    root.dataset.pinned = "false";
  }
}

function renderNav(root: HTMLElement, items: string[]): void {
  const nav = document.createElement("nav");
  nav.append(...items.map((label) => link(label)));
  root.append(nav);
}

function link(label: string): HTMLElement {
  const a = document.createElement("a");
  a.textContent = label;
  return a;
}

function promptPasskey(root: HTMLElement): void {
  root.dataset.passkeyPrompt = "1";
}
