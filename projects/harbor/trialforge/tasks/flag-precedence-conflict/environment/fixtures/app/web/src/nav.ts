import { isEnabled } from "./shared/flags";

const LEGACY_ITEMS = ["Home", "Orders", "Account"];
const NEXT_ITEMS = ["Home", "Orders", "Subscriptions", "Account", "Help"];

export function navItems(): string[] {
  return isEnabled("web.new_nav") ? NEXT_ITEMS : LEGACY_ITEMS;
}
