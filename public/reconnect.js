/**
 * AI-QMS Chainlit Connection Resilience v2.2
 * 三層備援: Socket.IO hooks → HTTP health poll → 手動重整提示
 *
 * v2.1 修正：加入「啟動保護期」，首次 connect 成功前不觸發重連
 * v2.2 修正：移除自動 location.reload()
 *   - 自動重整會清除 Chainlit 對話內容，改為持續嘗試重連 Socket.IO
 *   - 只在使用者手動點擊「重新整理」按鈕時才 reload
 *   - 保護期間（首次連線成功前）完全忽略所有重連觸發
 */
(function () {
  'use strict';

  var CFG = {
    healthCheckInterval: 6000,   // 每 6 秒輪詢 server 存活
    pingInterval: 25000,         // 每 25 秒發 keep-alive ping
    reconnectBaseDelay: 2000,    // 首次重連等待 ms
    reconnectMaxDelay: 30000,    // 最大等待 ms（30 秒）
    reconnectBackoff: 1.8,       // 指數退避係數
    socketHookRetries: 60,       // 嘗試找 socket 的次數 (×500ms = 30s)
    indicatorHideDelay: 4000,    // 「已恢復」提示幾 ms 後自動消失
    startupGrace: 30000,         // 啟動保護期上限 ms（首次連線成功前不重連）
    socketReconnectWait: 5000,   // 等待 Socket.IO 自行重連的時間（ms）
  };

  var state = {
    attempts: 0,
    delay: CFG.reconnectBaseDelay,
    reconnecting: false,
    socketHooked: false,
    // 啟動保護：首次 connect 成功前為 false
    ready: false,
    startTime: Date.now(),
  };

  /* 是否已過啟動保護期 */
  function isReady() {
    return state.ready || (Date.now() - state.startTime >= CFG.startupGrace);
  }

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
      'transition:opacity .3s',
    ].join(';');
    document.body.appendChild(indicator);
    return indicator;
  }

  function showIndicator(type, msg, showReloadBtn) {
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

    var html = '<span>' + s[2] + ' ' + msg + '</span>';
    if (showReloadBtn) {
      // 手動重整按鈕 — 使用者主動選擇才 reload，避免自動清除對話
      html += '<button onclick="location.reload()" style="'
        + 'margin-left:10px;padding:3px 10px;border:none;border-radius:6px;'
        + 'background:#fff;color:#ef4444;font-weight:700;cursor:pointer;font-size:12px'
        + '">重新整理</button>';
    } else {
      // 無重整按鈕時點擊關閉
      el.onclick = function () { el.style.display = 'none'; };
      el.style.cursor = 'pointer';
      el.title = '點擊關閉';
    }

    el.innerHTML = html;
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

  /* ─── 重連核心邏輯（不再自動 reload） ─── */
  function doReconnect() {
    if (!isReady()) {
      console.log('[QMS] startup grace — reconnect suppressed');
      return;
    }
    if (state.reconnecting) return;
    state.reconnecting = true;
    state.attempts++;

    var delay = state.delay;
    state.delay = Math.min(state.delay * CFG.reconnectBackoff, CFG.reconnectMaxDelay);

    showIndicator('reconnecting', '連線中斷，重連中... (' + state.attempts + ')');

    setTimeout(function () {
      isServerAlive().then(function (alive) {
        if (alive) {
          // Server up → 嘗試讓 Socket.IO 自行重連
          var sock = findSocket();
          if (sock && !sock.connected) {
            try { sock.connect(); } catch (e) {}
          }

          // 等待一段時間看 Socket.IO 能否重連成功
          setTimeout(function () {
            var s2 = findSocket();
            if (s2 && s2.connected) {
              // Socket.IO 重連成功
              onReconnected();
            } else {
              // Socket.IO 無法重連 → 持續顯示提示 + 提供手動重整按鈕
              // 不自動 reload，避免清除對話內容
              showIndicator('reconnecting',
                '無法自動重連 (' + state.attempts + ')，繼續嘗試中...',
                state.attempts >= 5  // 嘗試 5 次後才顯示重整按鈕
              );
              state.reconnecting = false;
              setTimeout(doReconnect, state.delay);
            }
          }, CFG.socketReconnectWait);

        } else {
          // Server 未回應 → 繼續等待，不 reload
          showIndicator('waiting', '等待伺服器回應... (' + state.attempts + ')');
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
    console.log('[QMS] Socket.IO hooked');

    sock.on('connect', function () {
      console.log('[QMS] connected');
      if (!state.ready) {
        state.ready = true;
        console.log('[QMS] startup grace lifted — reconnect now active');
      } else if (state.attempts > 0) {
        onReconnected();
      }
    });

    sock.on('disconnect', function (reason) {
      console.log('[QMS] disconnect:', reason);
      if (!isReady()) {
        console.log('[QMS] startup grace — disconnect ignored');
        return;
      }
      if (reason !== 'io client disconnect' && !state.reconnecting) {
        setTimeout(doReconnect, 800);
      }
    });

    sock.on('connect_error', function (err) {
      console.log('[QMS] connect_error:', err && err.message);
      if (!isReady()) {
        console.log('[QMS] startup grace — connect_error ignored');
        return;
      }
      if (!state.reconnecting) doReconnect();
    });
  }

  /* ─── 定期輪詢 ─── */
  var socketHookAttempts = 0;

  function startMonitoring() {
    // 嘗試掛鉤 Socket.IO（啟動期也執行以監聽首次 connect）
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

    // HTTP 健康輪詢（兜底）— 啟動保護期內跳過
    setInterval(function () {
      if (!isReady()) return;
      if (state.reconnecting) return;
      var sock = findSocket();
      if (sock && !sock.connected) {
        doReconnect();
        return;
      }
      if (!sock) {
        isServerAlive().then(function (alive) {
          if (!alive && !state.reconnecting) doReconnect();
        });
      }
    }, CFG.healthCheckInterval);

    // Keep-alive ping
    setInterval(function () {
      var sock = findSocket();
      if (sock && sock.connected) {
        try { sock.emit('client_keepalive', { ts: Date.now() }); } catch (e) {}
      }
    }, CFG.pingInterval);
  }

  /* ─── 瀏覽器事件 ─── */
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && isReady()) {
      var sock = findSocket();
      if (sock && !sock.connected && !state.reconnecting) {
        console.log('[QMS] tab focus → reconnect check');
        doReconnect();
      }
    }
  });

  // window.online 在頁面初始載入時也會觸發，保護期內忽略
  window.addEventListener('online', function () {
    console.log('[QMS] network online');
    if (!isReady()) {
      console.log('[QMS] startup grace — online event ignored');
      return;
    }
    if (!state.reconnecting) doReconnect();
  });

  window.addEventListener('offline', function () {
    showIndicator('offline', '網路中斷，等待網路恢復...');
  });

  /* ─── 啟動 ─── */
  function init() {
    startMonitoring();
    console.log('[QMS] Connection resilience v2.2 ready (no auto-reload, startup grace: '
      + CFG.startupGrace / 1000 + 's)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
