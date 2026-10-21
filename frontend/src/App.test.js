import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import App from './App';

global.IS_REACT_ACT_ENVIRONMENT = true;

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function renderAt(path) {
  window.history.pushState({}, '', path);
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<App />); });
  // let API calls fail -> demo fallback -> state updates
  for (let i = 0; i < 10; i++) {
    await act(async () => { await wait(300); });
  }
  const html = el.innerHTML;
  await act(async () => { root.unmount(); });
  el.remove();
  return html;
}

const cases = [
  ['/', 'Book an EV charging slot'],
  ['/search?city=Chennai', 'T. Nagar Charge Point'],
  ['/stations/Bangalore/1', 'Indiranagar Fast Hub'],
  ['/book/Bangalore/1?charger=101&slot=101002', 'Book a slot'],
  ['/my-bookings', 'Indiranagar Fast Hub'],
  ['/dashboard', 'Live charger status'],
  ['/admin', 'Admin Panel'],
  ['/some/unknown/route', 'Book an EV charging slot'], // redirects home
];

describe('every route renders (no backend running)', () => {
  test.each(cases)('%s', async (path, expected) => {
    const html = await renderAt(path);
    expect(html).toContain('EV Charging Network'); // Header present => Router OK
    expect(html).toContain(expected);
  }, 20000);

  test('demo banner appears when backend is down', async () => {
    const html = await renderAt('/search?city=Delhi');
    expect(html).toContain('Backend API not reachable');
  }, 20000);
});
