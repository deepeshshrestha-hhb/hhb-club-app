/* Christmas Lunch 2026 pre-order page.
 * Family -> member selection, the dynamic order form with a live price line,
 * the family summary + payment box, and a refresh of the kitchen summary /
 * all-orders table after each change. The price shown here is a preview only:
 * the server recalculates every price from MENU_XMAS2026. */
(function () {
    'use strict';
    const C = window.XMAS_PREORDER;
    let state = C.state;
    let saving = false;

    const $ = (id) => document.getElementById(id);
    const el = {
        family: $('familySelect'), member: $('memberSelect'), form: $('orderForm'), fields: $('orderFields'),
        childMenu: $('childMenuWrap'), menuKids: $('menuKids'), menuLunch: $('menuLunch'),
        lunch: $('lunchFields'), kids: $('kidsFields'), starter: $('starterSelect'), main: $('mainSelect'),
        riceWrap: $('riceWrap'), courseHint: $('courseHint'), rice: $('riceSelect'), dessertWrap: $('dessertWrap'), dessert: $('dessertSelect'),
        kidsMeal: $('kidsSelect'), ic: $('icCheck'), icWrap: $('icWrap'), icFlavour: $('icFlavour'), icSauce: $('icSauce'),
        drinksWrap: $('drinksWrap'), drink: $('drinkSelect'), hot: $('hotSelect'),
        notesWrap: $('notesWrap'), notes: $('notesInput'), notesCount: $('notesCount'),
        price: $('priceLine'), error: $('formError'), save: $('saveBtn'),
        familyCard: $('familyCard'), locked: $('xpLocked'), summary: $('summaryContainer'),
    };
    const toast = bootstrap.Toast.getOrCreateInstance($('xpToast'), { delay: 3000 });

    // ---------- helpers ----------
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
        (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const cents = (s) => Math.round(parseFloat(s || '0') * 100);
    const gbp = (c) => (c < 0 ? '-' : '') + '£' + (Math.abs(c) / 100).toFixed(2);
    const show = (node, on) => node.classList.toggle('d-none', !on);
    const checked = (name) => { const r = el.form.querySelector(`input[name="${name}"]:checked`); return r ? r.value : ''; };
    const familySeed = (name) => C.families.find((f) => f.family === name);
    const familyState = (name) => state.families.find((f) => f.family === name);
    const orderFor = (fam, member) => { const f = familyState(fam); return f ? f.orders.find((o) => o.member === member) : null; };
    const selectedMember = () => {
        const f = familySeed(el.family.value);
        return f ? f.members.find((m) => m.name === el.member.value) : null;
    };
    const canEdit = () => !state.locked || C.isAdmin;

    // ---------- member dropdown ----------
    function renderMembers() {
        const fam = el.family.value;
        const current = el.member.value;
        const f = familySeed(fam);
        const fs = familyState(fam);
        el.member.innerHTML = '<option value="">Choose a name…</option>';
        el.member.disabled = !f;
        if (!f) return;
        f.members.forEach((m) => {
            const ordered = fs && fs.members.find((x) => x.name === m.name && x.ordered);
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = `${m.name}${m.is_child ? ' (child)' : ''} — ${ordered ? '✅ Ordered' : '⏳ Not yet'}`;
            el.member.appendChild(opt);
        });
        el.member.value = f.members.some((m) => m.name === current) ? current : '';
    }

    // ---------- order form ----------
    function setRadio(name, value) {
        el.form.querySelectorAll(`input[name="${name}"]`).forEach((r) => { r.checked = r.value === value; });
    }

    function loadOrder() {
        const m = selectedMember();
        el.error.classList.add('d-none');
        show(el.form, !!m);
        if (!m) return;
        const o = orderFor(el.family.value, m.name);
        show(el.childMenu, m.is_child);
        setRadio('menu', o ? (o.menu_type === 'kids' ? 'kids' : 'lunch') : (m.is_child ? '' : 'lunch'));
        setRadio('meal_type', o && o.menu_type !== 'kids' ? o.menu_type : '');
        el.starter.value = (o && o.starter) || '';
        el.main.value = (o && o.main) || '';
        el.rice.value = (o && o.rice_naan) || '';
        el.dessert.value = (o && o.dessert) || '';
        el.kidsMeal.value = (o && o.kids_meal) || '';
        el.ic.checked = !!(o && o.kids_icecream);
        el.icFlavour.value = (o && o.ic_flavour) || '';
        el.icSauce.value = (o && o.ic_sauce) || '';
        el.drink.querySelectorAll('optgroup[data-alcohol]').forEach((g) => { g.hidden = m.is_child; g.disabled = m.is_child; });
        el.drink.value = (o && o.drink) || '';
        el.hot.value = (o && o.hot_drink) || '';
        el.notes.value = (o && o.notes) || '';
        el.save.textContent = o ? 'Update Order' : 'Save Order';
        el.fields.disabled = !canEdit();
        update();
    }

    function currentMenu() {
        const m = selectedMember();
        if (!m) return '';
        return m.is_child ? checked('menu') : 'lunch';
    }

    function update() {
        const menu = currentMenu();
        show(el.lunch, menu === 'lunch');
        show(el.kids, menu === 'kids');
        show(el.notesWrap, !!menu);
        show(el.drinksWrap, !!menu);

        const mainOpt = el.main.selectedOptions[0];
        const isCurry = !!(mainOpt && mainOpt.dataset.curry);
        show(el.riceWrap, isCurry);
        if (!isCurry) el.rice.value = '';

        // 2 Course = any two of starter/main/dessert; 3 Course = all three.
        const mealType = checked('meal_type');
        const two = mealType === '2course';
        show(el.dessertWrap, !!mealType);
        show(el.courseHint, two);
        [[el.starter, 'starter'], [el.main, 'main'], [el.dessert, 'dessert']].forEach(([sel, what]) => {
            sel.options[0].textContent = two ? `No ${what}` : `Choose a ${what}…`;
        });

        show(el.icWrap, el.ic.checked);
        if (!el.ic.checked) { el.icFlavour.value = ''; el.icSauce.value = ''; }

        el.notesCount.textContent = el.notes.value.length;
        renderPrice(menu);
        el.save.disabled = saving || !canEdit();
    }

    function priceParts(menu) {
        const parts = [];
        if (menu === 'kids') {
            if (el.kidsMeal.value) parts.push(['Kids meal', cents(C.kidsPrice)]);
            if (el.ic.checked) parts.push(["Kid's Ice Cream", cents(C.icPrice)]);
        } else if (menu === 'lunch') {
            const mt = el.form.querySelector('input[name="meal_type"]:checked');
            if (mt) parts.push([mt.dataset.label, cents(mt.dataset.price)]);
            [el.starter, el.main].forEach((sel) => {
                const opt = sel.selectedOptions[0];
                if (opt && opt.value && cents(opt.dataset.supp) > 0) parts.push([opt.dataset.short, cents(opt.dataset.supp)]);
            });
        }
        if (menu) {
            [el.drink, el.hot].forEach((sel) => {
                const opt = sel.selectedOptions[0];
                if (opt && opt.value) parts.push([opt.value, cents(opt.dataset.price)]);
            });
        }
        return parts;
    }

    function renderPrice(menu) {
        const parts = priceParts(menu);
        el.price.classList.toggle('xp-price-empty', !parts.length);
        if (!parts.length) {
            el.price.textContent = menu ? 'Choose your meal to see the price.' : 'Choose Kids Menu or Lunch Menu.';
            return;
        }
        const total = parts.reduce((s, p) => s + p[1], 0);
        el.price.textContent = parts.map((p) => `${p[0]} ${gbp(p[1])}`).join(' + ') + ` = ${gbp(total)} (plus ${C.tipPercent}% tip, added to your family total)`;
    }

    function validate() {
        const menu = currentMenu();
        if (!menu) return 'Please choose Kids Menu or Lunch Menu.';
        if (el.notes.value.length > 150) return 'Notes can be up to 150 characters.';
        if (menu === 'kids') {
            if (!el.kidsMeal.value) return 'Please choose a kids meal.';
            if (el.ic.checked && !el.icFlavour.value) return 'Please choose an ice cream flavour.';
            if (el.ic.checked && !el.icSauce.value) return 'Please choose an ice cream sauce.';
            return '';
        }
        if (!checked('meal_type')) return 'Please choose 2 Course or 3 Course.';
        if (checked('meal_type') === '3course') {
            if (!el.starter.value) return 'Please choose a starter.';
            if (!el.main.value) return 'Please choose a main.';
            if (!el.dessert.value) return 'Please choose a dessert.';
        } else if ([el.starter, el.main, el.dessert].filter((s) => s.value).length !== 2) {
            return 'For 2 Course, please choose any two of starter, main and dessert (or pick 3 Course for all three).';
        }
        if (!el.riceWrap.classList.contains('d-none') && !el.rice.value) return 'Please choose rice or naan for your curry.';
        return '';
    }

    function payload() {
        return {
            family: el.family.value, member: el.member.value, menu: currentMenu(),
            meal_type: checked('meal_type'), starter: el.starter.value, main: el.main.value,
            rice_naan: el.rice.value, dessert: el.dessert.value, kids_meal: el.kidsMeal.value,
            kids_icecream: el.ic.checked, ic_flavour: el.icFlavour.value, ic_sauce: el.icSauce.value,
            drink: el.drink.value, hot_drink: el.hot.value, notes: el.notes.value.trim(),
        };
    }

    function showError(msg) {
        el.error.textContent = msg;
        show(el.error, !!msg);
    }

    async function postJSON(url, body) {
        const res = await fetch(url, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        });
        let data = {};
        try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
        if (!res.ok || !data.ok) throw new Error(data.error || 'Something went wrong — please try again.');
        return data;
    }

    async function save(ev) {
        ev.preventDefault();
        const err = validate();
        if (err) { showError(err); return; }
        showError('');
        saving = true;
        el.save.disabled = true;
        try {
            const data = await postJSON(C.urls.save, payload());
            state = data.state;
            renderAll();
            loadOrder();
            $('xpToastBody').textContent = `Saved ${data.order.member}'s order — ${data.order.total_label}`;
            toast.show();
        } catch (e) {
            showError(e.message);
        } finally {
            saving = false;
            update();
        }
    }

    // ---------- family summary + payment ----------
    function renderFamilyCard() {
        const fs = familyState(el.family.value);
        show(el.familyCard, !!fs);
        if (!fs) return;
        const rows = fs.members.map((m) => {
            const o = fs.orders.find((x) => x.member === m.name);
            return o
                ? `<tr><td class="fw-semibold">${esc(m.name)}</td><td class="small">${esc(o.summary)}</td><td class="text-end">${esc(o.total_label)}</td></tr>`
                : `<tr class="text-muted"><td>${esc(m.name)}</td><td class="small fst-italic">⏳ Not yet ordered</td><td class="text-end">—</td></tr>`;
        }).join('');
        const diff = cents(fs.diff);
        let payNote = '';
        if (fs.paid) {
            payNote = `<div class="small text-success mt-1">Marked paid: ${esc(fs.paid_amount_label)}${fs.paid_at ? ' on ' + esc(fs.paid_at) : ''}</div>`;
            if (diff > 0) {
                payNote += `<div class="alert alert-warning py-2 mt-2 mb-0">Your total has changed by <strong>${esc(fs.diff_label)}</strong> since you marked paid — please transfer the difference.</div>`;
            } else if (diff < 0) {
                payNote += `<div class="alert alert-warning py-2 mt-2 mb-0">Your total has gone down by <strong>${esc(fs.diff_label)}</strong> since you marked paid — ${esc(C.organiser)} will sort out the difference.</div>`;
            }
        }
        el.familyCard.innerHTML = `
            <h2>${esc(fs.family)} family</h2>
            <div class="table-responsive"><table class="table table-sm align-middle">
                <thead><tr><th>Member</th><th>Order</th><th class="text-end">Price</th></tr></thead>
                <tbody>${rows}</tbody>
                <tfoot>
                    <tr><td colspan="2">Food &amp; drinks</td><td class="text-end">${esc(fs.food_label)}</td></tr>
                    <tr><td colspan="2">Tip (${C.tipPercent}% of food &amp; drinks)</td><td class="text-end">${esc(fs.tip_label)}</td></tr>
                    <tr><td colspan="2" class="fw-bold">Family total</td><td class="text-end xp-total">${esc(fs.total_label)}</td></tr>
                </tfoot>
            </table></div>
            ${fs.remaining ? `<div class="alert alert-info py-2 small">${fs.remaining} member${fs.remaining > 1 ? 's' : ''} still to order — total may change</div>` : ''}
            <div class="xp-pay">
                <p class="mb-2">Please transfer <strong>${esc(fs.total_label)}</strong> to ${esc(C.organiser)} around the <strong>1st week of December</strong> and tick the box below when done. No need to pay yet.</p>
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="paidCheck" ${fs.paid ? 'checked' : ''} ${fs.ordered_count ? '' : 'disabled'}>
                    <label class="form-check-label" for="paidCheck">We have transferred the payment.</label>
                </div>
                ${payNote}
            </div>`;
        const box = $('paidCheck');
        box.addEventListener('change', async () => {
            box.disabled = true;
            try {
                const data = await postJSON(C.urls.paid, { family: fs.family, paid: box.checked });
                state = data.state;
                renderAll();
                $('xpToastBody').textContent = box.checked ? 'Thanks — marked as paid.' : 'Payment tick removed.';
                toast.show();
            } catch (e) {
                box.checked = !box.checked;
                box.disabled = false;
                alert(e.message);
            }
        });
    }

    // ---------- summary + polling ----------
    async function refreshSummary() {
        try {
            const res = await fetch(C.urls.summary, { cache: 'no-store' });
            if (res.ok) {
                el.summary.innerHTML = await res.text();
                // Keep the "Exclude prices" switch in step with the page after the swap.
                const hide = document.getElementById('xpHidePrices');
                if (hide) hide.checked = document.documentElement.classList.contains('xp-no-prices');
            }
        } catch (e) { /* keep the last copy */ }
    }

    function renderLocked() {
        show(el.locked, state.locked);
        el.fields.disabled = !canEdit();
    }

    function renderAll() {
        renderMembers();
        renderFamilyCard();
        renderLocked();
        refreshSummary();
    }

    async function poll() {
        if (document.hidden || saving) return;
        try {
            const res = await fetch(C.urls.state, { cache: 'no-store' });
            if (!res.ok) return;
            state = await res.json();
            renderMembers();
            renderFamilyCard();
            renderLocked();
            update();
            refreshSummary();
        } catch (e) { /* offline - try again next time */ }
    }

    // ---------- wiring ----------
    el.family.addEventListener('change', () => { el.member.value = ''; renderMembers(); renderFamilyCard(); loadOrder(); });
    el.member.addEventListener('change', loadOrder);
    el.form.addEventListener('change', update);
    el.form.addEventListener('input', update);
    el.form.addEventListener('submit', save);
    setInterval(poll, 30000);
    renderLocked();
})();
