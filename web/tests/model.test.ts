import assert from "node:assert/strict";
import test from "node:test";
import {contrasts, display, heatmap, params, plotNumber} from "../src/model.ts";
import type {Configuration} from "../src/types.ts";

const exact = "0.33333333333333333333333333333333333";
const row = (interval_ms: number, duration_ms: number, consensus: string|null): Configuration => ({
  scenario: "isolated", interval_ms, duration_ms, phase_percent: 0,
  streams: [], broker: {coverage: "1", consensus_coverage: consensus, consensus_points: 1, pairwise_points: 0, decisions: 44},
});

test("uses exact wire values for cells and leaves unavailable support empty", () => {
  const result = heatmap([{ordinal: 9, data: row(100, 25, exact)},{ordinal: 12, data: row(250, 50, null)}], "", "consensus");
  assert.equal(result.cells[0][0].value, exact);
  assert.equal(result.cells[0][0].ordinal, 9);
  assert.match(result.cells[0][0].text, /support 44/);
  assert.equal(result.cells[0][1].ordinal, null);
  assert.equal(result.cells[1][1].value, null);
  assert.equal(display(null, "no_support"), "Unavailable (no_support)");
  assert.equal(plotNumber(null), null);
  assert.equal(typeof plotNumber(exact), "number");
});

test("heatmap refuses incompatible overlapping cells", () => {
  assert.throws(() => heatmap([{ordinal: 1, data: row(100,25,"0")},{ordinal: 2, data: row(100,25,"1")}], "", "coverage"), /exact scenario/);
});

test("exports have stable parameters and presentation reads upstream contrasts", () => {
  assert.equal(params({scenario:"short-spike", interval_ms:100, phase_percent:0, unused:""}), "interval_ms=100&phase_percent=0&scenario=short-spike");
  assert.deepEqual(contrasts.map(item => item.key), [
    "duration_to_duration", "snapshot_vs_duration_weighting", "original_cross_estimand",
  ]);
  assert.equal(display("9007199254740993"), "9007199254740993");
});
