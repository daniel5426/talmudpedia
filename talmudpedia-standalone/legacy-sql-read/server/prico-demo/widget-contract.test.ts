import test from "node:test";
import assert from "node:assert/strict";

import { validatePricoWidgetBundle } from "../../../src/features/prico-widgets/contract.js";

test("validatePricoWidgetBundle accepts a multi-row JSON bundle", () => {
  const parsed = validatePricoWidgetBundle({
    title: "Client Activity",
    subtitle: "Last 30 days",
    rows: [
      {
        widgets: [
          { kind: "kpi", id: "deals", span: 3, title: "Deals", value: "24" },
          { kind: "kpi", id: "volume", span: 3, title: "Volume", value: "$12.4M" },
          { kind: "kpi", id: "bank", span: 3, title: "Top Bank", value: "Hapoalim" },
          { kind: "kpi", id: "currency", span: 3, title: "Top Currency", value: "USD" },
        ],
      },
      {
        widgets: [
          {
            kind: "pie",
            id: "banks",
            span: 6,
            title: "Bank Concentration",
            data: [
              { label: "Hapoalim", value: 45 },
              { label: "Discount", value: 30 },
            ],
          },
          {
            kind: "bar",
            id: "currencies",
            span: 6,
            title: "Currency Concentration",
            data: [
              { label: "USD", value: 60 },
              { label: "EUR", value: 25 },
            ],
          },
        ],
      },
      {
        widgets: [
          {
            kind: "table",
            id: "recent",
            span: 12,
            title: "Recent Deals",
            columns: ["deal", "date", "bank"],
            rows: [
              ["1", "2026-03-10", "Hapoalim"],
              ["2", "2026-03-09", "Discount"],
            ],
          },
        ],
      },
    ],
  });

  assert.equal(parsed.ok, true);
  if (!parsed.ok) return;
  assert.equal(parsed.bundle.rows.length, 3);
  assert.equal(parsed.bundle.rows[0].widgets.length, 4);
});

test("validatePricoWidgetBundle rejects row span overflow", () => {
  const parsed = validatePricoWidgetBundle({
    rows: [
      {
        widgets: [
          { kind: "kpi", id: "a", span: 6, title: "A", value: "1" },
          { kind: "kpi", id: "b", span: 6, title: "B", value: "2" },
          { kind: "kpi", id: "c", span: 3, title: "C", value: "3" },
        ],
      },
    ],
  });

  assert.equal(parsed.ok, false);
  if (parsed.ok) return;
  assert.match(parsed.error, /Row span exceeds 12/);
});

test("validatePricoWidgetBundle rejects duplicate widget ids", () => {
  const parsed = validatePricoWidgetBundle({
    rows: [
      {
        widgets: [
          { kind: "pie", id: "banks", span: 6, title: "Bank concentration", data: [{ label: "A", value: 60 }] },
          { kind: "table", id: "banks", span: 6, title: "Bank detail", columns: ["bank"], rows: [["A"]] },
        ],
      },
    ],
  });

  assert.equal(parsed.ok, false);
  if (parsed.ok) return;
  assert.match(parsed.error, /Duplicate widget id/);
});

test("validatePricoWidgetBundle rejects invalid compare widgets", () => {
  const parsed = validatePricoWidgetBundle({
    rows: [
      {
        widgets: [
          {
            kind: "compare",
            id: "banks",
            span: 12,
            title: "Bank Deal Count",
            leftLabel: "A",
            rightLabel: "B",
            rightValue: 1,
          },
        ],
      },
    ],
  });

  assert.equal(parsed.ok, false);
  if (parsed.ok) return;
  assert.match(parsed.error, /leftValue/i);
});

test("validatePricoWidgetBundle rejects table rows with mismatched cells", () => {
  const parsed = validatePricoWidgetBundle({
    rows: [
      {
        widgets: [
          {
            kind: "table",
            id: "recent",
            span: 12,
            title: "Recent Deals",
            columns: ["deal", "date", "bank"],
            rows: [["1", "2026-03-10"]],
          },
        ],
      },
    ],
  });

  assert.equal(parsed.ok, false);
  if (parsed.ok) return;
  assert.match(parsed.error, /Table row 1 has 2 cells but expected 3/);
});
