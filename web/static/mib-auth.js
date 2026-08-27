/* MIB WebView entry point.
 *
 * MIB opens this page with ?access_token=...&return_uri=...&x_app_install_id=...
 * (see forte-mib3-webview's src/shared/views/mib3loader/index.tsx — this
 * mirrors it 1:1). access_token is short-lived and only good for this
 * exchange; the fetch below trades it for a long-life session by calling
 * Auth's /oauth/token directly from the browser with credentials: 'include',
 * so the Keycloak cookie the response sets lands in this browser's own
 * cookie jar. A backend proxy for this call would get the Set-Cookie
 * instead of the browser, which is why this runs client-side rather than
 * through web/app.py.
 */
(function () {
  var cfg = window.MIB_AUTH_CONFIG || {};
  var statusEl = document.getElementById('status');

  var params = new URLSearchParams(window.location.search);
  var accessToken = params.get('access_token');
  var returnUri = params.get('return_uri');
  var xAppInstallId = params.get('x_app_install_id');
  var lang = params.get('lang');

  if (xAppInstallId) {
    localStorage.setItem('x-app-install-id', xAppInstallId);
  }
  if (lang) {
    localStorage.setItem('locale', lang);
  }

  if (!accessToken) {
    if (statusEl) statusEl.textContent = 'access_token отсутствует';
    return;
  }

  var tokenParams = new URLSearchParams({
    grant_type: 'exchange',
    client_id: cfg.clientId || '',
    client_secret: cfg.clientSecret || '',
    scope: 'offline_access',
    redirect_uri: cfg.redirectUri || '',
    subject_token: accessToken,
    return_uri: returnUri || '',
  });

  var requestId =
    window.crypto && window.crypto.randomUUID
      ? window.crypto.randomUUID()
      : String(Date.now()) + '-' + Math.random().toString(16).slice(2);

  fetch((cfg.url || '') + 'oauth/token?' + tokenParams.toString(), {
    method: 'GET',
    headers: {
      'X-App-Install-Id': xAppInstallId || '',
      'X-Request-Id': requestId,
    },
    credentials: 'include',
  })
    .catch(function (err) {
      console.error('MIB auth exchange failed', err);
    })
    .finally(function () {
      window.location.replace(returnUri || '/');
    });
})();
