const HoloHud = (() => {
    let hudEl = null;

    function init() {
        hudEl = document.getElementById('engine-health-hud');
    }

    function updateHealth(data) {
        if (!hudEl) init();
        if (!hudEl) return;

        const setHud = (id, ok, yesText, noText) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.textContent = ok ? yesText : noText;
            el.style.color = ok ? '#48bb78' : '#f56565';
        };

        setHud('hud-camera', data.camera_ok, '✅ OK', '❌ FAIL');
        setHud('hud-mediapipe', data.mediapipe_ok, '✅ OK', '❌ MISSING');
        setHud('hud-hand', data.hand_detected, '✅ Tracking', '⬜ None');

        const hudMode = document.getElementById('hud-mode');
        if (hudMode) {
            hudMode.textContent = (data.mode || '').toUpperCase();
            hudMode.style.color = data.mode === 'active' ? '#48bb78' : '#ecc94b';
        }

        const hudGesture = document.getElementById('hud-gesture');
        if (hudGesture && data.last_gesture) {
            hudGesture.textContent = data.last_gesture;
        }
    }

    function updateHandStatus(tracking) {
        const el = document.getElementById('hud-hand');
        if (el) {
            el.textContent = tracking ? '✅ Tracking' : '⬜ None';
            el.style.color = tracking ? '#48bb78' : '#a0aec0';
        }
    }

    function updateGesture(gesture) {
        const el = document.getElementById('hud-gesture');
        if (el) {
            el.textContent = gesture;
            el.style.color = '#00f0ff';
            clearTimeout(el._fadeTimer);
            el._fadeTimer = setTimeout(() => { el.style.color = '#a0aec0'; }, 1500);
        }
    }

    return { init, updateHealth, updateHandStatus, updateGesture };
})();
