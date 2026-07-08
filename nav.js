// Intercept all fetch requests to automatically add access token and catch 401s
const originalFetch = window.fetch;
window.fetch = async function (resource, init) {
    init = init || {};
    init.headers = init.headers || {};
    const token = localStorage.getItem('access_token');
    if (token && !init.headers['Authorization'] && !init.headers['authorization']) {
        init.headers['Authorization'] = `Bearer ${token}`;
    }
    init.credentials = init.credentials || 'include';

    const response = await originalFetch(resource, init);

    // If 401 Unauthorized, display login modal (except when trying to log in itself)
    if (response.status === 401 && !resource.toString().includes('/auth/login')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_role');
        HoloNav.showLoginModal();
    }
    return response;
};

const HoloNav = (() => {
    const API = 'http://127.0.0.1:8081/api';

    const PAGES = [
        { id: 'portal', label: 'Portal', icon: '🏠', href: 'portal.html' },
        { id: 'kiosk', label: 'Kiosk', icon: '📺', href: 'index.html' },
        { id: 'chef', label: 'Chef', icon: '👨‍🍳', href: 'chef.html', badge: 'chef' },
        { id: 'cashier', label: 'Cashier', icon: '💳', href: 'cashier.html', badge: 'cashier' },
        { id: 'admin', label: 'Admin', icon: '⚙️', href: 'admin.html' },
    ];

    let _currentPage = '';
    let _statusPollTimer = null;

    function init(currentPage) {
        _currentPage = currentPage;
        _injectCSS();

        // Force authentication on staff/admin pages
        if (_currentPage !== 'kiosk' && !localStorage.getItem('access_token')) {
            showLoginModal();
            return;
        }

        _renderNav();
        document.body.classList.add('hm-nav-enabled');
        _pollBadges();
        setInterval(_pollBadges, 8000);
        _wireLogout();
    }

    function _injectCSS() {
        if (document.getElementById('hm-nav-css')) return;
        const link = document.createElement('link');
        link.id = 'hm-nav-css';
        link.rel = 'stylesheet';
        link.href = 'nav.css';
        document.head.appendChild(link);
    }

    function _renderNav() {
        const nav = document.createElement('nav');
        nav.className = 'hm-nav';
        nav.id = 'hm-nav';

        const linksHTML = PAGES.map(p => `
      <a href="${p.href}" class="hm-nav-link ${p.id === _currentPage ? 'active' : ''}" id="hm-link-${p.id}">
        <span class="nav-icon">${p.icon}</span>
        ${p.label}
        ${p.badge ? `<span class="hm-nav-badge" id="hm-badge-${p.badge}">0</span>` : ''}
      </a>
    `).join('');

        const userRole = localStorage.getItem('user_role');
        const roleBadge = userRole ? `<span style="background: rgba(0,240,255,0.1); border: 1px solid rgba(0,240,255,0.3); color: #00f0ff; border-radius: 4px; padding: 2px 6px; font-size: 0.65rem; font-weight: 700; text-transform: uppercase;">${userRole}</span>` : '';

        nav.innerHTML = `
      <a href="portal.html" class="hm-nav-brand">HoloMenu <span>Suite</span></a>
      <div class="hm-nav-links">${linksHTML}</div>
      <div class="hm-nav-status" style="display: flex; gap: 15px; align-items: center;">
        <div class="hm-nav-status-info" style="display: flex; align-items: center; gap: 7px;">
          <div class="hm-status-dot" id="hm-status-dot"></div>
          <span class="hm-nav-status-text" id="hm-status-text">Connecting…</span>
        </div>
        ${roleBadge}
        ${localStorage.getItem('access_token') ? `<button id="hm-logout-btn" style="background:none; border:1px solid rgba(255,23,68,0.4); color:#ff1744; border-radius:6px; padding:3px 8px; font-size:0.7rem; font-weight:700; cursor:pointer; text-transform:uppercase; transition: all 0.2s;">Logout</button>` : ''}
      </div>
    `;

        document.body.insertBefore(nav, document.body.firstChild);
    }

    function _wireLogout() {
        const logoutBtn = document.getElementById('hm-logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async () => {
                try {
                    await originalFetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' });
                } catch (_) { }
                localStorage.removeItem('access_token');
                localStorage.removeItem('user_role');
                window.location.reload();
            });
        }
    }

    function showLoginModal() {
        if (document.getElementById('hm-login-overlay')) {
            document.getElementById('hm-login-overlay').classList.add('visible');
            return;
        }

        const overlay = document.createElement('div');
        overlay.id = 'hm-login-overlay';
        overlay.className = 'hm-login-overlay visible';
        overlay.innerHTML = `
            <div class="hm-login-card">
                <div class="hm-login-logo">HoloMenu <span>Portal</span></div>
                <div class="hm-login-subtitle">System Authentication Required</div>
                <form id="hm-login-form">
                    <div class="hm-login-form-group">
                        <label class="hm-login-label">Username</label>
                        <input type="text" id="hm-login-username" class="hm-login-input" placeholder="Enter username" required autocomplete="username">
                    </div>
                    <div class="hm-login-form-group">
                        <label class="hm-login-label">Password</label>
                        <input type="password" id="hm-login-password" class="hm-login-input" placeholder="Enter password" required autocomplete="current-password">
                    </div>
                    <button type="submit" class="hm-login-btn">Log In</button>
                    <div id="hm-login-error" class="hm-login-error"></div>
                </form>
            </div>
        `;
        document.body.appendChild(overlay);

        document.getElementById('hm-login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('hm-login-username').value;
            const password = document.getElementById('hm-login-password').value;
            const errorDiv = document.getElementById('hm-login-error');
            errorDiv.style.display = 'none';

            try {
                const res = await originalFetch(`${API}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                if (!res.ok) {
                    throw new Error('Invalid username or password');
                }

                const data = await res.json();
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('user_role', data.role);
                overlay.classList.remove('visible');
                window.location.reload();
            } catch (err) {
                errorDiv.textContent = err.message || 'Login failed. Please try again.';
                errorDiv.style.display = 'block';
            }
        });
    }

    async function _pollBadges() {
        try {
            const res = await fetch(`${API}/health`);
            if (!res.ok) throw new Error('offline');
            const data = await res.json();

            // Update system status
            const dot = document.getElementById('hm-status-dot');
            const txt = document.getElementById('hm-status-text');
            if (dot) { dot.classList.add('online'); }
            if (txt) txt.textContent = 'System Online';

            // Chef badge = confirmed + cooking
            const chefCount = (data.status_counts?.confirmed || 0) + (data.status_counts?.cooking || 0);
            _setBadge('chef', chefCount);

            // Cashier badge = ready (awaiting payment)
            const cashierCount = data.status_counts?.ready || 0;
            _setBadge('cashier', cashierCount);

        } catch (_) {
            const dot = document.getElementById('hm-status-dot');
            const txt = document.getElementById('hm-status-text');
            if (dot) dot.classList.remove('online');
            if (txt) txt.textContent = 'Backend Offline';
        }
    }

    function _setBadge(page, count) {
        const el = document.getElementById(`hm-badge-${page}`);
        if (!el) return;
        el.textContent = count;
        el.classList.toggle('visible', count > 0);
    }

    return { init, showLoginModal };
})();
