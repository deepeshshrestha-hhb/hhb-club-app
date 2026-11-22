// HHB Annual Dinner & Gala 2026 - roles, RSVP form, who's coming, head count.
// Rendered from window.ANNUAL_DINNER.state so saves update in place (no reload,
// keeps scroll position) and a 30s poll picks up other people's changes.
(function () {
    'use strict';

    var cfg = window.ANNUAL_DINNER;
    var state = cfg.state;

    function $(id) { return document.getElementById(id); }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function toast(msg) {
        $('adToastBody').textContent = msg;
        bootstrap.Toast.getOrCreateInstance($('adToast')).show();
    }
    function post(path, body) {
        return fetch(cfg.apiBase + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().then(function (b) { return { ok: res.ok && b.ok, body: b }; });
        });
    }

    var memberOptions = cfg.members.map(function (m) {
        return '<option value="' + esc(m) + '">' + esc(m) + '</option>';
    }).join('');

    // ------------------------------------------------------------- roles --
    function renderRoles() {
        $('rolesList').innerHTML = state.roles.map(function (r) {
            if (r.holder) {
                return '<div class="ad-role"><div class="ad-role-name">' + esc(r.role) + '</div>' +
                    '<div class="ad-role-holder">✅ ' + esc(r.holder) + '</div></div>';
            }
            return '<div class="ad-role is-open"><div class="ad-role-name">' + esc(r.role) + '</div>' +
                '<div class="ad-role-open">Please volunteer</div>' +
                '<div class="ad-role-claim">' +
                '<select class="form-select form-select-sm" data-role-select="' + r.id + '" aria-label="Your name for ' + esc(r.role) + '">' +
                '<option value="">Your name…</option>' + memberOptions + '</select>' +
                '<button type="button" class="btn btn-sm btn-success text-nowrap" data-claim="' + r.id + '" disabled>I\'ll do it</button>' +
                '</div></div>';
        }).join('');
    }

    $('rolesList').addEventListener('change', function (e) {
        var id = e.target.getAttribute('data-role-select');
        if (id) document.querySelector('[data-claim="' + id + '"]').disabled = !e.target.value;
    });

    $('rolesList').addEventListener('click', function (e) {
        var btn = e.target.closest('[data-claim]');
        if (!btn) return;
        var id = btn.getAttribute('data-claim');
        var member = document.querySelector('[data-role-select="' + id + '"]').value;
        var role = state.roles.filter(function (r) { return String(r.id) === id; })[0];
        if (!member || !role) return;
        if (!confirm('Confirm: ' + member + ' will be "' + role.role + '"?\n\nOnly an admin can change this afterwards.')) return;
        btn.disabled = true;
        $('roleError').classList.add('d-none');
        post('/api/roles/' + id + '/claim', { member: member })
            .then(function (r) {
                if (r.body.state) { state = r.body.state; renderAll(); }
                if (!r.ok) throw new Error(r.body.error || 'Could not save - please try again.');
                toast('Thank you, ' + member.split(' ')[0] + '! 🙌');
            })
            .catch(function (err) {
                $('roleError').textContent = err.message;
                $('roleError').classList.remove('d-none');
                btn.disabled = false;
            });
    });

    // -------------------------------------------------------------- RSVP --
    var form = $('rsvpForm');
    var memberSelect = $('memberSelect');
    var submitBtn = $('rsvpSubmit');
    var counts = { adults: 0, teens: 0, children: 0 };
    var saving = false;
    var existing = null;

    function attending() {
        var el = form.querySelector('input[name="attending"]:checked');
        return el ? el.value : '';
    }
    function renderBands() {
        Object.keys(counts).forEach(function (b) { $('band_' + b).textContent = counts[b]; });
        $('partySize').textContent = 1 + counts.adults + counts.teens + counts.children;
        form.querySelectorAll('[data-step]').forEach(function (btn) {
            var n = counts[btn.getAttribute('data-band')];
            btn.disabled = btn.getAttribute('data-step') === '-1' ? n <= 0 : n >= cfg.maxPerBand;
        });
    }
    function updateForm() {
        $('guestFields').classList.toggle('d-none', attending() !== 'Yes');
        submitBtn.disabled = saving || !memberSelect.value || !attending();
        submitBtn.textContent = existing ? 'Update RSVP' : 'Send RSVP';
    }

    form.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-step]');
        if (!btn) return;
        var b = btn.getAttribute('data-band');
        counts[b] = Math.max(0, Math.min(cfg.maxPerBand, counts[b] + parseInt(btn.getAttribute('data-step'), 10)));
        renderBands();
    });
    form.addEventListener('change', function (e) { if (e.target.name === 'attending') updateForm(); });

    // Picking a name that's already replied loads their answer to update.
    memberSelect.addEventListener('change', function () {
        $('rsvpError').classList.add('d-none');
        existing = null;
        counts = { adults: 0, teens: 0, children: 0 };
        $('notesInput').value = '';
        form.querySelectorAll('input[name="attending"]').forEach(function (r) { r.checked = false; });
        $('rsvpExisting').classList.add('d-none');
        renderBands();
        updateForm();
        var name = memberSelect.value;
        if (!name || state.responded.indexOf(name) === -1) return;
        submitBtn.disabled = true;
        fetch(cfg.apiBase + '/api/rsvp?member=' + encodeURIComponent(name))
            .then(function (res) { return res.json(); })
            .then(function (b) {
                if (memberSelect.value !== name || !b.rsvp) return;
                existing = b.rsvp;
                $(existing.attending ? 'attYes' : 'attNo').checked = true;
                counts = { adults: existing.adults, teens: existing.teens, children: existing.children };
                $('notesInput').value = existing.notes || '';
                $('rsvpExisting').classList.remove('d-none');
                renderBands();
            })
            .catch(function () {})
            .finally(updateForm);
    });

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (submitBtn.disabled) return;
        saving = true;
        updateForm();
        $('rsvpError').classList.add('d-none');
        var yes = attending() === 'Yes';
        post('/api/rsvp', {
            member: memberSelect.value,
            attending: attending(),
            adults: yes ? counts.adults : 0,
            teens: yes ? counts.teens : 0,
            children: yes ? counts.children : 0,
            notes: yes ? $('notesInput').value : ''
        })
            .then(function (r) {
                if (!r.ok) throw new Error(r.body.error || 'Could not save - please try again.');
                state = r.body.state;
                existing = r.body.rsvp;
                $('rsvpExisting').classList.remove('d-none');
                renderAll();
                toast(yes ? 'You\'re on the list! See you on 5 December 🎉' : 'Thanks for letting us know.');
            })
            .catch(function (err) {
                $('rsvpError').textContent = err.message;
                $('rsvpError').classList.remove('d-none');
            })
            .finally(function () { saving = false; updateForm(); });
    });

    // ------------------------------------------ who's coming + head count --
    function arc(cx, cy, r, a0, a1) {
        var large = a1 - a0 > Math.PI ? 1 : 0;
        var x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
        var x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
        return 'M' + x0.toFixed(3) + ' ' + y0.toFixed(3) + ' A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x1.toFixed(3) + ' ' + y1.toFixed(3);
    }
    function renderDonut(s) {
        var parts = [[s.adults, 'var(--ad-adult)', 'Adults'], [s.teens, 'var(--ad-teen)', 'Teens'], [s.children, 'var(--ad-child)', 'Children']];
        var svg = '<circle cx="60" cy="60" r="48" fill="none" stroke="#e9eef5" stroke-width="16"/>';
        if (s.total > 0) {
            var nonZero = parts.filter(function (p) { return p[0] > 0; });
            if (nonZero.length === 1) {
                svg += '<circle cx="60" cy="60" r="48" fill="none" stroke="' + nonZero[0][1] + '" stroke-width="16"><title>' + nonZero[0][2] + ': ' + nonZero[0][0] + '</title></circle>';
            } else {
                var a = -Math.PI / 2, gap = 0.03;
                nonZero.forEach(function (p) {
                    var sweep = (p[0] / s.total) * Math.PI * 2;
                    svg += '<path d="' + arc(60, 60, 48, a + gap / 2, a + sweep - gap / 2) + '" fill="none" stroke="' + p[1] +
                        '" stroke-width="16"><title>' + p[2] + ': ' + p[0] + '</title></path>';
                    a += sweep;
                });
            }
        }
        $('ageDonut').innerHTML = svg;
    }

    function renderSummary() {
        var s = state.summary;
        $('heroCount').textContent = s.total;
        $('heroCountLabel').textContent = s.total === 1 ? 'person' : 'people';
        $('progTotal').textContent = s.total;
        $('progPct').textContent = s.progress_pct + '%';
        $('progBar').style.width = s.progress_pct + '%';
        $('progBar').parentNode.setAttribute('aria-valuenow', s.progress_pct);
        $('comingList').innerHTML = s.coming.length
            ? s.coming.map(function (n) { return '<span>' + esc(n) + '</span>'; }).join('')
            : '<p class="text-muted mb-0">No RSVPs yet. Be the first! 🎈</p>';
        $('hcTotal').textContent = s.total;
        $('hcAdults').textContent = s.adults;
        $('hcTeens').textContent = s.teens;
        $('hcChildren').textContent = s.children;
        $('hcYes').textContent = s.members_yes;
        $('hcNo').textContent = s.members_no;
        renderDonut(s);
        renderRsvps();
    }

    // ---------------------------------------------------------- all rsvps --
    // Public table. Notes sit behind an icon (they can be long); the delete
    // button is only drawn for admins (the route itself is admin_required).
    function hasNotes(n) {
        n = String(n || '').trim();
        return n !== '' && !/^(none|n\/a|na|-)$/i.test(n);
    }
    function renderRsvps() {
        var rows = state.rsvps || [];
        $('rsvpCount').textContent = rows.length;
        var cols = cfg.isAdmin ? 7 : 6;
        $('rsvpRows').innerHTML = rows.length ? rows.map(function (r, i) {
            var num = function (v) { return v ? v : '<span class="text-muted">–</span>'; };
            var notes = hasNotes(r.notes)
                ? '<button type="button" class="btn btn-sm btn-link p-0 text-decoration-none" data-notes="' + i +
                  '" aria-label="Read notes from ' + esc(r.member) + '" title="Read notes">📝</button>'
                : '';
            var del = cfg.isAdmin
                ? '<td><form method="post" action="' + esc(cfg.deleteUrl) + '" data-delete="' + esc(r.member) + '">' +
                  '<input type="hidden" name="member" value="' + esc(r.member) + '">' +
                  '<button class="btn btn-sm btn-link text-danger p-0" aria-label="Delete RSVP">🗑</button></form></td>'
                : '';
            return '<tr><td class="text-nowrap">' + esc(r.member) + '</td>' +
                '<td class="text-center">' + (r.attending ? '✅' : '❌') + '</td>' +
                '<td class="text-center">' + num(r.adults) + '</td>' +
                '<td class="text-center">' + num(r.teens) + '</td>' +
                '<td class="text-center">' + num(r.children) + '</td>' +
                '<td class="text-center">' + notes + '</td>' + del + '</tr>';
        }).join('') : '<tr><td colspan="' + cols + '" class="text-muted">No RSVPs yet.</td></tr>';
    }
    $('rsvpRows').addEventListener('click', function (e) {
        var btn = e.target.closest('[data-notes]');
        if (!btn) return;
        var r = (state.rsvps || [])[+btn.getAttribute('data-notes')];
        if (!r) return;
        $('notesModalTitle').textContent = 'Notes from ' + r.member;
        $('notesModalBody').textContent = r.notes;
        bootstrap.Modal.getOrCreateInstance($('notesModal')).show();
    });
    $('rsvpRows').addEventListener('submit', function (e) {
        var f = e.target.closest('[data-delete]');
        if (f && !confirm('Delete ' + f.getAttribute('data-delete') + "'s RSVP?")) e.preventDefault();
    });

    function renderAll() { renderRoles(); renderSummary(); }

    setInterval(function () {
        if (saving || document.hidden) return;
        // Don't wipe a half-picked role dropdown out from under someone.
        var busy = Array.prototype.some.call(document.querySelectorAll('[data-role-select]'), function (s) { return s.value; });
        fetch(cfg.apiBase + '/api/state')
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (s) { if (!s) return; state = s; if (!busy) renderRoles(); renderSummary(); })
            .catch(function () {});
    }, 30000);

    renderAll();
    renderBands();
    updateForm();
})();
