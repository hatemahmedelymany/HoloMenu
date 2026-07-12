/* ==========================================================================
   HoloMenu app.js — Phase 2: State Machine, Dwell-Click, DB-backed Catalog
   ========================================================================== */

const API_BASE = HoloApi.API_BASE;

// ─── App State Machine ────────────────────────────────────────────────────────
const STATE = {
  IDLE: 'IDLE',
  DEPARTMENT_SELECT: 'DEPARTMENT_SELECT',
  PRODUCT_BROWSE: 'PRODUCT_BROWSE',
  PRODUCT_DETAILS: 'PRODUCT_DETAILS',
  CART: 'CART',
  ORDER_CONFIRM: 'ORDER_CONFIRM',
  ORDER_COMPLETE: 'ORDER_COMPLETE',
};

let currentState = STATE.IDLE;
let currentOrderUid = null;
let currentDept = null;   // { id, name_en, name_ar }
let products = [];
let currentProductIndex = 0;
let cart = [];
let localLanguage = 'en';
let wsConnection = null;
let gestureCooldownActive = false;
let inactivityTimer = null;
const INACTIVITY_MS = 75_000;
const RETURN_TO_IDLE_MS = 8_000;

// ─── DOM References ──────────────────────────────────────────────────────────
const idleScreen = document.getElementById('idle-screen');
const deptScreen = document.getElementById('dept-screen');
const productScreen = document.getElementById('product-screen');

const startOrderBtn = document.getElementById('start-order-btn');
const backToDeptBtn = document.getElementById('back-to-depts-btn');
const deptButtonsEl = document.getElementById('dept-buttons');
const currentDeptLabel = document.getElementById('current-dept-label');

const connStatusBadge = document.getElementById('conn-status');
const connStatusText = document.getElementById('status-text');
const deptConnBadge = document.getElementById('dept-conn-badge');
const deptStatusText = document.getElementById('dept-status-text');

const handPointer = document.getElementById('hand-pointer');
const handPointerProd = document.getElementById('hand-pointer-product');
const gestureHud = document.getElementById('gesture-hud');

const carouselEl = document.getElementById('product-carousel');
const nameEl = document.getElementById('curr-product-name');
const priceEl = document.getElementById('curr-product-price');
const dotsEl = document.getElementById('carousel-dots');
const langToggleBtn = document.getElementById('lang-toggle');
const langToggleBtn2 = document.getElementById('lang-toggle-2');

const detailsPanel = document.getElementById('product-details-panel');
const detailsEmptyState = document.getElementById('details-empty-state');
const detailsContent = document.getElementById('details-content');
const detailCategory = document.getElementById('detail-category');
const detailTitle = document.getElementById('detail-title');
const detailPrice = document.getElementById('detail-price');
const detailDesc = document.getElementById('detail-desc');
const detailCalories = document.getElementById('detail-calories');
const detailAllergens = document.getElementById('detail-allergens');
const detailIngredients = document.getElementById('detail-ingredients');

const cartModal = document.getElementById('cart-modal');
const cartIndicatorBtn = document.getElementById('cart-indicator-btn');
const cartIndicatorBtn2 = document.getElementById('cart-indicator-btn-2');
const closeCartBtn = document.getElementById('close-cart-btn');
const cartItemsList = document.getElementById('cart-items-list');
const cartTotalPrice = document.getElementById('cart-total-price');
const addMoreBtn = document.getElementById('add-more-btn');
const confirmOrderBtn = document.getElementById('confirm-order-btn');

const productQrModal = document.getElementById('product-qr-modal');
const qrProductTitle = document.getElementById('qr-product-title');
const qrProductUrl = document.getElementById('qr-product-url');
const closeProductQrBtn = document.getElementById('close-product-qr-btn');

const orderCompleteModal = document.getElementById('order-complete-modal');
const countdownFill = document.getElementById('order-countdown-fill');

const simDrawer = document.getElementById('simulator-drawer');
const simToggleBtn = document.getElementById('simulator-toggle-btn');
const simWsUrlInput = document.getElementById('sim-ws-url');
const simBtnConnect = document.getElementById('sim-btn-connect');
const simStatusLabel = document.getElementById('sim-status-label');
const simCoordsPad = document.getElementById('sim-coords-pad');
const simCursor = document.getElementById('pad-cursor');
const simCoordXVal = document.getElementById('sim-coord-x');
const simCoordYVal = document.getElementById('sim-coord-y');
const simStartOrder = document.getElementById('sim-start-order');
const simEndSession = document.getElementById('sim-end-session');

// ─── Audio Synth ─────────────────────────────────────────────────────────────
const synth = {
  ctx: null,
  init() { if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)(); },
  playBeep(freq, type, duration) {
    try {
      this.init();
      if (this.ctx.state === 'suspended') this.ctx.resume();
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
      gain.gain.setValueAtTime(0.15, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + duration);
      osc.connect(gain); gain.connect(this.ctx.destination);
      osc.start(); osc.stop(this.ctx.currentTime + duration);
    } catch (e) { /* silent */ }
  },
  swipe() { this.playBeep(800, 'sine', 0.1); setTimeout(() => this.playBeep(1200, 'sine', 0.1), 50); },
  click() { this.playBeep(1000, 'triangle', 0.08); },
  success() { this.playBeep(600, 'sine', 0.12); setTimeout(() => this.playBeep(900, 'sine', 0.12), 80); setTimeout(() => this.playBeep(1300, 'sine', 0.2), 160); },
  close() { this.playBeep(1000, 'sine', 0.1); setTimeout(() => this.playBeep(600, 'sine', 0.15), 80); },
};

// ─── State Machine ───────────────────────────────────────────────────────────
function transitionTo(newState, payload = {}) {
  console.log(`State: ${currentState} → ${newState}`);
  currentState = newState;

  // Hide all screens/modals
  idleScreen.classList.remove('active');
  deptScreen.classList.remove('active');
  productScreen.classList.remove('active');
  cartModal.classList.add('hidden');
  productQrModal.classList.add('hidden');
  orderCompleteModal.classList.add('hidden');

  resetInactivityTimer();

  switch (newState) {
    case STATE.IDLE:
      idleScreen.classList.add('active');
      clearInactivityTimer();
      sendWsCmd('end_session');
      if (currentOrderUid && payload.cancel !== false) {
        apiCancelOrder(currentOrderUid, 'session_end');
      }
      currentOrderUid = null;
      cart = [];
      updateCartBadge();
      break;

    case STATE.DEPARTMENT_SELECT:
      deptScreen.classList.add('active');
      sendWsCmd('start_order');
      if (!currentOrderUid) createOrder();
      loadDepartments();
      break;

    case STATE.PRODUCT_BROWSE:
      productScreen.classList.add('active');
      if (payload.dept) {
        currentDept = payload.dept;
        currentDeptLabel.textContent = localLanguage === 'ar' ? currentDept.name_ar : currentDept.name_en;
        loadProductsByDept(currentDept.id);
      }
      break;

    case STATE.PRODUCT_DETAILS:
      productScreen.classList.add('active');
      toggleDetailsPanel(true);
      break;

    case STATE.CART:
      productScreen.classList.add('active');
      cartModal.classList.remove('hidden');
      renderCartItems();
      break;

    case STATE.ORDER_CONFIRM:
      productScreen.classList.add('active');
      cartModal.classList.remove('hidden');
      renderCartItems();
      confirmOrder();
      break;

    case STATE.ORDER_COMPLETE:
      orderCompleteModal.classList.remove('hidden');
      synth.success();
      sendWsCmd('end_session');
      startReturnToIdleCountdown();
      break;
  }
}

// ─── Inactivity Timer ────────────────────────────────────────────────────────
function resetInactivityTimer() {
  if (currentState === STATE.IDLE) return;
  clearInactivityTimer();
  inactivityTimer = setTimeout(() => {
    triggerHudNotification('SESSION TIMEOUT', '⏱️');
    transitionTo(STATE.IDLE);
  }, INACTIVITY_MS);
}

function clearInactivityTimer() {
  if (inactivityTimer) { clearTimeout(inactivityTimer); inactivityTimer = null; }
}

// ─── API Calls ───────────────────────────────────────────────────────────────
async function loadDepartments() {
  deptButtonsEl.innerHTML = '<div class="dept-loading">Loading...</div>';
  try {
    const depts = await HoloApi.getDepartments();
    renderDeptButtons(depts);
  } catch (e) {
    console.warn('API unavailable, using fallback departments', e);
    renderDeptButtons(FALLBACK_DEPTS);
  }
}

async function loadProductsByDept(deptId) {
  carouselEl.innerHTML = '<div class="hologram-viewport"><div class="spinner"></div></div>';
  currentProductIndex = 0;
  try {
    products = await HoloApi.getProductsByDept(deptId);
  } catch (e) {
    console.warn('API unavailable, using fallback products', e);
    products = FALLBACK_PRODUCTS.filter(p => p.category_id == deptId || true).slice(0, 4);
  }
  renderCarousel();
  updateProductDisplay();
}

async function createOrder() {
  try {
    const data = await HoloApi.createOrder();
    currentOrderUid = data.order_uid;
    console.log('Order created:', currentOrderUid);
  } catch (e) {
    console.warn('Could not create order in DB:', e);
    currentOrderUid = `local_${Date.now()}`;
  }
}

async function apiAddItem(productId, qty = 1) {
  if (!currentOrderUid) return;
  try {
    await HoloApi.addOrderItem(currentOrderUid, productId, qty);
  } catch (e) { console.warn('Could not add item to order:', e); }
}

async function confirmOrder() {
  if (!currentOrderUid) return;
  try {
    const data = await HoloApi.confirmOrder(currentOrderUid);

    // Render the sequential Order Number
    const orderNumEl = document.getElementById('order-complete-number');
    if (orderNumEl) {
      orderNumEl.textContent = `Order #${data.order_number || 'N/A'}`;
    }

    generateConfirmQR(data.qr_payload || `https://example.com/pickup/${currentOrderUid}`);
    setTimeout(() => transitionTo(STATE.ORDER_COMPLETE), 600);
  } catch (e) {
    console.warn('Could not confirm order:', e);
    generateConfirmQR(`https://example.com/pickup/${currentOrderUid}`);
    setTimeout(() => transitionTo(STATE.ORDER_COMPLETE), 600);
  }
}

async function apiCancelOrder(uid, reason = 'timeout') {
  try {
    await HoloApi.cancelOrder(uid, reason);
  } catch (e) { /* best effort */ }
}

async function logAnalyticsEvent(eventType, extra = {}) {
  if (!currentOrderUid) return;
  await HoloApi.logAnalyticsEvent(currentOrderUid, eventType, extra);
}

// ─── Department Buttons ───────────────────────────────────────────────────────
const DEPT_ICONS = { 'Burgers': '🍔', 'Sides': '🍟', 'Drinks': '🥤', 'Desserts': '🍰' };

function renderDeptButtons(depts) {
  deptButtonsEl.innerHTML = '';
  depts.forEach(dept => {
    const btn = document.createElement('div');
    btn.className = 'dept-btn glass-panel';
    btn.dataset.deptId = dept.id;
    btn.innerHTML = `
      <div class="dept-icon">${DEPT_ICONS[dept.name_en] || '🍴'}</div>
      <div class="dept-name EN-only">${dept.name_en}</div>
      <div class="dept-name AR-only">${dept.name_ar}</div>
      <svg class="dwell-ring" viewBox="0 0 44 44">
        <circle class="dwell-ring-track" cx="22" cy="22" r="20" fill="none" stroke-width="3"/>
        <circle class="dwell-ring-fill" cx="22" cy="22" r="20" fill="none" stroke-width="3"
          stroke-dasharray="125.66" stroke-dashoffset="125.66"/>
      </svg>`;

    // Mouse/touch click fallback
    btn.addEventListener('click', () => selectDepartment(dept));
    deptButtonsEl.appendChild(btn);
  });
}

function selectDepartment(dept) {
  synth.success();
  triggerHudNotification(dept.name_en.toUpperCase(), DEPT_ICONS[dept.name_en] || '🍴');
  logAnalyticsEvent('department_click', { department_id: dept.id });
  transitionTo(STATE.PRODUCT_BROWSE, { dept });
}

// ─── Dwell-Click Engine ───────────────────────────────────────────────────────
const DWELL_DURATION = 1300; // ms, from config
const DWELL_COOLDOWN = 800;
let dwellState = { target: null, startTime: 0, timer: null, lastClickTime: 0 };

function updateDwellCursor(ftx, fty) {
  if (currentState !== STATE.DEPARTMENT_SELECT) return;

  const px = ftx * window.innerWidth;
  const py = fty * window.innerHeight;

  let hoveredBtn = null;
  document.querySelectorAll('.dept-btn').forEach(btn => {
    const rect = btn.getBoundingClientRect();
    if (px >= rect.left && px <= rect.right && py >= rect.top && py <= rect.bottom) {
      hoveredBtn = btn;
    }
  });

  if (hoveredBtn !== dwellState.target) {
    // Reset previous ring
    if (dwellState.target) {
      const ring = dwellState.target.querySelector('.dwell-ring-fill');
      if (ring) ring.style.strokeDashoffset = '125.66';
      dwellState.target.classList.remove('dwell-active');
    }
    clearTimeout(dwellState.timer);
    dwellState.target = hoveredBtn;

    if (hoveredBtn) {
      const now = Date.now();
      if (now - dwellState.lastClickTime < DWELL_COOLDOWN) return;
      dwellState.startTime = now;
      hoveredBtn.classList.add('dwell-active');
      animateDwellRing(hoveredBtn, 0);
      dwellState.timer = setTimeout(() => {
        const deptId = parseInt(hoveredBtn.dataset.deptId);
        const allBtns = document.querySelectorAll(`.dept-btn[data-dept-id="${deptId}"]`);
        dwellState.lastClickTime = Date.now();
        dwellState.target = null;
        // Find dept data
        const nameEn = hoveredBtn.querySelector('.dept-name.EN-only').textContent;
        const nameAr = hoveredBtn.querySelector('.dept-name.AR-only').textContent;
        selectDepartment({ id: deptId, name_en: nameEn, name_ar: nameAr });
      }, DWELL_DURATION);
    }
  } else if (hoveredBtn && dwellState.startTime > 0) {
    // Animate ring progress
    const progress = Math.min((Date.now() - dwellState.startTime) / DWELL_DURATION, 1);
    const ring = hoveredBtn.querySelector('.dwell-ring-fill');
    if (ring) ring.style.strokeDashoffset = 125.66 * (1 - progress);
  }
}

function animateDwellRing(btn, progress) {
  const ring = btn.querySelector('.dwell-ring-fill');
  if (ring) ring.style.strokeDashoffset = 125.66 * (1 - progress);
}

// ─── Product Carousel ─────────────────────────────────────────────────────────
function renderCarousel() {
  dotsEl.innerHTML = '';
  products.forEach((_, idx) => {
    const dot = document.createElement('div');
    dot.className = `dot ${idx === currentProductIndex ? 'active' : ''}`;
    dotsEl.appendChild(dot);
  });
}

function updateProductDisplay() {
  if (products.length === 0) return;
  const count = products.length;
  carouselEl.innerHTML = '';

  products.forEach((prod, index) => {
    const card = document.createElement('div');
    card.className = 'hologram-viewport';
    if (index === currentProductIndex) card.classList.add('curr-card');
    else if (index === (currentProductIndex - 1 + count) % count) card.classList.add('prev-card');
    else if (index === (currentProductIndex + 1) % count) card.classList.add('next-card');
    else card.classList.add('hidden-card');

    const img = document.createElement('img');
    img.src = prod.media_path || prod.thumbnail_path || '';
    img.alt = prod.name_en;
    img.onerror = () => { img.src = 'https://picsum.photos/300/300?blur=2'; };
    card.appendChild(img);
    carouselEl.appendChild(card);
  });

  const p = products[currentProductIndex];
  nameEl.textContent = localLanguage === 'ar' ? p.name_ar : p.name_en;
  priceEl.textContent = `${p.price} ${p.currency || 'EGP'}`;

  dotsEl.querySelectorAll('.dot').forEach((d, i) =>
    d.classList.toggle('active', i === currentProductIndex));

  if (!detailsContent.classList.contains('hidden')) populateDetails(p);
}

function populateDetails(p) {
  detailCategory.textContent = localLanguage === 'ar' ? (currentDept?.name_ar || '') : (currentDept?.name_en || '');
  detailTitle.textContent = localLanguage === 'ar' ? p.name_ar : p.name_en;
  detailPrice.textContent = `${p.price} ${p.currency || 'EGP'}`;
  detailDesc.textContent = localLanguage === 'ar' ? p.description_ar : p.description_en;
  detailCalories.textContent = `${p.calories || 0} kcal`;
  const allergens = Array.isArray(p.allergens) ? p.allergens : [];
  detailAllergens.textContent = allergens.length ? allergens.join(', ') : 'None';
  detailIngredients.innerHTML = '';
  const ingredients = Array.isArray(p.ingredients) ? p.ingredients : [];
  ingredients.forEach(ing => {
    const span = document.createElement('span');
    span.className = 'tag'; span.textContent = ing;
    detailIngredients.appendChild(span);
  });
}

function toggleDetailsPanel(show) {
  if (show) {
    populateDetails(products[currentProductIndex]);
    detailsEmptyState.classList.add('hidden');
    detailsContent.classList.remove('hidden');
    synth.click();
  } else {
    detailsEmptyState.classList.remove('hidden');
    detailsContent.classList.add('hidden');
    synth.close();
  }
}

// ─── Swipe Nav ────────────────────────────────────────────────────────────────
function handleSwipe(direction) {
  if (gestureCooldownActive) return;
  triggerCooldown();
  const count = products.length;
  currentProductIndex = direction === 'RIGHT'
    ? (currentProductIndex + 1) % count
    : (currentProductIndex - 1 + count) % count;
  synth.swipe();
  updateProductDisplay();
  triggerHudNotification(direction === 'RIGHT' ? 'SWIPE RIGHT' : 'SWIPE LEFT', '↔️');
  resetInactivityTimer();
}

function triggerCooldown() {
  gestureCooldownActive = true;
  setTimeout(() => { gestureCooldownActive = false; }, 1000);
}

// ─── Cart ─────────────────────────────────────────────────────────────────────
function addToCart() {
  if (gestureCooldownActive) return;
  triggerCooldown();
  const item = products[currentProductIndex];
  const existing = cart.findIndex(c => c.id === item.id);
  if (existing > -1) {
    cart[existing].quantity += 1;
  } else {
    cart.push({ id: item.id, name_en: item.name_en, name_ar: item.name_ar, price: parseFloat(item.price), quantity: 1 });
  }
  apiAddItem(item.id, 1);
  logAnalyticsEvent('add_to_cart', { product_id: item.id });
  synth.success();
  updateCartBadge();
  triggerHudNotification('ADDED TO CART', '👍');
  resetInactivityTimer();
}

function updateCartBadge() {
  const totalQty = cart.reduce((a, c) => a + c.quantity, 0);
  document.querySelectorAll('#cart-count, #cart-count-2').forEach(el => el.textContent = totalQty);
  [cartIndicatorBtn, cartIndicatorBtn2].forEach(btn => {
    if (btn) { btn.classList.add('pulse-anim'); setTimeout(() => btn.classList.remove('pulse-anim'), 400); }
  });
}

function renderCartItems() {
  cartItemsList.innerHTML = '';
  if (cart.length === 0) {
    cartItemsList.innerHTML = '<p style="padding:15px;color:#718096">Cart is empty</p>';
    cartTotalPrice.textContent = '0 EGP';
    return;
  }
  let total = 0;
  cart.forEach(item => {
    const itemTotal = item.price * item.quantity;
    total += itemTotal;
    const div = document.createElement('div');
    div.className = 'cart-item';
    div.innerHTML = `
      <div class="cart-item-info">
        <span class="cart-item-title">${localLanguage === 'ar' ? item.name_ar : item.name_en}</span>
        <div class="qty-control" style="display:flex; align-items:center; gap:10px; margin-top:5px;">
          <button class="qty-btn" onclick="adjustCartQty(${item.id}, -1)" style="width:24px; height:24px; border-radius:50%; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:#fff; cursor:pointer; font-weight:bold; display:flex; align-items:center; justify-content:center;">-</button>
          <span class="cart-item-qty">${item.quantity}</span>
          <button class="qty-btn" onclick="adjustCartQty(${item.id}, 1)" style="width:24px; height:24px; border-radius:50%; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:#fff; cursor:pointer; font-weight:bold; display:flex; align-items:center; justify-content:center;">+</button>
        </div>
      </div>
      <span class="cart-item-price">${itemTotal} EGP</span>`;
    cartItemsList.appendChild(div);
  });
  cartTotalPrice.textContent = `${total.toFixed(2)} EGP`;

  const cartStr = `https://example.com/checkout?order=${currentOrderUid}`;
  new QRious({ element: document.getElementById('cart-qrcode'), value: cartStr, size: 150 });
}

window.adjustCartQty = async function (productId, delta) {
  const existingIndex = cart.findIndex(c => c.id === productId);
  if (existingIndex === -1) return;

  const newQty = cart[existingIndex].quantity + delta;

  // Local state update
  if (newQty <= 0) {
    cart.splice(existingIndex, 1);
  } else {
    cart[existingIndex].quantity = newQty;
  }

  // Update badge
  updateCartBadge();

  // Sync to database via PUT
  try {
    await HoloApi.updateOrderItem(currentOrderUid, productId, newQty);
  } catch (e) {
    console.warn('Could not sync cart update to DB:', e);
  }

  synth.click();
  renderCartItems();
};

function selectProduct() {
  if (gestureCooldownActive) return;
  triggerCooldown();
  const item = products[currentProductIndex];
  qrProductTitle.textContent = localLanguage === 'ar' ? item.name_ar : item.name_en;
  qrProductUrl.textContent = item.qr_order_url || `https://example.com/order/${item.id}`;
  new QRious({ element: document.getElementById('product-qrcode'), value: item.qr_order_url || '', size: 200 });
  productQrModal.classList.remove('hidden');
  synth.success();
  triggerHudNotification('PINCH SELECT', '👌');
}

function generateConfirmQR(url) {
  new QRious({ element: document.getElementById('confirm-qrcode'), value: url, size: 200 });
}

function startReturnToIdleCountdown() {
  let elapsed = 0;
  const step = 100;
  countdownFill.style.transition = `width ${RETURN_TO_IDLE_MS}ms linear`;
  countdownFill.style.width = '100%';
  setTimeout(() => {
    transitionTo(STATE.IDLE, { cancel: false });
  }, RETURN_TO_IDLE_MS);
}

// ─── HUD Notification ─────────────────────────────────────────────────────────
function triggerHudNotification(text, emoji) {
  gestureHud.querySelector('.hud-emoji').textContent = emoji;
  gestureHud.querySelector('.hud-text').textContent = text;
  gestureHud.classList.add('active');
  setTimeout(() => gestureHud.classList.remove('active'), 1200);
}

// ─── Language Toggle ──────────────────────────────────────────────────────────
function toggleLanguage() {
  localLanguage = localLanguage === 'en' ? 'ar' : 'en';
  document.documentElement.setAttribute('lang', localLanguage);
  document.documentElement.setAttribute('dir', localLanguage === 'ar' ? 'rtl' : 'ltr');
  document.querySelectorAll('[data-en]').forEach(el => {
    el.textContent = localLanguage === 'ar' ? el.getAttribute('data-ar') : el.getAttribute('data-en');
  });
  if (products.length) updateProductDisplay();
  synth.click();
}

// ─── Hand Pointer ────────────────────────────────────────────────────────────
function updateHandPointer(x, y, ftx, fty, state) {
  const activePointer = currentState === STATE.DEPARTMENT_SELECT ? handPointer : handPointerProd;

  // Move pointer
  activePointer.style.left = `${x * window.innerWidth}px`;
  activePointer.style.top = `${y * window.innerHeight}px`;
  activePointer.classList.add('active');

  activePointer.style.color = state === 'pinch' ? 'var(--glow-color-primary)'
    : state === 'fist' ? '#ff0055'
      : state === 'thumbs_up' ? 'var(--glow-color-accent)'
        : 'var(--glow-color-secondary)';

  clearTimeout(activePointer.hideTimeout);
  activePointer.hideTimeout = setTimeout(() => activePointer.classList.remove('active'), 2000);

  // Dwell-click update with fingertip
  if (ftx !== undefined && fty !== undefined) {
    updateDwellCursor(ftx, fty);
  }

  resetInactivityTimer();
}

// ─── WebSocket ───────────────────────────────────────────────────────────────
let wsSeq = 0;

function getDeviceId() {
  let deviceId = localStorage.getItem('holo_device_id');
  if (!deviceId) {
    deviceId = 'device-' + Math.random().toString(36).substr(2, 9) + '-' + Date.now();
    localStorage.setItem('holo_device_id', deviceId);
  }
  return deviceId;
}

function showPairingOverlay(errorMsg = '') {
  const overlay = document.getElementById('pairing-overlay');
  if (overlay) overlay.classList.remove('hidden');
  const errEl = document.getElementById('pairing-error');
  if (errEl) {
    if (errorMsg) {
      errEl.textContent = errorMsg;
      errEl.style.display = 'block';
    } else {
      errEl.style.display = 'none';
    }
  }
}

function sendWsCmd(cmd) {
  wsSeq++;
  HoloWs.send({ cmd, seq: wsSeq });
}

function setConnectionStatus(connected) {
  const cls = connected ? 'status-connected' : 'status-disconnected';
  const text = connected ? 'Vision Live' : 'Client Idle';
  const simText = connected ? 'Connected' : 'Disconnected';
  const simClass = connected ? 'text-connected' : 'text-disconnected';

  [connStatusBadge, deptConnBadge].forEach(el => { if (el) el.className = `status-badge ${cls}`; });
  [connStatusText, deptStatusText].forEach(el => { if (el) el.textContent = text; });
  simStatusLabel.textContent = simText;
  simStatusLabel.className = simClass;
}

function connectWebSocket(url) {
  const token = localStorage.getItem('holo_ws_token');
  const deviceId = getDeviceId();
  wsSeq = 0;

  HoloWs.connect(
    url,
    token,
    deviceId,
    (data) => handleWSEvent(data),
    (connected) => {
      setConnectionStatus(connected);
      if (connected) {
        wsSeq = 0;
        const overlay = document.getElementById('pairing-overlay');
        if (overlay) overlay.classList.add('hidden');
      }
    },
    (code, reason) => {
      setConnectionStatus(false);
      showPairingOverlay(reason || 'WebSocket authentication failed');
    }
  );
}

function handleWSEvent(data) {
  // Engine mode changes from backend
  if (data.event === 'engine_mode') {
    console.log(`Engine mode: ${data.mode}`);
    HoloHud.updateHealth({ mode: data.mode });
    return;
  }

  // Engine health status
  if (data.event === 'health_status') {
    HoloHud.updateHealth(data);
    // Console warnings for failures
    if (!data.camera_ok) console.warn('[HoloMenu] ⚠️ Camera is NOT open — check device_index in config.json');
    if (!data.mediapipe_ok) console.warn('[HoloMenu] ⚠️ MediaPipe is NOT available — pip install mediapipe');
    if (data.mode === 'active' && !data.hand_detected) console.warn('[HoloMenu] ⚠️ Active mode but no hand detected — check camera angle/lighting');
    return;
  }

  // Inactivity timeout from backend
  if (data.event === 'session_timeout') {
    triggerHudNotification('SESSION TIMEOUT', '⏱️');
    transitionTo(STATE.IDLE);
    return;
  }

  // Hand pointer
  if (data.event === 'pointer') {
    updateHandPointer(data.x, data.y, data.fingertip_x, data.fingertip_y, data.state);
    // Update hand status in HUD on every pointer frame
    HoloHud.updateHandStatus(true);
    return;
  }

  // Gesture events
  if (data.event === 'gesture' || data.event === 'ui_click') {
    const gesture = data.gesture || (data.event === 'ui_click' ? 'UI_CLICK' : null);
    if (!gesture) return;

    // Update gesture name in HUD
    HoloHud.updateGesture(gesture);
    console.log(`[HoloMenu] Gesture received: ${gesture} (state: ${currentState})`);

    resetInactivityTimer();

    // Route gesture based on current state
    switch (currentState) {
      case STATE.IDLE:
        // Only start order matters here
        break;

      case STATE.DEPARTMENT_SELECT:
        if (gesture === 'CLOSED_FIST') transitionTo(STATE.IDLE);
        break;

      case STATE.PRODUCT_BROWSE:
        if (gesture === 'SWIPE_LEFT') handleSwipe('LEFT');
        else if (gesture === 'SWIPE_RIGHT') handleSwipe('RIGHT');
        else if (gesture === 'OPEN_PALM') { transitionTo(STATE.PRODUCT_DETAILS); triggerHudNotification('DETAILS ON', '✋'); }
        else if (gesture === 'PINCH') selectProduct();
        else if (gesture === 'THUMBS_UP') addToCart();
        else if (gesture === 'CLOSED_FIST') transitionTo(STATE.DEPARTMENT_SELECT);
        break;

      case STATE.PRODUCT_DETAILS:
        if (gesture === 'CLOSED_FIST') { transitionTo(STATE.PRODUCT_BROWSE); toggleDetailsPanel(false); triggerHudNotification('DETAILS OFF', '✊'); }
        else if (gesture === 'THUMBS_UP') addToCart();
        else if (gesture === 'SWIPE_LEFT') { handleSwipe('LEFT'); }
        else if (gesture === 'SWIPE_RIGHT') { handleSwipe('RIGHT'); }
        break;

      case STATE.CART:
      case STATE.ORDER_CONFIRM:
        if (gesture === 'CLOSED_FIST') { cartModal.classList.add('hidden'); transitionTo(STATE.PRODUCT_BROWSE); }
        break;
    }
  }
}

// ─── Simulator ───────────────────────────────────────────────────────────────
function initSimulator() {
  simToggleBtn.addEventListener('click', () => simDrawer.classList.toggle('collapsed'));
  simBtnConnect.addEventListener('click', () => connectWebSocket(simWsUrlInput.value));

  simStartOrder.addEventListener('click', () => {
    sendWsCmd('start_order');
    if (currentState === STATE.IDLE) transitionTo(STATE.DEPARTMENT_SELECT);
  });

  simEndSession.addEventListener('click', () => {
    sendWsCmd('end_session');
    transitionTo(STATE.IDLE);
  });

  simCoordsPad.addEventListener('mousemove', (e) => {
    const rect = simCoordsPad.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    simCursor.style.left = `${x * 100}%`;
    simCursor.style.top = `${y * 100}%`;
    simCoordXVal.textContent = x.toFixed(2);
    simCoordYVal.textContent = y.toFixed(2);
    updateHandPointer(x, y, x, y, 'open');
  });

  simCoordsPad.addEventListener('mouseleave', () => {
    handPointer.classList.remove('active');
    handPointerProd.classList.remove('active');
  });

  document.querySelectorAll('.sim-action-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      handleWSEvent({ event: 'gesture', gesture: btn.dataset.gesture });
    });
  });
}

// ─── Fallback data (when API unavailable) ────────────────────────────────────
const FALLBACK_DEPTS = [
  { id: 1, name_en: 'Burgers', name_ar: 'برجر' },
  { id: 2, name_en: 'Sides', name_ar: 'مقبلات' },
  { id: 3, name_en: 'Drinks', name_ar: 'مشروبات' },
  { id: 4, name_en: 'Desserts', name_ar: 'حلويات' },
];

const FALLBACK_PRODUCTS = [
  {
    id: 1, name_en: 'Holo Classic Burger', name_ar: 'هولو برجر كلاسيك',
    description_en: 'Premium double beef patty with aged cheddar.', description_ar: 'شريحتان لحم فاخرتان مع جبن شيدر معتق.',
    price: 180, currency: 'EGP', ingredients: ['Beef Patty', 'Cheddar', 'Sauce'], calories: 720,
    allergens: ['Gluten', 'Dairy'], media_path: 'assets/images/burger.png', qr_order_url: 'https://example.com/order/1'
  },
  {
    id: 2, name_en: 'Neon Loaded Fries', name_ar: 'بطاطس نيون لودد',
    description_en: 'Crispy fries with cheese sauce.', description_ar: 'بطاطس مقرمشة بصلصة الجبن.',
    price: 95, currency: 'EGP', ingredients: ['Fries', 'Cheese Sauce'], calories: 480,
    allergens: ['Dairy'], media_path: 'assets/images/fries.png', qr_order_url: 'https://example.com/order/2'
  },
  {
    id: 3, name_en: 'Blue Mojito', name_ar: 'موهيتو أزرق',
    description_en: 'Refreshing mocktail.', description_ar: 'موكتيل منعش.',
    price: 75, currency: 'EGP', ingredients: ['Blue Curaçao', 'Lime', 'Mint'], calories: 150,
    allergens: [], media_path: 'assets/images/mojito.png', qr_order_url: 'https://example.com/order/3'
  },
  {
    id: 4, name_en: 'Cyber Lava Cake', name_ar: 'كيكة الحمم السيبرانية',
    description_en: 'Warm chocolate cake.', description_ar: 'كيكة شوكولاتة دافئة.',
    price: 110, currency: 'EGP', ingredients: ['Cocoa', 'Dark Chocolate'], calories: 540,
    allergens: ['Gluten', 'Dairy', 'Eggs'], media_path: 'assets/images/cake.png', qr_order_url: 'https://example.com/order/4'
  },
];

// ─── Bootstrap ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Initial state = IDLE
  transitionTo(STATE.IDLE, { cancel: false });

  // Start Order button
  startOrderBtn.addEventListener('click', () => transitionTo(STATE.DEPARTMENT_SELECT));

  // Back buttons
  backToDeptBtn.addEventListener('click', () => transitionTo(STATE.DEPARTMENT_SELECT));

  // Language
  [langToggleBtn, langToggleBtn2].forEach(btn => { if (btn) btn.addEventListener('click', toggleLanguage); });

  // Cart modals
  [cartIndicatorBtn, cartIndicatorBtn2].forEach(btn => { if (btn) btn.addEventListener('click', () => transitionTo(STATE.CART)); });
  closeCartBtn.addEventListener('click', () => { cartModal.classList.add('hidden'); currentState = STATE.PRODUCT_BROWSE; });
  closeProductQrBtn.addEventListener('click', () => productQrModal.classList.add('hidden'));
  addMoreBtn.addEventListener('click', () => { cartModal.classList.add('hidden'); transitionTo(STATE.DEPARTMENT_SELECT); });
  confirmOrderBtn.addEventListener('click', () => transitionTo(STATE.ORDER_CONFIRM));

  // Init simulator
  initSimulator();

  // Pairing Submit Listener
  const pairingSubmitBtn = document.getElementById('pairing-submit-btn');
  const pairingPinInput = document.getElementById('pairing-pin-input');
  const pairingError = document.getElementById('pairing-error');

  if (pairingSubmitBtn) {
    pairingSubmitBtn.addEventListener('click', async () => {
      const pin = pairingPinInput.value.trim();
      if (pin.length !== 6) {
        pairingError.textContent = 'Please enter a valid 6-digit PIN';
        pairingError.style.display = 'block';
        return;
      }
      pairingError.style.display = 'none';
      pairingSubmitBtn.disabled = true;
      pairingSubmitBtn.textContent = 'VERIFYING...';
      
      try {
        const deviceId = getDeviceId();
        const apiBase = typeof HoloApi !== 'undefined' ? HoloApi.API_BASE : 'http://127.0.0.1:8081/api';
        const response = await fetch(`${apiBase}/pairing/verify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin, device_id: deviceId })
        });
        
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || 'Pairing verification failed');
        }
        
        localStorage.setItem('holo_ws_token', data.token);
        pairingPinInput.value = '';
        pairingSubmitBtn.disabled = false;
        pairingSubmitBtn.textContent = 'SUBMIT PAIRING PIN';
        
        document.getElementById('pairing-overlay').classList.add('hidden');
        connectWebSocket(simWsUrlInput.value);
      } catch (err) {
        pairingError.textContent = err.message;
        pairingError.style.display = 'block';
        pairingSubmitBtn.disabled = false;
        pairingSubmitBtn.textContent = 'SUBMIT PAIRING PIN';
      }
    });
  }

  // Connect to WebSocket (auto)
  setTimeout(() => connectWebSocket(simWsUrlInput.value), 500);
});
