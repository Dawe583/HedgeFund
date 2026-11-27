import type { Formats } from "./dividendQuestion";
import { locale, money } from "./money";

// A day in a sentence: the long form, which no reader takes for another day.
const longDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" });

const perShare = new Intl.NumberFormat(locale, { maximumFractionDigits: 6 });

export const BANNER_FORMATS: Formats = {
  date: longDate,
  money: (amount, currency) => money(currency, "cents").format(amount),
  perShare: (amount, currency) => `${perShare.format(amount)} ${currency}`,
};
