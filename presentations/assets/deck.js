// Shared slide navigation. Arrow keys / space / click to advance.
(function () {
  const slides = [...document.querySelectorAll('.slide')];
  let i = 0;
  function show(n) {
    i = Math.max(0, Math.min(slides.length - 1, n));
    slides.forEach((s, k) => s.classList.toggle('active', k === i));
    const p = document.getElementById('progress');
    if (p) p.style.width = ((i + 1) / slides.length * 100) + '%';
    const c = document.getElementById('counter');
    if (c) c.textContent = (i + 1) + ' / ' + slides.length;
  }
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); show(i + 1); }
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); show(i - 1); }
    if (e.key === 'Home') show(0);
    if (e.key === 'End') show(slides.length - 1);
  });
  document.addEventListener('click', e => { if (!e.target.closest('a')) show(i + 1); });
  show(0);
})();
