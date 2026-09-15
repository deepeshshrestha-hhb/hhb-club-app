// Top 20 Player Vote page: tap-to-rank Top 10 picker + submit.
(function () {
    var EXISTING_URL = '/vote/api/existing';
    var SUBMIT_URL = '/vote';
    var PICK_N = 10;

    var candidates = window.VOTE_CANDIDATES || [];
    var picks = []; // ordered array of candidate names

    var candidateList = document.getElementById('candidateList');
    var pickList = document.getElementById('pickList');
    var pickCount = document.getElementById('pickCount');
    var pickHint = document.getElementById('pickHint');
    var submitBtn = document.getElementById('submitVoteBtn');
    var voterSelect = document.getElementById('voterSelect');
    var errorEl = document.getElementById('voteError');
    var successEl = document.getElementById('voteSuccess');

    if (!candidateList || !pickList || !voterSelect) return;

    function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
    }

    function showError(msg) {
        errorEl.textContent = msg || '';
        errorEl.hidden = !msg;
    }

    function renderCandidates() {
        candidateList.innerHTML = candidates.map(function (name) {
            var picked = picks.indexOf(name) !== -1;
            return '<button type="button" class="list-group-item list-group-item-action' +
                (picked ? ' picked' : '') + '" data-candidate="' + escapeHtml(name) + '"' +
                (picked ? ' disabled' : '') + '>' + escapeHtml(name) + '</button>';
        }).join('');
    }

    function renderPicks() {
        pickList.innerHTML = picks.map(function (name, i) {
            return '<li class="list-group-item d-flex align-items-center gap-2" data-pick="' + escapeHtml(name) + '">' +
                '<span class="rank-badge">' + (i + 1) + '</span>' +
                '<span class="flex-grow-1">' + escapeHtml(name) + '</span>' +
                '<button type="button" class="btn btn-sm btn-outline-danger" data-remove="' + escapeHtml(name) + '">&times;</button>' +
                '</li>';
        }).join('');
        pickCount.textContent = picks.length + ' / ' + PICK_N;
        pickHint.hidden = picks.length > 0;
        submitBtn.disabled = picks.length !== PICK_N || !voterSelect.value;
    }

    function render() {
        renderCandidates();
        renderPicks();
    }

    function addPick(name) {
        if (picks.indexOf(name) !== -1 || picks.length >= PICK_N) return;
        picks.push(name);
        render();
    }

    function removePick(name) {
        var idx = picks.indexOf(name);
        if (idx === -1) return;
        picks.splice(idx, 1);
        render();
    }

    candidateList.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-candidate]');
        if (!btn || btn.disabled) return;
        addPick(btn.getAttribute('data-candidate'));
    });

    pickList.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-remove]');
        if (!btn) return;
        removePick(btn.getAttribute('data-remove'));
    });

    // Drag the rank badge to reorder within the Top 10 - the picks array is
    // the single source of truth, so onEnd just re-reads the DOM order into
    // it and re-renders (which also renumbers the badges) rather than
    // trying to keep two representations in sync.
    if (typeof Sortable !== 'undefined') {
        Sortable.create(pickList, {
            animation: 150,
            handle: '.rank-badge',
            onEnd: function () {
                picks = Array.prototype.map.call(pickList.querySelectorAll('[data-pick]'), function (li) {
                    return li.getAttribute('data-pick');
                });
                render();
            },
        });
    }

    function loadExisting(member) {
        picks = [];
        render();
        if (!member) return;
        fetch(EXISTING_URL + '?member=' + encodeURIComponent(member))
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && Array.isArray(d.rankings)) {
                    // Drop anything no longer in the current Top 20 (e.g. the
                    // rankings changed since this member last voted) rather
                    // than failing to prefill at all.
                    picks = d.rankings.filter(function (n) { return candidates.indexOf(n) !== -1; });
                    render();
                }
            })
            .catch(function () {});
    }

    voterSelect.addEventListener('change', function () {
        showError('');
        successEl.hidden = true;
        loadExisting(voterSelect.value);
    });

    submitBtn.addEventListener('click', function () {
        showError('');
        successEl.hidden = true;
        if (!voterSelect.value || picks.length !== PICK_N) return;
        // Disable immediately, before the request starts, so a slow response
        // can't look like nothing happened and invite a repeat tap.
        submitBtn.disabled = true;
        fetch(SUBMIT_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ member_name: voterSelect.value, rankings: picks }),
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, body: d }; }); })
            .then(function (res) {
                if (!res.ok || !res.body.ok) {
                    showError((res.body && res.body.error) || 'Could not submit your vote.');
                    return;
                }
                successEl.hidden = false;
            })
            .catch(function () {
                showError('Network error - please try again.');
            })
            .finally(function () {
                submitBtn.disabled = picks.length !== PICK_N || !voterSelect.value;
            });
    });

    render();
})();
