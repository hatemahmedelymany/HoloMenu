const HoloWs = (() => {
    let ws = null;
    let _onMessage = null;
    let _onStatusChange = null;
    let _reconnectTimer = null;
    let _url = '';

    let _onAuthError = null;

    function connect(url, token, deviceId, onMessage, onStatusChange, onAuthError) {
        _onMessage = onMessage;
        _onStatusChange = onStatusChange;
        _onAuthError = onAuthError;
        _disconnectSilent();

        // Build URL with parameters
        let fullUrl = url;
        const queryParams = [];
        if (token) queryParams.push(`token=${encodeURIComponent(token)}`);
        if (deviceId) queryParams.push(`device_id=${encodeURIComponent(deviceId)}`);
        if (queryParams.length > 0) {
            fullUrl += (url.includes('?') ? '&' : '?') + queryParams.join('&');
        }
        _url = url; // save base url

        try {
            ws = new WebSocket(fullUrl);
            if (_onStatusChange) _onStatusChange(false);

            ws.onopen = () => {
                clearTimeout(_reconnectTimer);
                if (_onStatusChange) _onStatusChange(true);
            };

            ws.onclose = (e) => {
                if (_onStatusChange) _onStatusChange(false);
                
                // Auth error codes from server
                if (e.code >= 4001 && e.code <= 4005) {
                    console.warn(`[HoloWs] Connection rejected (code ${e.code}): ${e.reason}`);
                    if (_onAuthError) _onAuthError(e.code, e.reason);
                } else {
                    _scheduleReconnect(token, deviceId);
                }
            };

            ws.onerror = () => {
                if (_onStatusChange) _onStatusChange(false);
            };

            ws.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    if (_onMessage) _onMessage(data);
                } catch (_) { }
            };
        } catch (e) {
            console.error('WS Connection failed:', e);
            _scheduleReconnect(token, deviceId);
        }
    }

    function _scheduleReconnect(token, deviceId) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = setTimeout(() => {
            console.log('[HoloWs] Attempting reconnection...');
            connect(_url, token, deviceId, _onMessage, _onStatusChange, _onAuthError);
        }, 3000);
    }

    function _disconnectSilent() {
        if (ws) {
            ws.onopen = null;
            ws.onclose = null;
            ws.onerror = null;
            ws.onmessage = null;
            ws.close();
            ws = null;
        }
    }

    function send(data) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(data));
        }
    }

    function disconnect() {
        clearTimeout(_reconnectTimer);
        _disconnectSilent();
        if (_onStatusChange) _onStatusChange(false);
    }

    return { connect, send, disconnect };
})();
