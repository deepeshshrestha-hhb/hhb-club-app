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

    function populateCourtSelect(select) {
        if (select.options.length) return; // already built
        var placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '—';
        placeholder.disabled = true;
        placeholder.selected = true;
        select.appendChild(placeholder);
        for (var i = 1; i <= 4; i++) {
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
        document.querySelectorAll('.court-select').forEach(populateCourtSelect);
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
            // Always show the winning team first, whichever slot (Team 1/2)
            // it was actually entered into - scores can never be equal, so
            // there's always a clear winner to lead with.
            var team1Won = m.score1 > m.score2;
            var winTeam = team1Won ? [m.p1, m.p2] : [m.p3, m.p4];
            var winScore = team1Won ? m.score1 : m.score2;
            var loseTeam = team1Won ? [m.p3, m.p4] : [m.p1, m.p2];
            var loseScore = team1Won ? m.score2 : m.score1;
            var actions = canEdit
                ? '<td class="text-center text-nowrap">' +
                  '<div class="d-flex flex-column gap-1">' +
                  '<button class="btn btn-outline-secondary btn-sm scores-btn-compact" data-amend="' + m.id + '">Edit</button>' +
                  '<button class="btn btn-outline-danger btn-sm scores-btn-compact" data-delete="' + m.id + '">Del</button>' +
                  '</div></td>'
                : '';
            return '<tr class="' + rowClass + '" data-match-id="' + m.id + '">' +
                '<td class="text-center">' + escapeHtml(m.court_no) + '</td>' +
                '<td>' + escapeHtml(winTeam.join(' / ')) + '</td>' +
                '<td class="text-center fw-bold text-success">' + winScore + '</td>' +
                '<td>' + escapeHtml(loseTeam.join(' / ')) + '</td>' +
                '<td class="text-center text-muted">' + loseScore + '</td>' +
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
        // Rebuilding the player <select> options above can change whether the
        // form still counts as fully filled in (e.g. a poll refresh dropped
        // someone from the attendance list) - re-check the submit gate.
        if (updateScoreGate) updateScoreGate();
        if (updateAmendGate) updateAmendGate();
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

    function showToast(message) {
        var toastEl = document.getElementById('scoreToast');
        // Created lazily (not at load time) so a slow/blocked Bootstrap JS
        // load can't throw here and abort the rest of this script.
        if (!toastEl || typeof bootstrap === 'undefined') return;
        document.getElementById('scoreToastBody').textContent = message;
        bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 3000 }).show();
    }

    function duplicatePlayers(form) {
        var names = ['p1', 'p2', 'p3', 'p4']
            .map(function (n) { return form.querySelector('[name="' + n + '"]').value; })
            .filter(function (v) { return v; });
        return new Set(names).size !== names.length;
    }

    function formToFields(form) {
        var fd = new FormData(form);
        return {
            court_no: fd.get('court_no'),
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

    // Court No. + all four players + both scores are all `required` selects,
    // so the browser's own validity check already tells us whether every
    // field has a real (non-placeholder) value picked. On top of that, the
    // four players must be four *different* people - a player can't be in
    // both teams. Keeps the submit/save button disabled until both hold, and
    // explains why via msgEl when the fields are filled in but a player was
    // picked twice (the case that's otherwise easy to miss).
    function wireSubmitGate(form, button, msgEl) {
        if (!form || !button) return;
        function update() {
            var complete = form.checkValidity();
            var duplicate = complete && duplicatePlayers(form);
            button.disabled = !complete || duplicate;
            if (msgEl) {
                showError(msgEl, duplicate ? "The same player can't be in both teams." : '');
            }
        }
        form.addEventListener('change', update);
        form.addEventListener('input', update);
        update();
        return update;
    }

    // --- Add score ---
    var scoreForm = document.getElementById('scoreForm');
    var scoreSubmitBtn = scoreForm ? scoreForm.querySelector('button[type="submit"]') : null;
    var updateScoreGate = wireSubmitGate(scoreForm, scoreSubmitBtn, document.getElementById('formValidationMsg'));
    if (scoreForm) {
        scoreForm.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!scoreForm.checkValidity() || duplicatePlayers(scoreForm)) return; // belt-and-braces; button should already be disabled
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
                    updateScoreGate();
                    showToast('✅ Score submitted.');
                })
                .catch(function () { showError(errEl, 'Network error - please try again.'); });
        });
    }

    // --- Amend / Delete (event delegation on the table) ---
    var amendModalEl = document.getElementById('amendModal');
    var amendForm = document.getElementById('amendForm');
    var amendSaveBtn = document.getElementById('amendSaveBtn');
    var updateAmendGate = wireSubmitGate(amendForm, amendSaveBtn, document.getElementById('amendValidationMsg'));

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
            // The live attendance-driven player list can have moved on since
            // this match was submitted (someone dropped out, list refreshed,
            // etc.) - make sure this match's own four players are always
            // selectable options, or setting .value below silently fails to
            // select anything and the field looks blank.
            var amendPlayers = (state.players || []).slice();
            [match.p1, match.p2, match.p3, match.p4].forEach(function (p) {
                if (p && amendPlayers.indexOf(p) === -1) amendPlayers.push(p);
            });
            amendPlayers.sort(function (a, b) { return a.localeCompare(b); });
            populatePlayerSelect(amendForm.querySelector('[name="p1"]'), amendPlayers);
            populatePlayerSelect(amendForm.querySelector('[name="p2"]'), amendPlayers);
            populatePlayerSelect(amendForm.querySelector('[name="p3"]'), amendPlayers);
            populatePlayerSelect(amendForm.querySelector('[name="p4"]'), amendPlayers);
            populateScoreSelect(amendForm.querySelector('[name="score1"]'));
            populateScoreSelect(amendForm.querySelector('[name="score2"]'));
            populateCourtSelect(amendForm.querySelector('[name="court_no"]'));
            amendForm.querySelector('[name="id"]').value = match.id;
            amendForm.querySelector('[name="court_no"]').value = match.court_no;
            amendForm.querySelector('[name="p1"]').value = match.p1;
            amendForm.querySelector('[name="p2"]').value = match.p2;
            amendForm.querySelector('[name="score1"]').value = match.score1;
            amendForm.querySelector('[name="p3"]').value = match.p3;
            amendForm.querySelector('[name="p4"]').value = match.p4;
            amendForm.querySelector('[name="score2"]').value = match.score2;
            updateAmendGate(); // setting .value directly doesn't fire 'change'
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
                    showToast('✅ Score updated.');
                })
                .catch(function () { showError(errEl, 'Network error - please try again.'); });
        });
    }

    render();
    setInterval(fetchState, POLL_MS);
})();
