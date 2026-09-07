// Weekly Score Upload page: live-ish score entry + results table.
(function () {
    var STATE_URL = '/weekly-scores/api/state';
    var POLL_MS = 10000;

    var state = window.WEEKLY_SCORE_STATE || { status: 'none', date: null, matches: [], players: [] };

    function populateScoreSelect(select) {
        if (select.options.length) return; // already built
        var placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '—';
        placeholder.disabled = true;
        placeholder.selected = true;
        select.appendChild(placeholder);
        for (var i = 1; i <= 30; i++) {
            var opt = document.createElement('option');
            opt.value = i;
            opt.textContent = i;
            select.appendChild(opt);
        }
    }

    function populatePlayerSelect(select, players) {
        var current = select.value;
        select.innerHTML = '';
        var placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select player…';
        placeholder.disabled = true;
        placeholder.selected = !current;
        select.appendChild(placeholder);
        players.forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        });
        if (current && players.indexOf(current) !== -1) {
            select.value = current;
        }
    }

    function refreshFormOptions() {
        document.querySelectorAll('.score-select').forEach(populateScoreSelect);
        document.querySelectorAll('.player-select').forEach(function (sel) {
            populatePlayerSelect(sel, state.players || []);
        });
    }

    function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
    }

    function renderTable() {
        var body = document.getElementById('matchesBody');
        var noMsg = document.getElementById('noMatchesMsg');
        var actionsHead = document.getElementById('actionsHead');
        var canEdit = state.status === 'open';
        actionsHead.hidden = !canEdit;

        var matches = state.matches || [];
        if (!matches.length) {
            body.innerHTML = '';
            noMsg.hidden = false;
            return;
        }
        noMsg.hidden = true;

        body.innerHTML = matches.map(function (m) {
            var rowClass = m.is_duplicate ? 'duplicate-row' : '';
            var actions = canEdit
                ? '<td class="text-center text-nowrap">' +
                  '<button class="btn btn-outline-secondary btn-sm me-1" data-amend="' + m.id + '">Amend</button>' +
                  '<button class="btn btn-outline-danger btn-sm" data-delete="' + m.id + '">Delete</button>' +
                  '</td>'
                : '';
            return '<tr class="' + rowClass + '" data-match-id="' + m.id + '">' +
                '<td>' + escapeHtml(m.p1) + '</td>' +
                '<td>' + escapeHtml(m.p2) + '</td>' +
                '<td class="text-center fw-semibold">' + m.score1 + '</td>' +
                '<td>' + escapeHtml(m.p3) + '</td>' +
                '<td>' + escapeHtml(m.p4) + '</td>' +
                '<td class="text-center fw-semibold">' + m.score2 + '</td>' +
                actions +
                '</tr>';
        }).join('');
    }

    function applyStatusVisibility() {
        document.getElementById('noSessionMsg').hidden = state.status !== 'none';
        document.getElementById('scoreFormCard').hidden = state.status !== 'open';
        var label = document.getElementById('sessionDateLabel');
        label.textContent = state.date ? ('— ' + state.date) : '';
    }

    function render() {
        applyStatusVisibility();
        refreshFormOptions();
        renderTable();
    }

    function fetchState() {
        fetch(STATE_URL)
            .then(function (r) { return r.json(); })
            .then(function (d) { state = d; render(); })
            .catch(function () { /* transient network error - keep last known state */ });
    }

    function showError(el, msg) {
        el.textContent = msg;
        el.hidden = !msg;
    }

    function formToFields(form) {
        var fd = new FormData(form);
        return {
            p1: fd.get('p1'), p2: fd.get('p2'), score1: fd.get('score1'),
            p3: fd.get('p3'), p4: fd.get('p4'), score2: fd.get('score2'),
        };
    }

    function clearForm(form) {
        // Not form.reset(): the placeholder <option> is disabled, so native
        // reset() lands each <select> on the first real (enabled) option
        // instead of clearing it - explicitly blank every select instead.
        form.querySelectorAll('select').forEach(function (sel) { sel.value = ''; });
    }

    // --- Add score ---
    var scoreForm = document.getElementById('scoreForm');
    if (scoreForm) {
        scoreForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var errEl = document.getElementById('formError');
            showError(errEl, '');
            fetch('/weekly-scores/api/matches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formToFields(scoreForm)),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, body: d }; }); })
                .then(function (res) {
                    if (!res.ok || !res.body.ok) {
                        showError(errEl, res.body.error || 'Could not submit that score.');
                        return;
                    }
                    state = res.body;
                    render();
                    clearForm(scoreForm);
                })
                .catch(function () { showError(errEl, 'Network error - please try again.'); });
        });
    }

    // --- Amend / Delete (event delegation on the table) ---
    var amendModalEl = document.getElementById('amendModal');
    var amendForm = document.getElementById('amendForm');

    function getAmendModal() {
        // Created lazily (not at load time) so a slow/blocked Bootstrap JS
        // load can't throw here and abort the rest of this script.
        if (!amendModalEl || typeof bootstrap === 'undefined') return null;
        return bootstrap.Modal.getOrCreateInstance(amendModalEl);
    }

    document.getElementById('matchesBody').addEventListener('click', function (e) {
        var amendBtn = e.target.closest('[data-amend]');
        var deleteBtn = e.target.closest('[data-delete]');

        if (amendBtn) {
            var id = amendBtn.dataset.amend;
            var match = (state.matches || []).find(function (m) { return m.id === id; });
            if (!match) return;
            populatePlayerSelect(amendForm.querySelector('[name="p1"]'), state.players || []);
            populatePlayerSelect(amendForm.querySelector('[name="p2"]'), state.players || []);
            populatePlayerSelect(amendForm.querySelector('[name="p3"]'), state.players || []);
            populatePlayerSelect(amendForm.querySelector('[name="p4"]'), state.players || []);
            populateScoreSelect(amendForm.querySelector('[name="score1"]'));
            populateScoreSelect(amendForm.querySelector('[name="score2"]'));
            amendForm.querySelector('[name="id"]').value = match.id;
            amendForm.querySelector('[name="p1"]').value = match.p1;
            amendForm.querySelector('[name="p2"]').value = match.p2;
            amendForm.querySelector('[name="score1"]').value = match.score1;
            amendForm.querySelector('[name="p3"]').value = match.p3;
            amendForm.querySelector('[name="p4"]').value = match.p4;
            amendForm.querySelector('[name="score2"]').value = match.score2;
            showError(document.getElementById('amendError'), '');
            var modal = getAmendModal();
            if (modal) modal.show();
        }

        if (deleteBtn) {
            if (!confirm('Delete this score?')) return;
            fetch('/weekly-scores/api/matches/' + deleteBtn.dataset.delete + '/delete', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d.ok) { state = d; render(); }
                    else { alert(d.error || 'Could not delete that row.'); }
                });
        }
    });

    var amendSaveBtn = document.getElementById('amendSaveBtn');
    if (amendSaveBtn) {
        amendSaveBtn.addEventListener('click', function () {
            var errEl = document.getElementById('amendError');
            showError(errEl, '');
            var id = amendForm.querySelector('[name="id"]').value;
            fetch('/weekly-scores/api/matches/' + id + '/amend', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formToFields(amendForm)),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, body: d }; }); })
                .then(function (res) {
                    if (!res.ok || !res.body.ok) {
                        showError(errEl, res.body.error || 'Could not save that change.');
                        return;
                    }
                    state = res.body;
                    render();
                    var modal = getAmendModal();
                    if (modal) modal.hide();
                })
                .catch(function () { showError(errEl, 'Network error - please try again.'); });
        });
    }

    render();
    setInterval(fetchState, POLL_MS);
})();
