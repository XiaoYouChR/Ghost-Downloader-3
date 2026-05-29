import {DouyinStrategy} from "./strategies/douyin";
import {GenericStrategy} from "./strategies/generic";
import {XStrategy} from "./strategies/x";

import type {MediaStrategy} from "./strategy";

export class StrategyRegistry {
  private readonly strategies: MediaStrategy[] = [];

  register(strategy: MediaStrategy): void {
    this.strategies.push(strategy);
  }

  // Relies on GenericStrategy being registered last (matches() always true).
  pick(pageUrl: URL): MediaStrategy {
    return this.strategies.find((strategy) => strategy.matches(pageUrl))!;
  }
}

export function createDefaultRegistry(): StrategyRegistry {
  const registry = new StrategyRegistry();
  registry.register(new DouyinStrategy());
  registry.register(new XStrategy());
  registry.register(new GenericStrategy());
  return registry;
}
