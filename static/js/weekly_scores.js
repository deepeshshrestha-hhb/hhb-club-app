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

    // Players a given <select> should offer, kept alongside it so the search
    // combobox (see initPlayerCombobox below) can filter without re-deriving
    // the list on every keystroke - populatePlayerSelect is the one place
    // that decides what a select's options are, for both the plain rebuild
    // and the search-filtered UI layered on top of it.
    var comboboxPlayers = new WeakMap();

    function populatePlayerSelect(select, players) {
        comboboxPlayers.set(select, players);
        var current = select.value;
        // Decide up front whether `current` survives the rebuild, so exactly
        // one option ends up marked selected either way. Previously the
        // placeholder was only marked selected when `current` was empty, so
        // a *non-empty* current value that didn't exist in the new `players`
        // list left nothing explicitly selected - which browsers resolve by
        // silently selecting the first enabled (real) option instead of the
        // placeholder. That's how this select could jump to an unrelated
        // name instead of falling back to "Select player…".
        var restorable = !!current && players.indexOf(current) !== -1;
        select.innerHTML = '';
        var placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select player…';
        placeholder.disabled = true;
        placeholder.selected = !restorable;
        select.appendChild(placeholder);
        players.forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            if (restorable && name === current) opt.selected = true;
            select.appendChild(opt);
        });
    }

    function optionLabel(select) {
        var opt = select.options[select.selectedIndex];
        return opt && opt.value ? opt.textContent : '';
    }

    // Keeps a player-select's visible search-box text in sync with its
    // actual (hidden) selected value - called after anything rebuilds the
    // select's options or sets its value directly (populatePlayerSelect,
    // clearForm, amend prefill). Skipped while the box has focus so a poll
    // refresh mid-search doesn't wipe out what someone's currently typing.
    function syncComboInput(select) {
        var wrapper = select.closest('.player-combobox');
        var input = wrapper && wrapper.querySelector('.player-search-input');
        if (input && document.activeElement !== input) {
            input.value = optionLabel(select);
        }
    }

    function refreshFormOptions() {
        document.querySelectorAll('.score-select').forEach(populateScoreSelect);
        document.querySelectorAll('.court-select').forEach(populateCourtSelect);
        document.querySelectorAll('.player-select').forEach(function (sel) {
            // The 10s background poll runs this on *every* player-select on
            // the page, including ones inside an open Amend modal someone is
            // actively editing. Rebuilding with only the general attendance
            // list (state.players) would silently drop whatever's currently
            // chosen there (e.g. an older full-name value merged in just for
            // that match) and land on some unrelated name instead - always
            // keep the field's current value in its own option list across a
            // rebuild, on top of whatever the general list offers.
            var players = state.players || [];
            var current = sel.value;
            if (current && players.indexOf(current) === -1) {
                players = players.concat([current]);
            }
            populatePlayerSelect(sel, players);
            syncComboInput(sel);
        });
    }

    // Type-ahead search for a player <select>: the real select stays hidden
    // and is the single source of truth (value, `required`, FormData) so all
    // existing validation/gating code works unchanged - this just drives it
    // from a text input instead of a long native dropdown. Wired once per
    // field at page load; populatePlayerSelect rebuilding the select's
    // <option>s later doesn't need to re-wire anything here.
    function initPlayerCombobox(select) {
        var wrapper = select.closest('.player-combobox');
        var input = wrapper && wrapper.querySelector('.player-search-input');
        var menu = wrapper && wrapper.querySelector('.player-search-menu');
        if (!input || !menu) return;

        function optionEls() { return Array.prototype.slice.call(menu.querySelectorAll('[data-value]')); }
        function activeIndex() { return optionEls().findIndex(function (o) { return o.classList.contains('active-option'); }); }
        function setActive(idx) {
            optionEls().forEach(function (o, i) { o.classList.toggle('active-option', i === idx); });
            var el = optionEls()[idx];
            if (el) el.scrollIntoView({ block: 'nearest' });
        }
        function closeMenu() { menu.hidden = true; menu.innerHTML = ''; }
        function openMenu(filterText) {
            var players = comboboxPlayers.get(select) || [];
            var q = (filterText || '').trim().toLowerCase();
            var matches = q ? players.filter(function (n) { return n.toLowerCase().indexOf(q) !== -1; }) : players;
            if (!matches.length) {
                menu.innerHTML = '<div class="list-group-item text-muted small">No matches</div>';
            } else {
                menu.innerHTML = matches.map(function (n) {
                    return '<button type="button" class="list-group-item list-group-item-action" data-value="' +
                        escapeHtml(n) + '">' + escapeHtml(n) + '</button>';
                }).join('');
                setActive(0);
            }
            menu.hidden = false;
        }
        function commit(name) {
            select.value = name;
            input.value = name;
            closeMenu();
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }

        input.addEventListener('focus', function () { openMenu(''); });
        input.addEventListener('input', function () { openMenu(input.value); });
        input.addEventListener('keydown', function (e) {
            if (menu.hidden) {
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') openMenu(input.value);
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive(Math.min(activeIndex() + 1, optionEls().length - 1));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive(Math.max(activeIndex() - 1, 0));
            } else if (e.key === 'Enter') {
                e.preventDefault();
                var opts = optionEls();
                var target = opts[activeIndex()] || opts[0];
                if (target) commit(target.dataset.value);
            } else if (e.key === 'Escape') {
                closeMenu();
                input.value = optionLabel(select);
            }
        });
        menu.addEventListener('mousedown', function (e) {
            // mousedown (not click) + preventDefault so this fires before the
            // input's blur handler would otherwise close the menu first.
            var btn = e.target.closest('[data-value]');
            if (!btn) return;
            e.preventDefault();
            commit(btn.dataset.value);
        });
        input.addEventListener('blur', function () {
            setTimeout(function () {
                closeMenu();
                input.value = optionLabel(select);
            }, 150);
        });
    }

    document.querySelectorAll('.player-select').forEach(initPlayerCombobox);

    function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
    }

    // Per-court running totals above the table, so it's obvious at a glance
    // if one court is falling behind the others - the club wants roughly
    // equal matches across all 4 on a Sunday. The court(s) below the
    // busiest court are flagged (not just the single lowest), since with 4
    // courts more than one can be lagging at once.
    function renderCourtCounts(matches) {
        var el = document.getElementById('courtCounts');
        if (!el) return;
        if (!matches.length) {
            el.innerHTML = '';
            return;
        }
        var counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
        matches.forEach(function (m) {
            if (counts.hasOwnProperty(m.court_no)) counts[m.court_no]++;
        });
        var max = Math.max(counts[1], counts[2], counts[3], counts[4]);
        el.innerHTML = [1, 2, 3, 4].map(function (c) {
            var n = counts[c];
            var behind = max > 0 && n < max;
            var cls = behind ? 'bg-warning text-dark' : 'bg-secondary';
            return '<span class="badge ' + cls + '">Court ' + c + ': ' + n + '</span>';
        }).join('');
    }

    // Player filter dropdown + Total/Won/Lost badges above the table, so
    // anyone can check how many matches they've reported so far (a Sunday
    // session averages ~8 per player over 2 hours) without scanning every
    // row for their name.
    function populatePlayerFilter(players) {
        var sel = document.getElementById('playerFilter');
        if (!sel) return;
        var current = sel.value;
        sel.innerHTML = '';
        var allOpt = document.createElement('option');
        allOpt.value = '';
        allOpt.textContent = 'All players';
        sel.appendChild(allOpt);
        players.forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            sel.appendChild(opt);
        });
        // Preserve the current selection across a poll refresh, unless that
        // player has fallen off the attendance list.
        sel.value = players.indexOf(current) !== -1 ? current : '';
    }

    function computePlayerStats(matches, player) {
        var total = 0, won = 0, lost = 0;
        matches.forEach(function (m) {
            var inTeam1 = m.p1 === player || m.p2 === player;
            var inTeam2 = m.p3 === player || m.p4 === player;
            if (!inTeam1 && !inTeam2) return;
            total++;
            var team1Won = m.score1 > m.score2;
            if ((inTeam1 && team1Won) || (inTeam2 && !team1Won)) won++;
            else lost++;
        });
        return { total: total, won: won, lost: lost };
    }

    function renderTable() {
        var body = document.getElementById('matchesBody');
        var noMsg = document.getElementById('noMatchesMsg');
        var actionsHead = document.getElementById('actionsHead');
        var canEdit = state.status === 'open';
        actionsHead.hidden = !canEdit;

        var allMatches = state.matches || [];
        var countEl = document.getElementById('matchCount');
        if (countEl) countEl.textContent = allMatches.length + (allMatches.length === 1 ? ' match' : ' matches');
        renderCourtCounts(allMatches);

        // Union with everyone actually in the matches, not just the current
        // attendance list - the same reasoning as Amend always including a
        // match's own players (see the amend-open handler below): someone
        // can have real recorded matches without being in state.players
        // right now (attendance-list hiccup, a name resolved differently at
        // submit time, etc.), and they'd otherwise be impossible to filter
        // by despite having scores on the board.
        var filterPlayers = (state.players || []).slice();
        allMatches.forEach(function (m) {
            [m.p1, m.p2, m.p3, m.p4].forEach(function (p) {
                if (p && filterPlayers.indexOf(p) === -1) filterPlayers.push(p);
            });
        });
        filterPlayers.sort(function (a, b) { return a.localeCompare(b); });
        populatePlayerFilter(filterPlayers);
        var filterPlayer = document.getElementById('playerFilter').value;
        var statsEl = document.getElementById('playerFilterStats');
        var totalEl = document.getElementById('playerFilterTotal');
        var wonEl = document.getElementById('playerFilterWon');
        var lostEl = document.getElementById('playerFilterLost');
        if (filterPlayer) {
            var stats = computePlayerStats(allMatches, filterPlayer);
            totalEl.textContent = stats.total;
            wonEl.textContent = stats.won;
            lostEl.textContent = stats.lost;
            statsEl.hidden = false;
            // Bootstrap's d-flex carries !important, which beats the plain
            // [hidden]{display:none} the browser applies by default - with
            // both present at once, hidden had no visible effect and the
            // badges kept showing whichever player's numbers were computed
            // last, even after switching back to "All players". Only add
            // d-flex while actually shown, so hidden works when it's not.
            statsEl.classList.add('d-flex', 'flex-wrap');
        } else {
            statsEl.hidden = true;
            statsEl.classList.remove('d-flex', 'flex-wrap');
            totalEl.textContent = '0';
            wonEl.textContent = '0';
            lostEl.textContent = '0';
        }

        var matches = filterPlayer
            ? allMatches.filter(function (m) {
                return m.p1 === filterPlayer || m.p2 === filterPlayer || m.p3 === filterPlayer || m.p4 === filterPlayer;
            })
            : allMatches;

        if (!matches.length) {
            body.innerHTML = '';
            noMsg.hidden = false;
            noMsg.textContent = filterPlayer ? 'No matches for ' + filterPlayer + ' yet.' : 'No scores submitted yet.';
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

    // '2026-09-06' -> '06-Sep-2026' - matches the server-side display_date
    // Jinja filter used for the same date wherever it's server-rendered.
    function formatDisplayDate(isoStr) {
        if (!isoStr) return '';
        var parts = isoStr.split('-');
        if (parts.length !== 3) return isoStr;
        var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        var monthIdx = parseInt(parts[1], 10) - 1;
        if (monthIdx < 0 || monthIdx > 11) return isoStr;
        return parts[2] + '-' + months[monthIdx] + '-' + parts[0];
    }

    function applyStatusVisibility() {
        document.getElementById('noSessionMsg').hidden = state.status !== 'none';
        document.getElementById('scoreFormCard').hidden = state.status !== 'open';
        var label = document.getElementById('sessionDateLabel');
        label.textContent = state.date ? ('— ' + formatDisplayDate(state.date)) : '';
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
        form.querySelectorAll('.player-select').forEach(syncComboInput);
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
            // Disable immediately (before the request even starts) so a slow
            // response can't be mistaken for a failed submit and re-tapped -
            // that was creating the same match 4-5 times over on a slow
            // connection. updateScoreGate() in .finally() restores the right
            // state afterwards (re-disabled if the form is now empty/invalid).
            scoreSubmitBtn.disabled = true;
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
                    showToast('✅ Score submitted.');
                })
                .catch(function () { showError(errEl, 'Network error - please try again.'); })
                .finally(function () { updateScoreGate(); });
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
            amendForm.querySelectorAll('.player-select').forEach(syncComboInput);
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
                    if (d.ok) { state = d; render(); showToast('🗑️ Score deleted.'); }
                    else { alert(d.error || 'Could not delete that row.'); }
                });
        }
    });

    if (amendSaveBtn) {
        amendSaveBtn.addEventListener('click', function () {
            var errEl = document.getElementById('amendError');
            showError(errEl, '');
            var id = amendForm.querySelector('[name="id"]').value;
            // See the matching note on scoreForm's submit handler - disable
            // immediately so a slow response doesn't invite a repeat click.
            amendSaveBtn.disabled = true;
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
                .catch(function () { showError(errEl, 'Network error - please try again.'); })
                .finally(function () { updateAmendGate(); });
        });
    }

    var playerFilterSelect = document.getElementById('playerFilter');
    if (playerFilterSelect) {
        playerFilterSelect.addEventListener('change', renderTable);
    }

    render();
    setInterval(fetchState, POLL_MS);
})();
