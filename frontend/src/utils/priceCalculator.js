// Estimated cost for a booking slot: energy delivered = power * hours * 0.5
// (assumes an average 50% of rated power over the session).
// This is only a UI estimate. The backend's booking_amount is the real price.
export function estimateCost(charger, hours = 1) {
  if (!charger) return 0;
  const kwh = charger.power_kw * hours * 0.5;
  return Math.round(kwh * charger.price_per_kwh);
}

export const formatINR = (n) => `₹${Number(n).toLocaleString('en-IN')}`;
