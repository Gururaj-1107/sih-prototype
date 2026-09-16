/**
 * CashOut Forecast - Global Environment & API Configuration
 * Supports local development and production deployments (Render backend / Firebase frontend).
 */
window.APP_CONFIG = {
  // If running in production (e.g. Firebase Hosting), point to Render backend URL.
  // Otherwise, default to current origin or localhost:8000.
  API_BASE_URL: (function() {
    // 1. Check if user configured an explicit override in localStorage
    const override = localStorage.getItem("CASHOUT_API_BASE_URL");
    if (override) return override;

    // 2. Check current hostname
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return window.location.port === "8000" ? "" : "http://localhost:8000";
    }

    // 3. Deployed frontend (e.g. *.web.app, *.firebaseapp.com, or custom domain)
    // You can customize your Render backend URL below:
    return window.RENDER_BACKEND_URL || "https://cashout-forecast-api.onrender.com";
  })(),

  VERSION: "2.1.0-SIH2026",
  SIMULATION_MODE: true,
  PLATFORM_NAME: "CashOut Forecast — Controlled Decoy Intelligence",
};

console.log("[Config] Loaded API Base URL:", window.APP_CONFIG.API_BASE_URL);
