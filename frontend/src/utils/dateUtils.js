export const formatDate = (iso) =>
  new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

export const formatTime = (iso) =>
  new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });

export const formatRange = (startIso, endIso) =>
  `${formatDate(startIso)}, ${formatTime(startIso)} – ${formatTime(endIso)}`;

export const isUpcoming = (iso) => new Date(iso).getTime() > Date.now();
