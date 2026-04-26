const BASE_URL = window.location.origin;
const API_URL = `${BASE_URL}/api/auth`;

// ===== MODAL CLOSE ANIMATION =====
function closeModal(overlayEl) {
    if (!overlayEl) return;
    overlayEl.classList.add('closing');
    overlayEl.addEventListener('animationend', () => {
        overlayEl.classList.remove('active', 'closing');
        overlayEl.style.display = '';
    }, { once: true });
}

// ===== SCROLL FADE-IN =====
const _fadeObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => {
        if (!e.isIntersecting) return;
        e.target.classList.add('visible');
        _fadeObserver.unobserve(e.target);
    });
}, { threshold: 0.08 });

function observeFade(root) {
    const els = (root || document).querySelectorAll('.fade-up:not(.visible)');
    els.forEach((el, i) => {
        el.style.transitionDelay = `${i * 0.06}s`;
        _fadeObserver.observe(el);
    });
}

// ── Dev live-reload ──
(function () {
    if (typeof io === 'undefined') return;
    try {
        const _dev = io(`${BASE_URL}`, { transports: ['websocket', 'polling'], extraHeaders: { 'ngrok-skip-browser-warning': 'true' } });
        _dev.on('dev_reload', () => window.location.reload());
    } catch (e) {}
})();

// ===== TOGGLE PASSWORD =====
function togglePassword(id) {
    const input = document.getElementById(id);
    input.type = input.type === 'password' ? 'text' : 'password';
}

// ===== ROLE SELECTOR =====
function selectRole(role) {
    document.querySelectorAll('.role-card').forEach(card => card.classList.remove('active'));
    document.getElementById('role-' + role).classList.add('active');
    document.getElementById('role').value = role;
}

// ===== JWT SESSION GUARD =====
function _getTokenExp() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.exp ? payload.exp * 1000 : null;
    } catch { return null; }
}

function _clearSession() {
    const uid = localStorage.getItem('user_id');
    if (uid) localStorage.removeItem('profile_avatar_' + uid);
    ['token','role','full_name','first_name','last_name','middle_initial','email','student_number','user_id'].forEach(k => localStorage.removeItem(k));
}

function _expireSession() {
    _clearSession();
    localStorage.setItem('session_expired', '1');
    window.location.href = '/login';
}

let _sessionTimer = null;
function initSessionGuard() {
    const exp = _getTokenExp();
    if (!exp) return;
    const remaining = exp - Date.now();
    if (remaining <= 0) { _expireSession(); return; }
    if (_sessionTimer) clearTimeout(_sessionTimer);
    _sessionTimer = setTimeout(_expireSession, remaining);
}

// Intercept 401 on any fetch call globally
(function() {
    const _orig = window.fetch;
    window.fetch = async function(...args) {
        const res = await _orig.apply(this, args);
        if (res.status === 401 && localStorage.getItem('token')) {
            _expireSession();
        }
        return res;
    };
})();

// ===== CHECK AUTH (para sa dashboard) =====
function checkAuth(expectedRole) {
    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');
    const full_name = localStorage.getItem('full_name');

    if (!token) {
        window.location.href = '/login';
        return;
    }

    initSessionGuard();

    if (role !== expectedRole) {
        if (role === 'professor') {
            window.location.href = '/dashboard_professor';
        } else {
            window.location.href = '/dashboard_student';
        }
        return;
    }

    const userNameEl = document.getElementById('userName');
    if (userNameEl) userNameEl.textContent = full_name;

    document.body.classList.add('dashboard-body');
}

// ===== LOGOUT =====
function logout() {
    _clearSession();
    window.location.href = '/login';
}

// ===== SIDEBAR =====
function initSidebar() {
    const role = localStorage.getItem('role');
    const fullName = localStorage.getItem('full_name') || 'User';
    const initial = fullName.charAt(0).toUpperCase();
    const avatar = localStorage.getItem('profile_avatar_' + localStorage.getItem('user_id'));
    const badgeClass = role === 'professor' ? 'badge-prof' : 'badge-student';
    const badgeText = role === 'professor' ? 'Professor' : 'Student';

    const avatarHtml = avatar
        ? `<div class="sidebar-avatar" style="overflow:hidden;padding:0;"><img src="${avatar}" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block;"></div>`
        : `<div class="sidebar-avatar">${initial}</div>`;

    const professorItems = `
        <a class="sidebar-item" href="/dashboard_professor">
            <span class="sidebar-icon"><i class="ph-bold ph-chalkboard"></i></span><span>My Classes</span>
        </a>
        <a class="sidebar-item" href="/profile">
            <span class="sidebar-icon"><i class="ph-bold ph-user-circle"></i></span><span>Profile & Settings</span>
        </a>`;

    const studentItems = `
        <a class="sidebar-item" href="/dashboard_student">
            <span class="sidebar-icon"><i class="ph-bold ph-books"></i></span><span>My Classes</span>
        </a>
        <a class="sidebar-item" href="/profile">
            <span class="sidebar-icon"><i class="ph-bold ph-user-circle"></i></span><span>Profile & Settings</span>
        </a>`;

    const menuItems = role === 'professor' ? professorItems : studentItems;

    // Inject overlay
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    overlay.id = 'sidebarOverlay';
    overlay.onclick = closeSidebar;
    document.body.appendChild(overlay);

    // Inject sidebar
    const sidebar = document.createElement('div');
    sidebar.className = 'sidebar';
    sidebar.id = 'sidebar';
    sidebar.innerHTML = `
        <div class="sidebar-header">
            ${avatarHtml}
            <div class="sidebar-user-info">
                <strong>${fullName}</strong>
                <span class="badge ${badgeClass}">${badgeText}</span>
            </div>
            <button class="sidebar-close" onclick="closeSidebar()">
                <i class="ph-bold ph-x"></i>
            </button>
        </div>
        <div class="sidebar-brand">
            <i class="ph-bold ph-flask sidebar-brand-icon"></i>
            <span>PHYSLAB</span>
        </div>
        <nav class="sidebar-nav">
            ${menuItems}
        </nav>
        <div class="sidebar-footer">
            <button class="sidebar-logout" onclick="logout()">
                <i class="ph-bold ph-sign-out"></i>
                <span>Logout</span>
            </button>
        </div>`;
    document.body.appendChild(sidebar);

    // Highlight active page
    const currentPath = window.location.pathname;
    document.querySelectorAll('.sidebar-item').forEach(item => {
        if (item.getAttribute('href') === currentPath) {
            item.classList.add('active');
        }
    });
}

function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebarOverlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('active');
    document.body.style.overflow = '';
}

// ── NOTIFICATION SYSTEM ──────────────────────────────────────────
let _notifUnread = 0;
const _notifIcons = {
    post:    { icon: 'ph-newspaper',       color: '#8b5cf6' },
    comment: { icon: 'ph-chat-circle',     color: '#3b82f6' },
    submit:  { icon: 'ph-paper-plane-tilt',color: '#10b981' },
    grade:   { icon: 'ph-star',            color: '#f59e0b' },
    joined:  { icon: 'ph-user-plus',       color: '#ec4899' },
    invite:  { icon: 'ph-envelope-simple-open', color: '#0A66C2' },
};

function _notifTimeAgo(iso) {
    const d = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (d < 60) return 'just now';
    if (d < 3600) return `${Math.floor(d/60)}m ago`;
    if (d < 86400) return `${Math.floor(d/3600)}h ago`;
    return `${Math.floor(d/86400)}d ago`;
}

function _notifItemHtml(n) {
    const ic = _notifIcons[n.type] || { icon: 'ph-bell', color: 'var(--indigo)' };
    return `<div class="nd-item${n.is_read ? '' : ' nd-unread'}" onclick="openNotif(${n.id},'${n.link||''}')">
        <div class="nd-icon" style="background:${ic.color}22;color:${ic.color}"><i class="ph-bold ${ic.icon}"></i></div>
        <div class="nd-body">
            <div class="nd-msg">${n.message}</div>
            <div class="nd-time">${_notifTimeAgo(n.ts)}</div>
        </div>
        ${n.is_read ? '' : '<div class="nd-dot"></div>'}
    </div>`;
}

function _updateNotifBadge(count) {
    _notifUnread = Math.max(0, count);
    const badge = document.getElementById('notifBadge');
    if (!badge) return;
    badge.textContent   = _notifUnread > 99 ? '99+' : _notifUnread;
    badge.style.display = _notifUnread ? 'flex' : 'none';
}

async function _loadNotifications(skipBadge = false) {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
        const data = await fetch(`${BASE_URL}/api/notifications/`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.json());
        const list = document.getElementById('ndList');
        if (!list) return;
        if (!skipBadge) {
            const unread = data.filter(n => !n.is_read).length;
            _updateNotifBadge(unread);
        }
        list.innerHTML = data.length
            ? data.map(_notifItemHtml).join('')
            : '<div class="nd-empty">No notifications yet.</div>';
    } catch {}
}

async function openNotif(id, link) {
    const token = localStorage.getItem('token');
    try { await fetch(`${BASE_URL}/api/notifications/${id}/read`, { method:'POST', headers:{'Authorization':`Bearer ${token}`} }); } catch {}
    document.getElementById('notifDropdown')?.classList.remove('nd-open');
    if (_notifUnread > 0) _updateNotifBadge(_notifUnread - 1);
    const el = document.querySelector(`.nd-item[onclick*="openNotif(${id},"]`);
    if (el) { el.classList.remove('nd-unread'); el.querySelector('.nd-dot')?.remove(); }
    // Intercept invite links
    if (link && link.startsWith('invite:')) {
        openInviteResponseModal(parseInt(link.split(':')[1]));
        return;
    }
    if (link) navigateTo(link);
}

async function markAllNotifRead() {
    const token = localStorage.getItem('token');
    try { await fetch(`${BASE_URL}/api/notifications/read-all`, { method:'POST', headers:{'Authorization':`Bearer ${token}`} }); } catch {}
    _updateNotifBadge(0);
    document.querySelectorAll('.nd-unread').forEach(el => {
        el.classList.remove('nd-unread');
        el.querySelector('.nd-dot')?.remove();
    });
}

async function toggleNotifDropdown() {
    const dd = document.getElementById('notifDropdown');
    if (!dd) return;
    dd.classList.toggle('nd-open');
    if (dd.classList.contains('nd-open')) {
        _updateNotifBadge(0); // clear badge instantly
        const token = localStorage.getItem('token');
        if (token) {
            try {
                await fetch(`${BASE_URL}/api/notifications/read-all`, {
                    method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
                });
            } catch {}
        }
        _loadNotifications(true); // skipBadge=true — badge already cleared above
    }
}

// Close dropdown on outside click
document.addEventListener('click', e => {
    const wrap = document.getElementById('notifBellWrap');
    if (wrap && !wrap.contains(e.target)) {
        document.getElementById('notifDropdown')?.classList.remove('nd-open');
    }
});

function _showNotifToast(n) {
    const ic = _notifIcons[n.type] || { icon: 'ph-bell', color: 'var(--indigo)' };
    // Invite: show Accept/Decline buttons directly in toast
    if (n.type === 'invite' && n.link && n.link.startsWith('invite:')) {
        const inviteId = parseInt(n.link.split(':')[1]);
        const toast = document.createElement('div');
        toast.className = 'notif-toast';
        toast.innerHTML = `
            <div class="nt-icon" style="background:${ic.color}22;color:${ic.color}"><i class="ph-bold ${ic.icon}"></i></div>
            <div class="nt-body">
                <div class="nt-msg">${n.message}</div>
                <div class="nt-invite-actions">
                    <button class="nt-invite-accept" onclick="respondInviteToast(${inviteId},'accept',this)"><i class="ph-bold ph-check"></i> Accept</button>
                    <button class="nt-invite-decline" onclick="respondInviteToast(${inviteId},'decline',this)"><i class="ph-bold ph-x"></i> Decline</button>
                </div>
            </div>
            <button class="nt-close" onclick="this.closest('.notif-toast').remove()"><i class="ph-bold ph-x"></i></button>`;
        document.body.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('nt-show'));
        setTimeout(() => { toast.classList.remove('nt-show'); setTimeout(() => toast.remove(), 400); }, 12000);
        return;
    }
    // On submissions page, add a Reload button for submit-type notifications
    const onSubmissionsPage = window.location.pathname === '/submissions' && n.type === 'submit';
    const reloadBtn = onSubmissionsPage
        ? `<button class="nt-reload-btn" onclick="if(typeof loadData==='function')loadData();this.closest('.notif-toast').remove();">
               <i class="ph-bold ph-arrows-clockwise"></i> Reload
           </button>`
        : '';
    const toast = document.createElement('div');
    toast.className = 'notif-toast';
    toast.innerHTML = `
        <div class="nt-icon" style="background:${ic.color}22;color:${ic.color}"><i class="ph-bold ${ic.icon}"></i></div>
        <div class="nt-body"><div class="nt-msg">${n.message}</div>${reloadBtn || '<div class="nt-sub">Tap to view</div>'}</div>
        <button class="nt-close" onclick="this.closest('.notif-toast').remove()"><i class="ph-bold ph-x"></i></button>`;
    if (n.link && !onSubmissionsPage) toast.style.cursor = 'pointer';
    toast.addEventListener('click', e => {
        if (e.target.closest('.nt-close') || e.target.closest('.nt-reload-btn')) return;
        toast.remove();
        if (n.link && !onSubmissionsPage) navigateTo(n.link);
    });
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('nt-show'));
    setTimeout(() => { toast.classList.remove('nt-show'); setTimeout(() => toast.remove(), 400); }, 5000);
}

async function respondInviteToast(inviteId, action, btn) {
    const token = localStorage.getItem('token');
    const toast = btn.closest('.notif-toast');
    btn.disabled = true;
    try {
        const r = await fetch(`${BASE_URL}/api/classes/invites/${inviteId}/respond`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const d = await r.json();
        if (r.ok) {
            toast?.remove();
            showToast(d.message, 'success');
            if (action === 'accept' && d.class_id) navigateTo(`/class_detail?id=${d.class_id}`);
        } else {
            showToast(d.message || 'Failed!', 'error');
            if (btn) btn.disabled = false;
        }
    } catch { showToast('Cannot connect to server!', 'error'); if (btn) btn.disabled = false; }
}

async function openInviteResponseModal(inviteId) {
    const token = localStorage.getItem('token');
    // Fetch invite details
    let inv;
    try {
        const r = await fetch(`${BASE_URL}/api/classes/invites/pending`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const list = await r.json();
        inv = list.find(i => i.invite_id === inviteId);
    } catch {}

    if (!inv) { showToast('Invite no longer available.', 'info'); return; }

    // Ensure modal exists
    let modal = document.getElementById('inviteResponseModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'inviteResponseModal';
        modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);align-items:center;justify-content:center;';
        modal.innerHTML = `
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:28px;max-width:380px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,0.4);">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
                <div style="width:44px;height:44px;border-radius:12px;background:rgba(10,102,194,0.12);border:1px solid rgba(10,102,194,0.2);display:flex;align-items:center;justify-content:center;font-size:20px;color:#0A66C2;flex-shrink:0;">
                    <i class="ph-bold ph-envelope-simple-open"></i>
                </div>
                <div>
                    <div style="font-size:15px;font-weight:800;color:var(--text);">Class Invite</div>
                    <div style="font-size:12px;color:var(--text-2);">You've been invited to join a class</div>
                </div>
            </div>
            <div id="inviteModalBody" style="background:var(--input-bg);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:20px;"></div>
            <div style="display:flex;gap:10px;">
                <button id="inviteDeclineBtn" style="flex:1;padding:10px;border-radius:10px;border:1px solid var(--border);background:transparent;color:var(--text-2);font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;">
                    <i class="ph-bold ph-x"></i> Decline
                </button>
                <button id="inviteAcceptBtn" style="flex:2;padding:10px;border-radius:10px;border:none;background:#0A66C2;color:white;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;">
                    <i class="ph-bold ph-check"></i> Accept Invite
                </button>
            </div>
        </div>`;
        document.body.appendChild(modal);
        modal.addEventListener('click', e => { if (e.target === modal) { modal.style.display = 'none'; } });
    }

    document.getElementById('inviteModalBody').innerHTML = `
        <div style="font-size:13px;font-weight:800;color:var(--text);margin-bottom:4px;">${inv.class_name}</div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:2px);">${inv.subject} — ${inv.section}</div>
        <div style="font-size:12px;color:var(--text-3);display:flex;align-items:center;gap:5px;margin-top:6px;"><i class="ph-bold ph-chalkboard-teacher" style="color:#0A66C2;"></i> ${inv.professor_name}</div>
        <div style="font-size:11px;color:var(--text-3);margin-top:4px;">${inv.sent_at}</div>`;

    const acceptBtn  = document.getElementById('inviteAcceptBtn');
    const declineBtn = document.getElementById('inviteDeclineBtn');
    acceptBtn.onclick  = () => _handleInviteResponse(inviteId, 'accept',  modal);
    declineBtn.onclick = () => _handleInviteResponse(inviteId, 'decline', modal);

    modal.style.display = 'flex';
}

async function _handleInviteResponse(inviteId, action, modal) {
    const token = localStorage.getItem('token');
    const btn = document.getElementById(action === 'accept' ? 'inviteAcceptBtn' : 'inviteDeclineBtn');
    if (btn) btn.disabled = true;
    try {
        const r = await fetch(`${BASE_URL}/api/classes/invites/${inviteId}/respond`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const d = await r.json();
        if (r.ok) {
            modal.style.display = 'none';
            showToast(d.message, 'success');
            if (action === 'accept' && d.class_id) navigateTo(`/class_detail?id=${d.class_id}`);
        } else {
            showToast(d.message || 'Failed!', 'error');
            if (btn) btn.disabled = false;
        }
    } catch { showToast('Cannot connect to server!', 'error'); if (btn) btn.disabled = false; }
}

function _getMyUserId() {
    const stored = parseInt(localStorage.getItem('user_id') || '0');
    if (stored) return stored;
    // Fallback: decode JWT sub claim (no re-login needed)
    try {
        const token = localStorage.getItem('token') || '';
        return parseInt(JSON.parse(atob(token.split('.')[1])).sub) || 0;
    } catch { return 0; }
}

function _setupNotifSocket() {
    const myId = _getMyUserId();
    if (!myId) return;
    const sock = window._phSocket || io(`${BASE_URL}`, { transports: ['websocket', 'polling'], extraHeaders: { 'ngrok-skip-browser-warning': 'true' } });
    window._phSocket = sock;
    sock.on('new_notification', n => {
        if (parseInt(n.user_id) !== myId) return;
        _updateNotifBadge(_notifUnread + 1);
        _showNotifToast(n);
        const list = document.getElementById('ndList');
        const dd   = document.getElementById('notifDropdown');
        if (list && dd?.classList.contains('nd-open')) {
            list.querySelector('.nd-empty')?.remove();
            list.insertAdjacentHTML('afterbegin', _notifItemHtml({...n, is_read: false}));
        }
    });
}

function initNotifBell() {
    const navUser = document.querySelector('.nav-user');
    if (!navUser || document.getElementById('notifBellWrap')) return;
    const wrap = document.createElement('div');
    wrap.id = 'notifBellWrap';
    wrap.className = 'notif-bell-wrap';
    wrap.innerHTML = `
        <button class="notif-bell-btn" id="notifBellBtn" onclick="toggleNotifDropdown()">
            <i class="ph-bold ph-bell"></i>
            <span class="notif-badge" id="notifBadge" style="display:none">0</span>
        </button>
        <div class="notif-dropdown" id="notifDropdown">
            <div class="nd-header">
                <span class="nd-title">Notifications</span>
                <button class="nd-read-all" onclick="markAllNotifRead()">Mark all read</button>
            </div>
            <div class="nd-list" id="ndList"><div class="nd-empty">No notifications yet.</div></div>
        </div>`;
    navUser.insertBefore(wrap, navUser.querySelector('.nav-avatar-wrap') || navUser.querySelector('.nav-avatar') || null);
    _loadNotifications();
    // Load Socket.IO if not yet available, then connect
    if (typeof io !== 'undefined') {
        _setupNotifSocket();
    } else {
        const s = document.createElement('script');
        s.src = 'https://cdn.socket.io/4.7.5/socket.io.min.js';
        s.onload = _setupNotifSocket;
        document.head.appendChild(s);
    }
}

// =============================================
// ===== PHASE 1 — GLOBAL FEATURES =====
// =============================================

// ===== TOAST NOTIFICATIONS =====
function showToast(message, type = 'success', duration = 3000) {
    const existing = document.querySelector(`.toast.toast-${type}`);
    if (existing) existing.remove();

    const icons = {
        success: '<i class="ph-bold ph-check-circle"></i>',
        error:   '<i class="ph-bold ph-x-circle"></i>',
        warning: '<i class="ph-bold ph-warning"></i>',
        info:    '<i class="ph-bold ph-info"></i>'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.success}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">
            <i class="ph-bold ph-x"></i>
        </button>`;

    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast-show'));

    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

// ===== 🌀 PAGE TRANSITION =====
function navigateTo(url) {
    document.body.classList.add('page-exit');
    setTimeout(() => {
        window.location.href = url;
    }, 300);
}

// Intercept all internal link clicks for smooth transition
document.addEventListener('DOMContentLoaded', () => {
    // Fade in on page load
    document.body.classList.add('page-enter');
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            document.body.classList.add('page-enter-active');
        });
    });
});

// ===== 💀 LOADING SKELETON =====
function skeletonCard(count = 3) {
    return Array(count).fill(`
        <div class="skeleton-card">
            <div class="skeleton-line skeleton-title"></div>
            <div class="skeleton-line skeleton-sub"></div>
            <div class="skeleton-line skeleton-sub short"></div>
        </div>`).join('');
}

function skeletonList(count = 4) {
    return Array(count).fill(`
        <div class="skeleton-item">
            <div class="skeleton-avatar"></div>
            <div class="skeleton-content">
                <div class="skeleton-line skeleton-title"></div>
                <div class="skeleton-line skeleton-sub"></div>
            </div>
        </div>`).join('');
}

function skeletonActivity(count = 3) {
    return Array(count).fill(`
        <div class="skeleton-item">
            <div class="skeleton-icon"></div>
            <div class="skeleton-content">
                <div class="skeleton-line skeleton-title"></div>
                <div class="skeleton-line skeleton-sub short"></div>
            </div>
            <div class="skeleton-badge"></div>
        </div>`).join('');
}

// ===== 🌙 THEME SYSTEM =====
function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('physlab_theme', t);
}

// Auto-init on every page
document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('.navbar') && localStorage.getItem('token')) {
        initSidebar();
        initNotifBell();
    }
    applyTheme(localStorage.getItem('physlab_theme') || 'dark');
    // Register service worker on every page to keep cache fresh
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
    }
});

// ===== PROGRESS BAR =====
function createProgressBar() {
    const existing = document.getElementById('pageProgressBar');
    if (existing) existing.remove();
    const bar = document.createElement('div');
    bar.className = 'page-progress-bar';
    bar.id = 'pageProgressBar';
    document.body.appendChild(bar);
    return bar;
}

function startProgress() {
    const bar = createProgressBar();
    requestAnimationFrame(() => bar.classList.add('filling'));
    return bar;
}

function finishProgress(bar) {
    bar.classList.remove('filling');
    bar.classList.add('done');
    setTimeout(() => bar.remove(), 600);
}

// ===== RIPPLE EFFECT =====
function createRipple(x, y) {
    const ripple = document.createElement('div');
    ripple.className = 'page-ripple';
    const size = Math.max(window.innerWidth, window.innerHeight) * 2.2;
    ripple.style.cssText = `
        width: ${size}px;
        height: ${size}px;
        left: ${x - size / 2}px;
        top: ${y - size / 2}px;
    `;
    document.body.appendChild(ripple);
    requestAnimationFrame(() => {
        requestAnimationFrame(() => ripple.classList.add('expand'));
    });
    setTimeout(() => ripple.remove(), 800);
}

// ===== OVERLAY HELPERS =====
const _NON_OVERLAY = ['login', 'register', 'index'];
function _isNoOverlay(url) {
    const p = (url || '').split('?')[0].replace(/\/$/, '');
    return p === '' || _NON_OVERLAY.some(n => p === '/' + n || p.endsWith('/' + n));
}
function _buildOverlay() {
    const el = document.createElement('div');
    el.id = 'pto';
    el.innerHTML = '<img class="pto-logo" src="/static/logo.svg" alt=""><span class="pto-label">PHYSLAB</span>';
    const isDark = (localStorage.getItem('physlab_theme') || document.documentElement.getAttribute('data-theme') || 'light') !== 'light';
    el.style.backgroundColor = isDark ? '#1B1F23' : '#eeeeff';
    el.querySelector('.pto-label').style.color = isDark ? '#ffffff' : '#1B1F23';
    document.body.appendChild(el);
    return el;
}


// ===== OVERRIDE navigateTo =====
function navigateTo(url, event) {
    if (document.body.classList.contains('page-exiting')) return;

    if (event) createRipple(event.clientX, event.clientY);
    else createRipple(window.innerWidth / 2, window.innerHeight / 2);

    const bar = startProgress();
    document.body.classList.add('page-exiting');
    document.body.classList.remove('page-entering');

    // No overlay for login/register/index
    if (_isNoOverlay(url) || _isNoOverlay(window.location.pathname)) {
        setTimeout(() => { finishProgress(bar); window.location.href = url; }, 320);
        return;
    }

    // Logo overlay: appears → animates → glows → navigate
    const ov = _buildOverlay();
    requestAnimationFrame(() => {
        ov.classList.add('pto-show');
        setTimeout(() => ov.classList.add('pto-anim'),  50);
        setTimeout(() => ov.classList.add('pto-glow'), 550);
        setTimeout(() => {
            finishProgress(bar);
            sessionStorage.setItem('physlab_nav', '1');
            window.location.href = url;
        }, 1350);
    });
}

// ===== FIX: pageshow =====
window.addEventListener('pageshow', (e) => {
    document.getElementById('pto')?.remove();
    document.documentElement.removeAttribute('data-entering');
    document.body.classList.remove('page-exiting');
    document.body.classList.remove('page-entering');
    document.body.style.opacity = '1';

    if (e.persisted) {
        document.body.classList.add('page-entering');
        const bar = createProgressBar(); bar.classList.add('filling');
        setTimeout(() => { finishProgress(bar); document.body.classList.remove('page-entering'); }, 500);
    }
});

// ===== PAGE ENTER ANIMATION =====
document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.remove('page-exiting');
    document.body.style.opacity = '1';
    observeFade();

    // Arriving from overlay nav
    if (document.documentElement.hasAttribute('data-entering')) {
        document.documentElement.removeAttribute('data-entering');
        const ov = _buildOverlay();
        ov.classList.add('pto-show', 'pto-arrived');
        setTimeout(() => { ov.classList.add('pto-hide'); setTimeout(() => ov.remove(), 450); }, 200);
    }

    requestAnimationFrame(() => {
        document.body.classList.add('page-entering');
        const bar = createProgressBar();
        bar.classList.add('filling');
        setTimeout(() => finishProgress(bar), 500);
    });

    setTimeout(() => {
        document.body.classList.remove('page-entering');
    }, 800);
});

// ===== INTERCEPT ALL INTERNAL <a> LINKS =====
document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;
    const href = link.getAttribute('href');
    if (!href || href.startsWith('http') || href.startsWith('mailto') || href.startsWith('#')) return;
    e.preventDefault();
    navigateTo(href, e);
});