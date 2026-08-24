import { isEnabled } from "../shared/flags";

export function mountExpressLane(root: HTMLElement): boolean {
  if (!isEnabled("checkout.express_lane")) {
    return false;
  }
  const button = document.createElement("button");
  button.textContent = "Buy now";
  button.className = "express-lane";
  root.append(button);
  return true;
}
