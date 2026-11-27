(() => {
  const slides = [...document.querySelectorAll('.slide')];
  const steps = slides.map(s => parseInt(s.dataset.steps, 10) || 1);
  const counter = document.querySelector('.counter');
  const pad = n => String(n).padStart(2, '0');
  let i = 0, k = 1;

  if (location.search.includes('still')) document.documentElement.classList.add('still');

  // Step dots for slides that build up in several steps.
  slides.forEach((s, n) => {
    if (steps[n] > 1) s.insertAdjacentHTML('beforeend', '<div class="stepdots">' + '<i></i>'.repeat(steps[n]) + '</div>');
  });

  function fit() {
    document.documentElement.style.setProperty('--s', Math.min(innerWidth / 1920, innerHeight / 1080));
  }

  // Elements with data-show="a" (and optional data-hide="b") get .on while a <= step < b.
  function render() {
    slides.forEach((s, n) => s.classList.toggle('active', n === i));
    const s = slides[i];
    s.dataset.cur = k;
    s.querySelectorAll('[data-show]').forEach(el => {
      const a = +el.dataset.show, b = el.dataset.hide ? +el.dataset.hide : Infinity;
      el.classList.toggle('on', k >= a && k < b);
    });
    s.querySelectorAll('.stepdots i').forEach((d, n) => d.classList.toggle('on', n < k));
    counter.textContent = pad(i + 1) + ' / ' + pad(slides.length);
    history.replaceState(null, '', '#' + (i + 1) + (steps[i] > 1 ? '.' + k : ''));
  }

  function go(n, step = 1) {
    i = Math.max(0, Math.min(slides.length - 1, n));
    k = Math.max(1, Math.min(steps[i], step));
    render();
  }
  const next = () => k < steps[i] ? go(i, k + 1) : i < slides.length - 1 && go(i + 1, 1);
  const prev = () => k > 1 ? go(i, k - 1) : i > 0 && go(i - 1, steps[i - 1]);

  const fromHash = () => {
    const [a, b] = location.hash.slice(1).split('.');
    go((parseInt(a, 10) || 1) - 1, parseInt(b, 10) || 1);
  };

  addEventListener('resize', fit);
  addEventListener('hashchange', fromHash);
  addEventListener('click', e => e.clientX > innerWidth / 2 ? next() : prev());
  addEventListener('keydown', e => {
    if (['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter'].includes(e.key)) { e.preventDefault(); next(); }
    else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].includes(e.key)) { e.preventDefault(); prev(); }
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(slides.length - 1, 99);
    else if (e.key === 'f') document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
  });

  fit();
  fromHash();
})();
