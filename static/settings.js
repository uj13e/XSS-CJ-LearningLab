// CSP 対応: インラインイベントハンドラの代わりに外部ファイルからバインド
// script-src 'self' が有効な状態でもこのファイルは許可される
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.toggle input[type=checkbox]').forEach(function (cb) {
    cb.addEventListener('change', function () {
      this.closest('form').submit();
    });
  });
});
