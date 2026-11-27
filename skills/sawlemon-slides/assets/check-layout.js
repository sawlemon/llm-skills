// Paste into tab.playwright.evaluate(<this function>) on deck.html?still (viewport 1920x1080).
// Walks every slide and every build step; returns elements that spill into the footer or off the right edge.
async () => {
  const out = [], sc = document.querySelector('.stage').getBoundingClientRect().width / 1920;
  const slides = [...document.querySelectorAll('.slide')];
  for (let n = 0; n < slides.length; n++) {
    const steps = +slides[n].dataset.steps || 1;
    for (let k = 1; k <= steps; k++) {
      location.hash = `${n + 1}.${k}`;
      await new Promise(r => setTimeout(r, 30));
      const s = slides[n], sr = s.getBoundingClientRect();
      s.querySelectorAll('*').forEach(el => {
        const r = el.getBoundingClientRect();
        if (!r.width || getComputedStyle(el).opacity === '0') return;
        const bottom = (r.bottom - sr.top) / sc, right = (r.right - sr.left) / sc, top = (r.top - sr.top) / sc;
        if (bottom > 975 || right > 1910 || top < 20) out.push(`${n + 1}.${k} ${el.tagName} ${el.className?.baseVal ?? el.className}`);
      });
      s.querySelectorAll('.beat,.card,.step,.punch,.chip').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 2) out.push(`${n + 1}.${k} text overflows ${el.className}`);
      });
    }
  }
  location.hash = '1';
  return out;
}
