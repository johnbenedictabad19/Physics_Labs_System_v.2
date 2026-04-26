/**
 * navbar.js — shared navbar profile card + dropdown logic for all logged-in pages.
 * Load AFTER static/script.js so API_URL and logout() are available.
 */
(function () {
    const _uid   = () => localStorage.getItem('user_id');
    const _token = () => localStorage.getItem('token');
    const _role  = () => localStorage.getItem('role') || 'student';

    // ── Detect which nav item is active from the current URL ──────────────────
    function _activePage() {
        const p = window.location.pathname;
        if (p.includes('dashboard')) return 'classes';
        if (p.includes('archived'))  return 'archived';
        if (p.includes('profile'))   return 'profile';
        return '';
    }

    // ── Build the full dropdown HTML (profile card + menu items) ──────────────
    function _buildDropdown() {
        const role       = _role();
        const fullName   = localStorage.getItem('full_name')      || '';
        const firstName  = localStorage.getItem('first_name')     || '';
        const lastName   = localStorage.getItem('last_name')      || '';
        const email      = localStorage.getItem('email')          || '';
        const studentNum = localStorage.getItem('student_number') || '';
        const avatar     = localStorage.getItem('profile_avatar_' + _uid()) || '';

        const displayName = fullName || (lastName && firstName ? `${lastName}, ${firstName}` : firstName || lastName || 'User');
        const subInfo     = role === 'student' ? studentNum : email;
        const roleLabel   = role === 'professor' ? 'Professor' : 'Student';
        const dashHref    = role === 'professor' ? '/dashboard_professor' : '/dashboard_student';
        const dashIcon    = role === 'professor' ? 'ph-chalkboard' : 'ph-books';
        const active      = _activePage();

        const avatarInner = avatar
            ? `<img src="${avatar}" style="width:100%;height:100%;object-fit:cover;border-radius:10px;" alt="avatar">`
            : `<span class="nd-pc-initial">${(firstName || 'U').charAt(0).toUpperCase()}</span>`;

        return `
<div class="nd-profile-card">
    <div class="nd-pc-avatar">${avatarInner}</div>
    <div class="nd-pc-info">
        <div class="nd-pc-name">${displayName}</div>
        <div class="nd-pc-meta">
            <span class="nd-pc-role">${roleLabel}</span>
            ${subInfo ? `<span class="nd-pc-sub">${subInfo}</span>` : ''}
        </div>
    </div>
</div>
<div class="nd-divider"></div>
<a href="${dashHref}" ${active === 'classes'  ? 'class="nd-active"' : ''}><i class="ph-bold ${dashIcon}"></i> My Classes</a>
<a href="/archived"   ${active === 'archived' ? 'class="nd-active"' : ''}><i class="ph-bold ph-archive"></i> Archived</a>
<a href="/profile"    ${active === 'profile'  ? 'class="nd-active"' : ''}><i class="ph-bold ph-user-circle"></i> Profile & Settings</a>
<div class="nd-divider"></div>
<button class="nd-logout" onclick="logout()"><i class="ph-bold ph-sign-out"></i> Logout</button>`;
    }

    // ── Populate the avatar button (initial or photo) ─────────────────────────
    function _populateAvatar() {
        const btn = document.getElementById('navAvatar');
        if (!btn) return;
        const avatar  = localStorage.getItem('profile_avatar_' + _uid()) || '';
        const initial = btn.querySelector('.nav-av-initial');
        const img     = btn.querySelector('img');
        const name    = localStorage.getItem('first_name') || localStorage.getItem('full_name') || 'U';
        if (initial) initial.textContent = name.charAt(0).toUpperCase();
        if (avatar && img) {
            img.src = avatar; img.style.display = 'block';
            if (initial) initial.style.display = 'none';
        } else {
            if (img) img.style.display = 'none';
            if (initial) initial.style.display = '';
        }
    }

    // ── Render dropdown into the DOM ──────────────────────────────────────────
    function _render() {
        const dd = document.getElementById('navDropdown');
        if (dd) dd.innerHTML = _buildDropdown();
        _populateAvatar();
    }

    // ── Fetch fresh profile data from API then re-render ─────────────────────
    async function _syncProfile() {
        const token = _token();
        if (!token) return;
        const base = (typeof API_URL !== 'undefined') ? API_URL : '/api/auth';
        try {
            const res = await fetch(base + '/profile', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) return;
            const d = await res.json();
            localStorage.setItem('full_name',      d.full_name      || '');
            localStorage.setItem('first_name',     d.first_name     || '');
            localStorage.setItem('last_name',      d.last_name      || '');
            localStorage.setItem('middle_initial', d.middle_initial || '');
            localStorage.setItem('email',          d.email          || '');
            localStorage.setItem('student_number', d.student_number || '');
            if (d.role) localStorage.setItem('role', d.role);
            if (d.avatar && _uid()) localStorage.setItem('profile_avatar_' + _uid(), d.avatar);
        } catch (_) {}
        _render();
    }

    // ── Dropdown toggle (global, overrides any inline definition) ─────────────
    window.toggleNavDropdown = function () {
        document.getElementById('navDropdown')?.classList.toggle('open');
    };

    document.addEventListener('click', function (e) {
        if (!e.target.closest('.nav-avatar-wrap')) {
            document.getElementById('navDropdown')?.classList.remove('open');
        }
    });

    // ── Init on DOM ready ─────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        _render();       // fast: from localStorage
        _syncProfile();  // async: fetch fresh data then re-render
    });
})();
