// Top 20 Player Vote page: tap-to-rank Top 10 picker + PIN-gated resubmission.
(function () {
    var STATUS_URL = '/vote/api/status';
    var VERIFY_URL = '/vote/api/verify';
    var SUBMIT_URL = '/vote';
    var PICK_N = 10;

    var candidates = window.VOTE_CANDIDATES || [];
    var picks = []; // ordered array of candidate names
    var unlockedPin = null; // set once a returning voter's PIN has been verified this page load

    var candidateList = document.getElementById('candidateList');
    var pickList = document.getElementById('pickList');
    var pickCount = document.getElementById('pickCount');
    var pickHint = document.getElementById('pickHint');
    var pickerArea = document.getElementById('pickerArea');
    var submitBtn = document.getElementById('submitVoteBtn');
    var voterSelect = document.getElementById('voterSelect');
    var errorEl = document.getElementById('voteError');
    var successEl = document.getElementById('voteSuccess');
    var pinReveal = document.getElementById('votePinReveal');
    var pinRevealValue = document.getElementById('votePinValue');
    var pinGateCard = document.getElementById('pinGateCard');
    var pinGateName = document.getElementById('pinGateName');
    var pinInput = document.getElementById('pinInput');
    var pinUnlockBtn = document.getElementById('pinUnlockBtn');
    var pinError = document.getElementById('pinError');

    if (!candidateList || !pickList || !voterSelect) return;

    function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = s == null ? '' : String(s);
        return div.innerHTML;
    }

    function showError(msg) {
        errorEl.textContent = msg || '';
        errorEl.hidden = !msg;
        if (msg) scrollToTop();
    }

    // The confirmation/PIN alerts render near the top of the page, but on
    // mobile a voter is scrolled well down into "Your Top 10" by the time
    // they tap Submit - without this, "Vote recorded" and the PIN are
    // invisible off-screen and the submission looks like it did nothing.
    function scrollToTop() {
        window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
    }

    function showPinError(msg) {
        pinError.textContent = msg || '';
        pinError.hidden = !msg;
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

    // Resets everything vote-identity-related whenever the "Voting as" name
    // changes, so switching names mid-session can't leak a half-unlocked
    // picker or a stale PIN into the next member's flow.
    function resetIdentityState() {
        picks = [];
        unlockedPin = null;
        pickerArea.hidden = true;
        pinGateCard.hidden = true;
        pinInput.value = '';
        showPinError('');
        showError('');
        successEl.hidden = true;
        pinReveal.hidden = true;
    }

    function showPicker() {
        pinGateCard.hidden = true;
        pickerArea.hidden = false;
        render();
    }

    voterSelect.addEventListener('change', function () {
        resetIdentityState();
        var member = voterSelect.value;
        if (!member) return;
        fetch(STATUS_URL + '?member=' + encodeURIComponent(member))
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.has_voted) {
                    pinGateName.textContent = member;
                    pinGateCard.hidden = false;
                } else {
                    showPicker();
                }
            })
            .catch(function () {
                showError('Could not check your voting status - please try again.');
            });
    });

    pinUnlockBtn.addEventListener('click', function () {
        showPinError('');
        var pin = pinInput.value.trim();
        var member = voterSelect.value;
        if (!member || !pin) return;
        pinUnlockBtn.disabled = true;
        fetch(VERIFY_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ member_name: member, pin: pin }),
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, body: d }; }); })
            .then(function (res) {
                if (!res.ok || !res.body.ok) {
                    showPinError((res.body && res.body.error) || 'Incorrect PIN.');
                    return;
                }
                unlockedPin = pin;
                picks = (res.body.rankings || []).filter(function (n) { return candidates.indexOf(n) !== -1; });
                showPicker();
            })
            .catch(function () {
                showPinError('Network error - please try again.');
            })
            .finally(function () {
                pinUnlockBtn.disabled = false;
            });
    });

    submitBtn.addEventListener('click', function () {
        showError('');
        successEl.hidden = true;
        pinReveal.hidden = true;
        if (!voterSelect.value || picks.length !== PICK_N) return;
        // Disable immediately, before the request starts, so a slow response
        // can't look like nothing happened and invite a repeat tap.
        submitBtn.disabled = true;
        var body = { member_name: voterSelect.value, rankings: picks };
        if (unlockedPin) body.pin = unlockedPin;
        fetch(SUBMIT_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, body: d }; }); })
            .then(function (res) {
                if (!res.ok || !res.body.ok) {
                    showError((res.body && res.body.error) || 'Could not submit your vote.');
                    return;
                }
                if (res.body.pin) {
                    // First-ever submission for this member - this is the
                    // only time the plaintext PIN is ever available, so show
                    // it prominently and remember it for any further edit
                    // within this same page load.
                    unlockedPin = res.body.pin;
                    pinRevealValue.textContent = res.body.pin;
                    pinReveal.hidden = false;
                } else {
                    successEl.hidden = false;
                }
                scrollToTop();
            })
            .catch(function () {
                showError('Network error - please try again.');
            })
            .finally(function () {
                submitBtn.disabled = picks.length !== PICK_N || !voterSelect.value;
            });
    });
})();
