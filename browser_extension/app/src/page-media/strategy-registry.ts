import {DouyinStrategy} from "./strategies/douyin";
import {GenericStrategy} from "./strategies/generic";
import {XStrategy} from "./strategies/x";

import type {MediaStrategy} from "./strategy";

// Order matters: GenericStrategy is the fallback (matches() always true), so it stays last.
const STRATEGIES: readonly MediaStrategy[] = [
  new DouyinStrategy(),
  new XStrategy(),
  new GenericStrategy(),
];

export function pickStrategy(pageUrl: URL): MediaStrategy {
  return STRATEGIES.find((strategy) => strategy.matches(pageUrl))!;
}
