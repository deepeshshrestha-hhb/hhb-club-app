// Live countdown for every .ad-countdown[data-start] on the page (the
// /annual-dinner hero and the Dashboard banner). Shared so both stay in sync.
(function () {
    'use strict';
    var boxes = document.querySelectorAll('.ad-countdown[data-start]');
    if (!boxes.length) return;

    function pad(n) { return n < 10 ? '0' + n : String(n); }

    function tick() {
        boxes.forEach(function (box) {
            var ms = new Date(box.getAttribute('data-start')).getTime() - Date.now();
            if (ms <= 0) {
                box.classList.add('d-none');
                var done = document.getElementById(box.id + 'Done');
                if (done) done.classList.remove('d-none');
                return;
            }
            var s = Math.floor(ms / 1000);
            var parts = { d: Math.floor(s / 86400), h: Math.floor(s / 3600) % 24, m: Math.floor(s / 60) % 60, s: s % 60 };
            box.querySelectorAll('[data-unit]').forEach(function (el) {
                var u = el.getAttribute('data-unit');
                el.textContent = u === 'd' ? parts.d : pad(parts[u]);
            });
        });
    }
    tick();
    setInterval(tick, 1000);
})();
