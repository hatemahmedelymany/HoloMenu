const HoloWs = (() => {
    let ws = null;
    let _onMessage = null;
    let _onStatusChange = null;
    let _reconnectTimer = null;
    let _url = '';

    function connect(url, onMessage, onStatusChange) {
        _url = url;
        _onMessage = onMessage;
        _onStatusChange = onStatusChange;
        _disconnectSilent();

        try {
            ws = new WebSocket(url);
            if (_onStatusChange) _onStatusChange(false);

            ws.onopen = () => {
                clearTimeout(_reconnectTimer);
                if (_onStatusChange) _onStatusChange(true);
            };

            ws.onclose = () => {
                if (_onStatusChange) _onStatusChange(false);
                _scheduleReconnect();
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
            _scheduleReconnect();
        }
    }

    function _scheduleReconnect() {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = setTimeout(() => {
            console.log('[HoloWs] Attempting reconnection...');
            connect(_url, _onMessage, _onStatusChange);
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
