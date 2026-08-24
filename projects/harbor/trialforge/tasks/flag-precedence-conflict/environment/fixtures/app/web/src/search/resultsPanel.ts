import { isEnabled } from "../shared/flags";
import { skeletonRows } from "../shared/loaders";

// The panel renders a "sorted by relevance" affordance and suppresses the
// score column when the semantic reranker is in play, because the raw BM25
// score stops matching the displayed order.
export function renderResults(root: HTMLElement, hits: Hit[]): void {
  const reranked = isEnabled("search.semantic_rerank", true);
  root.replaceChildren(
    ...(hits.length === 0 ? skeletonRows(5) : hits.map((h) => row(h, reranked)))
  );
}

function row(hit: Hit, reranked: boolean): HTMLElement {
  const el = document.createElement("li");
  el.textContent = hit.title;
  if (!reranked) {
    el.dataset.score = hit.score.toFixed(3);
  }
  return el;
}

export interface Hit {
  title: string;
  score: number;
}
