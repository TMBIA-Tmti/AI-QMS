/**
 * AI-QMS Chainlit Connection Resilience v2.3
 * 純後台靜默重連：不顯示任何提示，不自動 reload，不顯示手動按鈕
 *
 * v2.3 變更：
 *   - 移除所有 UI 指示器（showIndicator 變為純 console.log）
 *   - 所有重連嘗試完全在後台靜默進行
 *   - 30s 啟動保護期，頁面剛開啟時不觸發重連
 *   - 永不自動 location.reload()
 */
(function () {
  'use strict';

  var CFG = {
    healthCheckInterval: 6000,
    pingInterval: 25000,
    reconnectBaseDelay: 2000,
    reconnectMaxDelay: 30000,
    reconnectBackoff: 1.8,
    socketHookRetries: 60,
    startupGrace: 30000,
    socketReconnectWait: 5000,
  };

  var state = {
    attempts: 0,
    delay: CFG.reconnectBaseDelay,
    reconnecting: false,
    socketHooked: false,
    ready: false,
    startTime: Date.now(),
  };

  function isReady() {
    return state.ready || (Date.now() - state.startTime >= CFG.startupGrace);
  }

  /* ─── Server 存活探測 ─── */
  function isServerAlive() {
    return fetch(location.origin + '/', {
      method: 'HEAD',
      cache: 'no-store',
      signal: AbortSignal.timeout ? AbortSignal.timeout(3000) : undefined,
    }).then(function (r) { return r.ok || r.status < 500; })
      .catch(function () { return false; });
  }

  /* ─── 後台靜默重連（永不 reload，永不顯示 UI） ─── */
  function doReconnect() {
    if (!isReady()) return;
    if (state.reconnecting) return;
    state.reconnecting = true;
    state.attempts++;

    var delay = state.delay;
    state.delay = Math.min(state.delay * CFG.reconnectBackoff, CFG.reconnectMaxDelay);

    console.log('[QMS] reconnect attempt', state.attempts, 'delay=', delay);

    setTimeout(function () {
      isServerAlive().then(function (alive) {
        if (alive) {
          var sock = findSocket();
          if (sock && !sock.connected) {
            try { sock.connect(); } catch (e) {}
          }
          setTimeout(function () {
            var s2 = findSocket();
            if (s2 && s2.connected) {
              onReconnected();
            } else {
              // 繼續後台重試，不顯示任何提示
              state.reconnecting = false;
              setTimeout(doReconnect, state.delay);
            }
          }, CFG.socketReconnectWait);
        } else {
          state.reconnecting = false;
          setTimeout(doReconnect, delay);
        }
      });
    }, delay);
  }

  function onReconnected() {
    console.log('[QMS] reconnected after', state.attempts, 'attempts');
    state.reconnecting = false;
    state.attempts = 0;
    state.delay = CFG.reconnectBaseDelay;
  }

  /* ─── 尋找 Socket.IO 實例 ─── */
  function findSocket() {
    if (window.socket && typeof window.socket.on === 'function') return window.socket;
    if (window.__cl_socket) return window.__cl_socket;
    if (typeof window.io === 'function' && window.io.sockets) {
      var keys = Object.keys(window.io.sockets);
      if (keys.length) return window.io.sockets[keys[0]];
    }
    try {
      var root = document.getElementById('root') || document.querySelector('[data-testid]');
      if (root && root._reactFiber) {
        var fiber = root._reactFiber;
        for (var i = 0; i < 50 && fiber; i++, fiber = fiber.return) {
          if (fiber.memoizedState && fiber.memoizedState.queue &&
              fiber.memoizedState.queue.dispatch) {
            var ctx = fiber.memoizedProps && fiber.memoizedProps.value;
            if (ctx && ctx.socket) return ctx.socket;
          }
        }
      }
    } catch (e) {}
    return null;
  }

  /* ─── Hook Socket.IO 事件 ─── */
  function hookSocket(sock) {
    if (state.socketHooked) return;
    state.socketHooked = true;
    console.log('[QMS] socket hooked');

    sock.on('connect', function () {
      if (!state.ready) {
        state.ready = true;
        console.log('[QMS] initial connect OK, grace lifted');
      } else if (state.attempts > 0) {
        onReconnected();
      }
    });

    sock.on('disconnect', function (reason) {
      if (!isReady()) return;
      if (reason !== 'io client disconnect' && !state.reconnecting) {
        setTimeout(doReconnect, 800);
      }
    });

    sock.on('connect_error', function (err) {
      if (!isReady()) return;
      if (!state.reconnecting) doReconnect();
    });
  }

  /* ─── 監控循環 ─── */
  var socketHookAttempts = 0;

  function startMonitoring() {
    var hookTimer = setInterval(function () {
      socketHookAttempts++;
      var sock = findSocket();
      if (sock) {
        hookSocket(sock);
        clearInterval(hookTimer);
      } else if (socketHookAttempts >= CFG.socketHookRetries) {
        clearInterval(hookTimer);
      }
    }, 500);

    setInterval(function () {
      if (!isReady() || state.reconnecting) return;
      var sock = findSocket();
      if (sock && !sock.connected) { doReconnect(); return; }
      if (!sock) {
        isServerAlive().then(function (alive) {
          if (!alive && !state.reconnecting) doReconnect();
        });
      }
    }, CFG.healthCheckInterval);

    setInterval(function () {
      var sock = findSocket();
      if (sock && sock.connected) {
        try { sock.emit('client_keepalive', { ts: Date.now() }); } catch (e) {}
      }
    }, CFG.pingInterval);
  }

  /* ─── 瀏覽器事件（靜默） ─── */
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && isReady()) {
      var sock = findSocket();
      if (sock && !sock.connected && !state.reconnecting) doReconnect();
    }
  });

  window.addEventListener('online', function () {
    if (!isReady() || state.reconnecting) return;
    doReconnect();
  });

  /* ─── 啟動 ─── */
  function init() {
    startMonitoring();
    console.log('[QMS] resilience v2.3 ready (silent mode, grace=' + CFG.startupGrace / 1000 + 's)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
