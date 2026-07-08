# HoloMenu Project Architecture Guide

This document defines the system-wide architecture for HoloMenu, covering the structural relationships and boundaries between the **Frontend**, the **Gesture Recognition Engine**, and the **FastAPI Backend**.

---

## 1. System Topology & Boundaries

HoloMenu consists of three independent components collaborating over standard local networking boundaries:

```
                  ┌──────────────────────────────┐
                  │       Customer Kiosk         │
                  │   & Staff Operator Portal    │
                  │   (Frontend - Static Web)    │
                  └──────┬────────────────┬──────┘
                         │                │
             HTTP REST   │                │ WebSocket WS
             (Port 8081) │                │ (Port 8766)
                         ▼                ▼
        ┌──────────────────┐            ┌──────────────────┐
        │  FastAPI Backend │            │  Gesture Engine  │
        │   (MySQL DB)     │            │ (MediaPipe / CV) │
        └──────────────────┘            └──────────────────┘
```

### Network Boundaries:
1. **REST API Interface (Port 8081)**:
   * Used by Kiosk and Operator portals (Chef, Cashier, Admin, Portal) to load menu configurations, handle order lifecycles, pay orders, fetch analytics, and query server health.
   * Standard JSON payload structures with JWT authorization token validation.
2. **WebSocket Interface (Port 8766)**:
   * A continuous duplex link between the Customer Kiosk and the Gesture Engine.
   * Broadcasts frame-by-frame hand tracker coordinates (`pointer` events), active gestures (`gesture` events), and camera/MediaPipe health status frames.

---

## 2. Frontend Layered Design (Plain JavaScript)

To prevent code duplication, shared functionalities have been extracted into reusable vanilla JS modules in `assets/js/`:

* **`assets/js/api-client.js` (`HoloApi`)**:
  * Unified service wrapper for all fetch requests. Defines `API_BASE` and handles credentials, REST paths, and response parsing.
* **`assets/js/websocket-client.js` (`HoloWs`)**:
  * Manages the raw browser WebSocket connection to the gesture recognition engine, including auto-reconnection attempts every 3 seconds if connectivity is interrupted.
* **`assets/js/engine-status-hud.js` (`HoloHud`)**:
  * Standardizes drawing and updating the visual HUD indicator tracking camera access, MediaPipe state, and active gesture tracking on the screen.
* **`events.js` (`HoloEvents`)**:
  * Listens to Server-Sent Events (SSE) from the backend `/api/events/stream` and runs polling fallback loops if the connection drops.

### Adding Features to the Frontend:
* **Page-Specific Logic**: Put it inside the page's HTML file script tag (e.g. `chef.html` or `cashier.html`) or in the corresponding script file (e.g., `app.js` for the customer kiosk).
* **Global API Endpoints**: Add a method to `HoloApi` in `assets/js/api-client.js`.

---

## 3. Gesture Recognition Engine Architecture

The Gesture Engine is organized as a modular package in `gesture_engine/`:

* **`gesture_engine/main.py`**: The main orchestrator. Bootstraps the OpenCV video acquisition loop and coordinates frames with the MediaPipe classifier.
* **`gesture_engine/config/settings.py`**: Settings loader containing gesture/camera thresholds, websocket port, and the MediaPipe landmarker task file download details.
* **`gesture_engine/vision/camera.py`**: Video capture lifecycle wrapper. Controls starting and stopping camera hardware dynamically based on session command events.
* **`gesture_engine/vision/hand_landmarker.py`**: Low-level MediaPipe Tasks model manager.
* **`gesture_engine/vision/gesture_classifier.py`**: A pure functional layer that processes geometric coordinates (landmarks) to label hand shapes. Free from side-effects (`cv2` or `websockets` imports).
* **`gesture_engine/transport/websocket_server.py`**: Manages websocket client sockets and frame/state broadcasting.
* **`gesture_engine/transport/commands.py`**: Parses commands received from clients (`start_order`, `end_session`).
* **`gesture_engine/state.py`**: Explicit, centralized tracking state variables (e.g. `ENGINE_MODE`, `pointer_state`).

### Adding Features to the Gesture Engine:
* **New Gestures**: Implement the logic in `gesture_engine/vision/gesture_classifier.py` (which takes landmarks coordinate lists).
* **New Network Commands**: Register the command payload parser in `gesture_engine/transport/commands.py`.

---

## 4. Backend Clean Architecture (FastAPI)

The backend follows the four classic layers of Clean Architecture:

* **Domain Layer (`backend/domain/`)**:
  * Core entities and invariant logic (e.g. `order_rules.py` transition asserts). Framework-agnostic.
* **Application Layer (`backend/application/`)**:
  * Use Cases matching system interactions (creating orders, calculating receipts, auditing).
  * Interface specifications (repositories like `order_repository.py`).
* **Infrastructure Layer (`backend/infrastructure/`)**:
  * Operational implementations: MySQL queries (`MysqlOrderRepo`), Sentry logging, Prometheus metrics, database connection pooling.
* **Interface Layer (`backend/interface/`)**:
  * Router handlers capturing incoming endpoints (`orders.py`, `chef.py`, `admin.py`) and FastAPI dependencies.

### Adding Features to the Backend:
1. **Domain Logic**: Update/create python models/validators in `backend/domain/`.
2. **Use Case / Interfaces**: Create/update contracts in `backend/application/interfaces/` and coordinate orchestration in `backend/application/use_cases/`.
3. **Database implementation**: Write the MySQL query logic inside `backend/infrastructure/database/` implementing your interface protocol.
4. **Endpoints**: Expose the route inside `backend/interface/routers/` using FastAPI route declarations.
