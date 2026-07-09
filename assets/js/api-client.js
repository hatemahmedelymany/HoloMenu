const HoloApi = {
    API_BASE: 'http://127.0.0.1:8081/api',

    _getToken() {
        return localStorage.getItem('access_token');
    },

    async _handleResponse(response) {
        if (response.status === 401 || response.status === 403) {
            // Unified behavior: redirect to login
            window.location.href = '/login.html';
            return null;
        }
        if (!response.ok) {
            const body = await response.text();
            throw new Error(`HoloApi error ${response.status}: ${body}`);
        }
        return response.json();
    },

    async _request(path, options = {}) {
        const token = this._getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...(options.headers || {}),
        };
        const response = await fetch(`${this.API_BASE}${path}`, { ...options, headers });
        return this._handleResponse(response);
    },

    async getDepartments() {
        return this._request('/departments');
    },

    async getProductsByDept(deptId) {
        return this._request(`/departments/${deptId}/products`);
    },

    async createOrder() {
        return this._request('/orders', { method: 'POST' });
    },

    async addOrderItem(orderUid, productId, qty) {
        return this._request(`/orders/${orderUid}/items`, {
            method: 'POST',
            body: JSON.stringify({ product_id: productId, quantity: qty }),
        });
    },

    async updateOrderItem(orderUid, productId, qty) {
        return this._request(`/orders/${orderUid}/items`, {
            method: 'PUT',
            body: JSON.stringify({ product_id: productId, quantity: qty }),
        });
    },

    async confirmOrder(orderUid) {
        return this._request(`/orders/${orderUid}/confirm`, { method: 'POST' });
    },

    async cancelOrder(orderUid, reason = 'timeout') {
        return this._request(`/orders/${orderUid}/cancel?reason=${reason}`, { method: 'POST' });
    },

    async logAnalyticsEvent(orderUid, eventType, extra = {}) {
        try {
            await fetch(`${this.API_BASE}/analytics/events`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this._getToken()}`
                },
                body: JSON.stringify({ event_type: eventType, session_uid: orderUid, ...extra }),
            });
        } catch (e) { /* best effort */ }
    },

    async getHealth() {
        return this._request('/health');
    },

    async getChefOrders() {
        return this._request('/chef/orders');
    },

    async updateOrderStatus(orderId, status) {
        return this._request(`/orders/${orderId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
    },

    async getCashierOrders() {
        return this._request('/cashier/orders');
    },

    async payOrder(orderId, payload) {
        return this._request(`/orders/${orderId}/pay`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async getAdminOrders() {
        return this._request('/admin/orders');
    },

    async getAdminStats() {
        return this._request('/admin/stats');
    },

    async getAnalyticsSummary() {
        return this._request('/analytics/summary');
    },

    async createProduct(payload) {
        return this._request('/products', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async updateProduct(productId, payload) {
        return this._request(`/products/${productId}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
    },

    async deleteProduct(productId) {
        return this._request(`/products/${productId}`, {
            method: 'DELETE'
        });
    },

    async createDepartment(payload) {
        return this._request('/departments', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async updateDepartment(deptId, payload) {
        return this._request(`/departments/${deptId}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
    },

    async deleteDepartment(deptId) {
        return this._request(`/departments/${deptId}`, {
            method: 'DELETE'
        });
    }
};
