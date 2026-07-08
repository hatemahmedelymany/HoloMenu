const HoloApi = (() => {
    const API_BASE = 'http://127.0.0.1:8081/api';

    async function getDepartments() {
        const res = await fetch(`${API_BASE}/departments`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function getProductsByDept(deptId) {
        const res = await fetch(`${API_BASE}/departments/${deptId}/products`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function createOrder() {
        const res = await fetch(`${API_BASE}/orders`, { method: 'POST' });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function addOrderItem(orderUid, productId, qty) {
        const res = await fetch(`${API_BASE}/orders/${orderUid}/items`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_id: productId, quantity: qty }),
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function updateOrderItem(orderUid, productId, qty) {
        const res = await fetch(`${API_BASE}/orders/${orderUid}/items`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_id: productId, quantity: qty }),
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function confirmOrder(orderUid) {
        const res = await fetch(`${API_BASE}/orders/${orderUid}/confirm`, { method: 'POST' });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function cancelOrder(orderUid, reason = 'timeout') {
        const res = await fetch(`${API_BASE}/orders/${orderUid}/cancel?reason=${reason}`, { method: 'POST' });
        return res.ok;
    }

    async function logAnalyticsEvent(orderUid, eventType, extra = {}) {
        try {
            await fetch(`${API_BASE}/analytics/events`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ event_type: eventType, session_uid: orderUid, ...extra }),
            });
        } catch (e) { /* best effort */ }
    }

    async function getHealth() {
        const res = await fetch(`${API_BASE}/health`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function getChefOrders() {
        const res = await fetch(`${API_BASE}/chef/orders`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function updateOrderStatus(orderId, status) {
        const res = await fetch(`${API_BASE}/orders/${orderId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function getCashierOrders() {
        const res = await fetch(`${API_BASE}/cashier/orders`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function payOrder(orderId, payload) {
        const res = await fetch(`${API_BASE}/orders/${orderId}/pay`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function getAdminOrders() {
        const res = await fetch(`${API_BASE}/admin/orders`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function getAdminStats() {
        const res = await fetch(`${API_BASE}/admin/stats`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function getAnalyticsSummary() {
        const res = await fetch(`${API_BASE}/analytics/summary`);
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function createProduct(payload) {
        const res = await fetch(`${API_BASE}/products`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function updateProduct(productId, payload) {
        const res = await fetch(`${API_BASE}/products/${productId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function deleteProduct(productId) {
        const res = await fetch(`${API_BASE}/products/${productId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('API error');
        return res.ok;
    }

    async function createDepartment(payload) {
        const res = await fetch(`${API_BASE}/departments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function updateDepartment(deptId, payload) {
        const res = await fetch(`${API_BASE}/departments/${deptId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('API error');
        return res.json();
    }

    async function deleteDepartment(deptId) {
        const res = await fetch(`${API_BASE}/departments/${deptId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('API error');
        return res.ok;
    }

    return {
        API_BASE,
        getDepartments,
        getProductsByDept,
        createOrder,
        addOrderItem,
        updateOrderItem,
        confirmOrder,
        cancelOrder,
        logAnalyticsEvent,
        getHealth,
        getChefOrders,
        updateOrderStatus,
        getCashierOrders,
        payOrder,
        getAdminOrders,
        getAdminStats,
        getAnalyticsSummary,
        createProduct,
        updateProduct,
        deleteProduct,
        createDepartment,
        updateDepartment,
        deleteDepartment
    };
})();
