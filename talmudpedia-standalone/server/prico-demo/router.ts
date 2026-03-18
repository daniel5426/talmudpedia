import express from "express";

import {
  type ClientActivitySummaryRequest,
  type ConcentrationRequest,
  type DealScopedRequest,
  PricoToolError,
} from "./contracts.js";
import {
  getBankConcentration,
  getClientActivitySummary,
  getCurrencyConcentration,
  getDealExplainer,
  getMarketContext,
} from "./service.js";

function handleError(res: express.Response, error: unknown) {
  if (error instanceof PricoToolError) {
    res.status(error.status).json({
      error: error.message,
      code: error.code,
    });
    return;
  }

  const message = error instanceof Error ? error.message : "Unexpected PRICO demo server error.";
  res.status(500).json({
    error: message,
    code: "INTERNAL_ERROR",
  });
}

export function createPricoDemoRouter() {
  const router = express.Router();

  router.post("/client-activity-summary", async (req, res) => {
    try {
      const payload = req.body as ClientActivitySummaryRequest;
      res.json(await getClientActivitySummary(payload));
    } catch (error) {
      handleError(res, error);
    }
  });

  router.post("/bank-concentration", async (req, res) => {
    try {
      const payload = req.body as ConcentrationRequest;
      res.json(await getBankConcentration(payload));
    } catch (error) {
      handleError(res, error);
    }
  });

  router.post("/currency-concentration", async (req, res) => {
    try {
      const payload = req.body as ConcentrationRequest;
      res.json(await getCurrencyConcentration(payload));
    } catch (error) {
      handleError(res, error);
    }
  });

  router.post("/deal-explainer", async (req, res) => {
    try {
      const payload = req.body as DealScopedRequest;
      res.json(await getDealExplainer(payload));
    } catch (error) {
      handleError(res, error);
    }
  });

  router.post("/market-context", async (req, res) => {
    try {
      const payload = req.body as DealScopedRequest;
      res.json(await getMarketContext(payload));
    } catch (error) {
      handleError(res, error);
    }
  });

  return router;
}
