// November Group Holiday 2026 - availability form, live totals and table.
// All rendering is client-side from window.HOLIDAY.state so a save can refresh
// the cards/table in place without a page reload (keeps scroll position).
(function () {
    'use strict';

    var cfg = window.HOLIDAY;
    var state = cfg.state;
    var weekends = cfg.weekends;

    var form = document.getElementById('holidayForm');
    var familySelect = document.getElementById('familySelect');
    var submitBtn = document.getElementById('submitBtn');
    var noteInput = document.getElementById('noteInput');
    var lastUpdated = document.getElementById('lastUpdated');
    var formError = document.getElementById('formError');
    var saving = false;

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

    // ---- Totals cards ---------------------------------------------------
    function renderCards() {
        var min = state.min_people;
        var html = state.totals.map(function (t) {
            var pct = Math.min(100, Math.round(t.people / min * 100));
            var status = t.min_reached
                ? '<span class="badge text-bg-success">Minimum reached ✓</span>'
                : '<span class="badge text-bg-warning">Not enough yet (need ' + t.need + ' more)</span>';
            var lead = '';
            if (t.leading) lead = '<span class="badge text-bg-primary">🏆 Currently leading</span>';
            else if (t.tied) lead = '<span class="badge text-bg-info">Tied for the lead</span>';
            return '<div class="col-12 col-md-6">' +
                '<div class="card wk-card h-100 ' + (t.leading ? 'leading' : '') + '">' +
                '<div class="card-body">' +
                '<div class="d-flex justify-content-between align-items-start gap-2 mb-1">' +
                '<div><div class="fw-bold">' + esc(t.name) + '</div>' +
                '<div class="text-muted small">' + esc(t.dates) + '</div>' +
                (t.label ? '<span class="badge text-bg-light border mt-1">' + esc(t.label) + '</span>' : '') +
                '</div>' + lead + '</div>' +
                '<div class="d-flex align-items-baseline gap-2 my-2">' +
                '<span class="wk-count">' + t.people + '</span>' +
                '<span class="text-muted">/ ' + min + ' minimum</span></div>' +
                '<div class="progress mb-2" role="progressbar" aria-valuenow="' + t.people + '" aria-valuemin="0" aria-valuemax="' + min + '">' +
                '<div class="progress-bar ' + (t.min_reached ? 'bg-success' : '') + '" style="width:' + pct + '%"></div></div>' +
                '<div class="d-flex justify-content-between align-items-center flex-wrap gap-1">' +
                '<span class="small text-muted">' + plural(t.families, 'family', 'families') + ' attending</span>' +
                status + '</div>' +
                '</div></div></div>';
        }).join('');
        document.getElementById('totalsCards').innerHTML = html;
        document.getElementById('respondedCount').textContent =
            state.responded + ' of ' + state.family_count + ' families have responded';
    }

    // ---- Responses table ------------------------------------------------
    function cell(r, key) {
        if (!r) return '<span class="awaiting">Awaiting response</span>';
        if (r[key + '_available'] === 'yes')
            return '<span class="text-success fw-semibold">✓ ' + plural(r[key + '_people'], 'person', 'people') + '</span>';
        return '<span class="text-muted">✗ Can\'t make it</span>';
    }

    function renderTable() {
        document.getElementById('holidayRows').innerHTML = state.rows.map(function (row) {
            var r = row.response;
            return '<tr><td class="fw-semibold">' + esc(row.family.replace(/ and family$/, '')) + '</td>' +
                weekends.map(function (wk) { return '<td>' + cell(r, wk.key) + '</td>'; }).join('') +
                '<td class="note-cell">' + (r && r.note ? esc(r.note) : '') + '</td>' +
                '<td class="small text-muted">' + (r ? esc(r.updated_display) : '') + '</td></tr>';
        }).join('');
        document.getElementById('holidayTotalsRow').innerHTML = '<td>Total</td>' +
            state.totals.map(function (t) {
                return '<td>' + plural(t.people, 'person', 'people') + ' · ' + plural(t.families, 'family', 'families') + '</td>';
            }).join('') + '<td></td><td></td>';
    }

    function renderAll() { renderCards(); renderTable(); }

    // ---- Form -----------------------------------------------------------
    function radio(key, val) { return document.getElementById(key + (val === 'yes' ? 'Yes' : 'No')); }
    function peopleInput(key) { return document.getElementById(key + 'People'); }
    function chosen(key) {
        var el = form.querySelector('input[name="' + key + '_available"]:checked');
        return el ? el.value : null;
    }

    function syncPeopleEnabled() {
        weekends.forEach(function (wk) {
            var inp = peopleInput(wk.key);
            var yes = chosen(wk.key) === 'yes';
            inp.disabled = !yes;
            inp.required = yes;
            if (!yes) inp.value = '';
        });
    }

    function isValid() {
        if (!familySelect.value) return false;
        return weekends.every(function (wk) {
            var c = chosen(wk.key);
            if (!c) return false;
            if (c === 'no') return true;
            var n = parseInt(peopleInput(wk.key).value, 10);
            return n >= 1 && n <= cfg.maxPeople;
        });
    }

    function updateSubmitState() { submitBtn.disabled = saving || !isValid(); }

    function findResponse(family) {
        for (var i = 0; i < state.rows.length; i++)
            if (state.rows[i].family === family) return state.rows[i].response;
        return null;
    }

    function loadFamily() {
        formError.classList.add('d-none');
        var r = findResponse(familySelect.value);
        weekends.forEach(function (wk) {
            radio(wk.key, 'yes').checked = !!(r && r[wk.key + '_available'] === 'yes');
            radio(wk.key, 'no').checked = !!(r && r[wk.key + '_available'] === 'no');
        });
        syncPeopleEnabled();
        weekends.forEach(function (wk) {
            if (r && r[wk.key + '_available'] === 'yes') peopleInput(wk.key).value = r[wk.key + '_people'];
        });
        noteInput.value = r ? (r.note || '') : '';
        lastUpdated.textContent = r ? 'Last updated ' + r.updated_display : '';
        submitBtn.textContent = r ? 'Update my response' : 'Submit';
        updateSubmitState();
    }

    familySelect.addEventListener('change', loadFamily);
    form.addEventListener('change', function (e) {
        if (e.target.type === 'radio') {
            syncPeopleEnabled();
            var key = e.target.name.replace('_available', '');
            if (e.target.value === 'yes') peopleInput(key).focus();
        }
        updateSubmitState();
    });
    form.addEventListener('input', updateSubmitState);

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!isValid() || saving) return;
        saving = true;
        updateSubmitState();
        formError.classList.add('d-none');

        var payload = { family: familySelect.value, note: noteInput.value };
        weekends.forEach(function (wk) {
            payload[wk.key + '_available'] = chosen(wk.key);
            payload[wk.key + '_people'] = peopleInput(wk.key).value || 0;
        });
        var wasUpdate = !!findResponse(familySelect.value);

        fetch(cfg.apiBase + '/api/respond', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
            .then(function (r) {
                if (!r.ok || !r.body.ok) throw new Error((r.body && r.body.error) || 'Could not save - please try again.');
                state = r.body.state;
                renderAll();
                loadFamily();
                document.getElementById('holidayToastBody').textContent =
                    wasUpdate ? 'Response updated — thank you!' : 'Response saved — thank you!';
                bootstrap.Toast.getOrCreateInstance(document.getElementById('holidayToast')).show();
            })
            .catch(function (err) {
                formError.textContent = err.message || 'Could not save - please try again.';
                formError.classList.remove('d-none');
            })
            .finally(function () { saving = false; updateSubmitState(); });
    });

    // Pick up other families' answers while the page stays open.
    setInterval(function () {
        if (saving || document.hidden) return;
        fetch(cfg.apiBase + '/api/state')
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (s) { if (s) { state = s; renderAll(); } })
            .catch(function () {});
    }, 30000);

    // Collapse caret
    var collapseEl = document.getElementById('strategyCollapse');
    var toggleBtn = document.querySelector('[data-bs-target="#strategyCollapse"]');
    collapseEl.addEventListener('show.bs.collapse', function () { toggleBtn.textContent = toggleBtn.textContent.replace('▸', '▾'); });
    collapseEl.addEventListener('hide.bs.collapse', function () { toggleBtn.textContent = toggleBtn.textContent.replace('▾', '▸'); });

    renderAll();
    loadFamily();
})();
