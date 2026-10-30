// クリックジャッキング ステージウィンドウ JS (CSP 対応: 外部ファイル)
// ★ クロスブラウザ対応: URLパラメータ (?x=0&y=-220&opacity=5) を最優先で読む。
//    postMessage はコントロールパネルと同じブラウザで開いた場合のリアルタイム調整用。

var frame   = document.getElementById('victim-frame');
var blocked = document.getElementById('blocked-msg');

// ── ① URLパラメータから初期値を設定 ─────────────────────────────────
(function applyUrlParams() {
  var p       = new URLSearchParams(window.location.search);
  var x       = +(p.get('x')       ?? 0);
  var y       = +(p.get('y')       ?? -220);
  var opacity = +(p.get('opacity') ?? 5);
  frame.style.opacity   = opacity / 100;
  frame.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
})();

// ── ② iframe ロード後: 同一ブラウザの opener に通知 ─────────────────
frame.addEventListener('load', function () {
  try {
    if (frame.contentDocument) {
      blocked.classList.remove('show');
    }
  } catch (e) {
    blocked.classList.add('show');
  }
  // 同一ブラウザで開いた場合のみ有効（クロスブラウザでは opener=null なので何もしない）
  if (window.opener && !window.opener.closed) {
    window.opener.postMessage({ type: 'cj-ready' }, '*');
  }
});

frame.addEventListener('error', function () {
  blocked.classList.add('show');
});

// ── ③ コントロールパネルからの postMessage (同一ブラウザのみ) ────────
window.addEventListener('message', function (e) {
  if (!e.data || e.data.type !== 'cj-update') return;

  var opacity = e.data.opacity != null ? e.data.opacity : 5;
  var x       = e.data.x       != null ? e.data.x       : 0;
  var y       = e.data.y       != null ? e.data.y       : -220;

  frame.style.opacity   = opacity / 100;
  frame.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
  // ★ デコイボタンは動かさない —— iframeだけを動かして削除ボタンを合わせる
});
