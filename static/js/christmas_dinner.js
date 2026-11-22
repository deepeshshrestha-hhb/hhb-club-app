// Christmas Dinner 2026 RSVP - headcount form, running total and replies table.
// Rendered client-side from window.XMAS_DINNER.state so a save can refresh the
// totals and table in place without a page reload (keeps scroll position).
(function () {
    'use strict';

    var cfg = window.XMAS_DINNER;
    var state = cfg.state;

    var form = document.getElementById('xmForm');
    var familySelect = document.getElementById('familySelect');
    var peopleInput = document.getElementById('peopleInput');
    var submitBtn = document.getElementById('submitBtn');
    var formError = document.getElementById('formError');
    var saving = false;

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

    function comingCell(r) {
        if (!r) return '<span class="xm-muted fst-italic">Awaiting reply</span>';
        if (r.people === 0) return '<span class="xm-muted">Can\'t make it</span>';
        return '<strong>' + r.people + '</strong>';
    }

    function render() {
        document.getElementById('totalPeople').textContent = state.total_people;
        document.getElementById('totalLabel').textContent =
            (state.total_people === 1 ? 'person' : 'people') + ' coming from ' +
            plural(state.families_coming, 'family', 'families');
        document.getElementById('respondedLabel').textContent =
            state.responded + ' of ' + state.family_count + ' families have replied';
        document.getElementById('xmRows').innerHTML = state.rows.map(function (row) {
            return '<tr><td>' + esc(row.family.replace(/ and family$/, '')) + '</td>' +
                '<td>' + comingCell(row.response) + '</td></tr>';
        }).join('');
        document.getElementById('xmTotalRow').innerHTML =
            '<td>Total</td><td>' + state.total_people + '</td>';
    }

    function findResponse(family) {
        for (var i = 0; i < state.rows.length; i++)
            if (state.rows[i].family === family) return state.rows[i].response;
        return null;
    }

    function isValid() {
        var raw = peopleInput.value.trim();
        if (!familySelect.value || !/^\d+$/.test(raw)) return false;
        return parseInt(raw, 10) <= cfg.maxPeople;
    }

    function updateSubmit() { submitBtn.disabled = saving || !isValid(); }

    // Picking a family that has already replied loads their number to edit.
    function loadFamily() {
        formError.classList.add('d-none');
        var r = findResponse(familySelect.value);
        peopleInput.value = r ? r.people : '';
        submitBtn.textContent = r ? 'Update' : 'Send';
        updateSubmit();
    }

    familySelect.addEventListener('change', loadFamily);
    peopleInput.addEventListener('input', updateSubmit);

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!isValid() || saving) return;
        saving = true;
        updateSubmit();
        formError.classList.add('d-none');
        var people = parseInt(peopleInput.value, 10);

        fetch(cfg.apiBase + '/api/respond', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ family: familySelect.value, people: people })
        })
            .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
            .then(function (r) {
                if (!r.ok || !r.body.ok) throw new Error((r.body && r.body.error) || 'Could not save - please try again.');
                state = r.body.state;
                render();
                submitBtn.textContent = 'Update';
                document.getElementById('xmToastBody').textContent =
                    people === 0 ? 'Thanks for letting us know.' : 'Thank you, see you on the 12th!';
                bootstrap.Toast.getOrCreateInstance(document.getElementById('xmToast')).show();
            })
            .catch(function (err) {
                formError.textContent = err.message || 'Could not save - please try again.';
                formError.classList.remove('d-none');
            })
            .finally(function () { saving = false; updateSubmit(); });
    });

    // Pick up other families' replies while the page stays open.
    setInterval(function () {
        if (saving || document.hidden) return;
        fetch(cfg.apiBase + '/api/state')
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (s) { if (s) { state = s; render(); } })
            .catch(function () {});
    }, 30000);

    render();
})();
