/**
 * AI-QMS Chainlit Connection Resilience v2.0
 * 三層備援: Socket.IO hooks → HTTP health poll → 頁面重載
 */
(function () {
  'use strict';

  var CFG = {
    healthCheckInterval: 4000,   // 每 4 秒輪詢 server 存活
    pingInterval: 20000,         // 每 20 秒發 keep-alive ping
    reconnectBaseDelay: 1500,    // 首次重連等待 ms
    reconnectMaxDelay: 20000,    // 最大等待 ms
    reconnectBackoff: 1.6,       // 指數退避係數
    socketHookRetries: 60,       // 嘗試找 socket 的次數 (×500ms = 30s)
    indicatorHideDelay: 4000,    // 「已恢復」提示幾 ms 後自動消失
  };

  var state = {
    attempts: 0,
    delay: CFG.reconnectBaseDelay,
    reconnecting: false,
    socketHooked: false,
  };

  /* ─── 浮動狀態指示器 ─── */
  var indicator = null;

  function getIndicator() {
    if (indicator) return indicator;
    indicator = document.createElement('div');
    indicator.id = 'qms-conn';
    indicator.style.cssText = [
      'position:fixed', 'bottom:20px', 'right:20px', 'z-index:2147483647',
      'padding:10px 16px', 'border-radius:10px',
      'font-family:"Microsoft JhengHei",Arial,sans-serif',
      'font-size:13px', 'font-weight:700',
      'display:none', 'align-items:center', 'gap:8px',
      'box-shadow:0 4px 16px rgba(0,0,0,.35)',
      'transition:opacity .3s', 'cursor:pointer',
    ].join(';');
    indicator.title = '點擊關閉';
    indicator.onclick = function () { indicator.style.display = 'none'; };
    document.body.appendChild(indicator);
    return indicator;
  }

  function showIndicator(type, msg) {
    var el = getIndicator();
    var styles = {
      reconnecting: ['#ef4444', '#fff', '⚡'],
      connected:    ['#10b981', '#fff', '✓'],
      waiting:      ['#f59e0b', '#fff', '⏳'],
      offline:      ['#6b7280', '#fff', '📡'],
    };
    var s = styles[type] || styles.waiting;
    el.style.background = s[0];
    el.style.color = s[1];
    el.innerHTML = s[2] + ' ' + msg;
    el.style.display = 'flex';
    if (type === 'connected') {
      setTimeout(function () { el.style.display = 'none'; }, CFG.indicatorHideDelay);
    }
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

  /* ─── 重連核心邏輯 ─── */
  function doReconnect() {
    if (state.reconnecting) return;
    state.reconnecting = true;
    state.attempts++;

    var delay = state.delay;
    state.delay = Math.min(state.delay * CFG.reconnectBackoff, CFG.reconnectMaxDelay);

    showIndicator('reconnecting',
      '連線中斷，重連中... (' + state.attempts + ')');

    setTimeout(function () {
      isServerAlive().then(function (alive) {
        if (alive) {
          // Server up: 嘗試讓 Socket.IO 重連，若 2s 內沒成功就 reload
          var sock = findSocket();
          if (sock && !sock.connected) {
            try { sock.connect(); } catch (e) {}
          }
          setTimeout(function () {
            var s2 = findSocket();
            if (s2 && s2.connected) {
              onReconnected();
            } else {
              location.reload();
            }
          }, 2000);
        } else {
          // Server 仍未回應，繼續等待
          showIndicator('waiting',
            '等待伺服器回應... (' + state.attempts + ')');
          state.reconnecting = false;
          setTimeout(doReconnect, delay);
        }
      });
    }, delay);
  }

  function onReconnected() {
    state.reconnecting = false;
    state.attempts = 0;
    state.delay = CFG.reconnectBaseDelay;
    showIndicator('connected', '連線已恢復');
  }

  /* ─── 尋找 Socket.IO 實例 ─── */
  function findSocket() {
    // Chainlit 2.x 將 socket 暴露在不同位置
    if (window.socket && typeof window.socket.on === 'function') return window.socket;
    if (window.__cl_socket) return window.__cl_socket;
    // 走 Socket.IO 全域管理器
    if (typeof window.io === 'function' && window.io.sockets) {
      var keys = Object.keys(window.io.sockets);
      if (keys.length) return window.io.sockets[keys[0]];
    }
    // 掃描 Chainlit React fiber 內部狀態 (最後手段)
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
    console.log('[QMS] Socket.IO hooked');

    sock.on('disconnect', function (reason) {
      console.log('[QMS] disconnect:', reason);
      if (reason !== 'io client disconnect' && !state.reconnecting) {
        setTimeout(doReconnect, 800);
      }
    });

    sock.on('connect', function () {
      console.log('[QMS] connected');
      if (state.attempts > 0) onReconnected();
    });

    sock.on('connect_error', function (err) {
      console.log('[QMS] connect_error:', err && err.message);
      if (!state.reconnecting) doReconnect();
    });
  }

  /* ─── 定期輪詢: 找到 socket 後掛鉤；作為備援也做 HTTP 健康檢查 ─── */
  var socketHookAttempts = 0;

  function startMonitoring() {
    // 嘗試掛鉤 Socket.IO
    var hookTimer = setInterval(function () {
      socketHookAttempts++;
      var sock = findSocket();
      if (sock) {
        hookSocket(sock);
        clearInterval(hookTimer);
      } else if (socketHookAttempts >= CFG.socketHookRetries) {
        clearInterval(hookTimer);
        console.log('[QMS] Socket not found after retries; using HTTP poll only');
      }
    }, 500);

    // HTTP 健康輪詢（兜底）
    setInterval(function () {
      if (state.reconnecting) return;
      var sock = findSocket();
      // 若 socket 存在且斷線 → 重連
      if (sock && !sock.connected) {
        doReconnect();
        return;
      }
      // 若 socket 找不到 → HTTP 檢查
      if (!sock) {
        isServerAlive().then(function (alive) {
          if (!alive && !state.reconnecting) doReconnect();
        });
      }
    }, CFG.healthCheckInterval);

    // Keep-alive ping（防止 WebSocket idle timeout）
    setInterval(function () {
      var sock = findSocket();
      if (sock && sock.connected) {
        try { sock.emit('client_keepalive', { ts: Date.now() }); } catch (e) {}
      }
    }, CFG.pingInterval);
  }

  /* ─── 瀏覽器事件 ─── */
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) {
      var sock = findSocket();
      if ((sock && !sock.connected) && !state.reconnecting) {
        console.log('[QMS] tab focus → reconnect check');
        doReconnect();
      }
    }
  });

  window.addEventListener('online', function () {
    console.log('[QMS] network online');
    if (!state.reconnecting) doReconnect();
  });

  window.addEventListener('offline', function () {
    showIndicator('offline', '網路中斷，等待網路恢復...');
  });

  /* ─── 啟動 ─── */
  function init() {
    startMonitoring();
    console.log('[QMS] Connection resilience v2.0 ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
