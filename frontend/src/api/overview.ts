import { api } from "./client";
import type { Schemas } from "./types";

/* The consolidated fund overview (design §8, rule D13): ledger wealth — the
   trading account already inside it through the broker statement — with the
   engine's own figure beside it, never summed in, and the reconciliation
   between the two statements about the same money. */

export type OverviewFund = Schemas["OverviewFund"];
export type OverviewTradingEquity = Schemas["OverviewTradingEquity"];
export type OverviewReconciliation = Schemas["OverviewReconciliation"];

export async function getFundOverview(): Promise<OverviewFund> {
  return (await api.get<OverviewFund>("/api/overview/fund")).data;
}

export async function putTradingAccount(institutionId: number): Promise<OverviewReconciliation> {
  return (await api.put<OverviewReconciliation>("/api/overview/trading-account", { institution_id: institutionId })).data;
}
