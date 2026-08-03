import { describe, expect, it } from "vitest";
import { shouldShowEuMiner } from "./eu-miner-route";

describe("shouldShowEuMiner", () => {
  it("uses the explicit EU miner route", () => {
    expect(shouldShowEuMiner("/eu-miner", "quantforge.giorgiy.org")).toBe(true);
    expect(shouldShowEuMiner("/eu-miner/", "quantforge.giorgiy.org")).toBe(true);
  });

  it("uses the EU page as the root experience on dedicated hosts", () => {
    expect(shouldShowEuMiner("/", "eu.quantforge.giorgiy.org")).toBe(true);
    expect(shouldShowEuMiner("/", "miner.quantforge.giorgiy.org")).toBe(true);
  });

  it("keeps the research terminal on the primary host", () => {
    expect(shouldShowEuMiner("/", "quantforge.giorgiy.org")).toBe(false);
  });
});
