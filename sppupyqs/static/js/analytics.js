(function () {
  'use strict';

  const GOOGLE_ANALYTICS_ID = 'G-HSZBTND87R';
  const CLARITY_PROJECT_ID = 'wnwgewvz6t';
  const hostname = window.location.hostname;
  const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';

  if (isLocal) return;

  initGoogleAnalytics(GOOGLE_ANALYTICS_ID);
  initClarity(CLARITY_PROJECT_ID);

  function initGoogleAnalytics(measurementId) {
    if (window.__GA_LOADED__) return;
    window.__GA_LOADED__ = true;

    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () {
      window.dataLayer.push(arguments);
    };

    const s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(measurementId);
    s.addEventListener('load', function () {
      window.gtag('js', new Date());
      window.gtag('config', measurementId);
    }, { once: true });
    document.head.appendChild(s);
  }

  function initClarity(projectId) {
    if (window.__CLARITY_LOADED__) return;
    window.__CLARITY_LOADED__ = true;

    (function (c, l, a, r, i, t, y) {
      c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
      t = l.createElement(r);
      t.async = 1;
      t.src = 'https://www.clarity.ms/tag/' + i;
      y = l.getElementsByTagName(r)[0];
      y.parentNode.insertBefore(t, y);
    })(window, document, 'clarity', 'script', projectId);
  }
})();
