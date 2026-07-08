/**
 * HoloMenu — events.js
 * SSE real-time listener with polling fallback.
 * Usage: import and call HoloEvents.init(onEvent)
 */
const HoloEvents = (() => {
    const API = 'http://127.0.0.1:8081/api';
    let evtSource = null;
    let pollTimer = null;
    let _onEvent = null;
    let _sseAvailable = false;

    function init(onEvent) {
        _onEvent = onEvent;
        _trySSE();
    }

    function _trySSE() {
        try {
            evtSource = new EventSource(`${API}/events/stream`);

            evtSource.onopen = () => {
                _sseAvailable = true;
                _stopPolling();
                console.log('[HoloEvents] SSE connected');
            };

            evtSource.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    if (_onEvent) _onEvent(data);
                } catch (_) { }
            };

            evtSource.onerror = () => {
                _sseAvailable = false;
                evtSource.close();
                evtSource = null;
                console.warn('[HoloEvents] SSE failed — falling back to polling');
                _startPolling();
            };
        } catch (err) {
            _sseAvailable = false;
            _startPolling();
        }
    }

    function _startPolling() {
        if (pollTimer) return;
        // Poll every 5 seconds as fallback
        pollTimer = setInterval(() => {
            if (_onEvent) _onEvent({ type: 'poll_tick' });
        }, 5000);
    }

    function _stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function destroy() {
        if (evtSource) evtSource.close();
        _stopPolling();
    }

    return { init, destroy };
})();
