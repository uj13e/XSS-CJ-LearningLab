"""
Stored XSS PoC デモアプリケーション
====================================
【重要】教育・許可された検証(自分の管理下にある環境でのセキュリティ学習)専用です。
公開サーバーには絶対に設置しないでください。自分が所有・管理していない、
または書面で許可を得ていないシステムに対して使用しないでください。

意図的に脆弱にしたゲストブック(掲示板)アプリケーションです。
以下4点のstored XSSの実害を再現します。
  1. セッションCookieの窃取
  2. 被害者IPアドレスの記録
  3. ページの改ざん(デフェイス)
  4. GPS位置情報の窃取(Geolocation API)

詳細な手順は README.md を参照してください。
"""

from flask import Flask, request, render_template, redirect, url_for, make_response
import datetime
import secrets
import json
import os
import re
import random
import threading
import time

app = Flask(__name__)

# --- ファイルDB (同ディレクトリに JSON ファイルで保存) --------------------
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE  = os.path.join(BASE_DIR, "messages.json")
LOOT_FILE      = os.path.join(BASE_DIR, "loot.json")
SETTINGS_FILE  = os.path.join(BASE_DIR, "settings.json")


def _load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ #
# 対策設定 (settings.json で永続化)                                    #
# ------------------------------------------------------------------ #
DEFAULT_SETTINGS = {
    "httponly":        False,
    "escape":          False,
    "sanitize":        False,
    "csp":             False,
    "samesite_strict": False,
    "x_frame_options": False,
}


def _load_settings() -> dict:
    s = DEFAULT_SETTINGS.copy()
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s.update(json.load(f))
    return s


def _save_settings(s: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def _strip_tags(text: str) -> str:
    """HTMLタグをすべて除去するシンプルなサニタイザー。"""
    return re.sub(r"<[^>]+>", "", text)


# ------------------------------------------------------------------ #
# デモ用アカウント                                                      #
# ------------------------------------------------------------------ #
ACCOUNTS = {
    "admin": {"password": "Admin@2024", "role": "admin", "prefix": "adm_"},
    "staff": {"password": "Staff@2024", "role": "staff", "prefix": "stf_"},
    "user":  {"password": "User@2024",  "role": "user",  "prefix": "usr_"},
    # guest はパスワードなし — /guest-login ルートでランダムトークンを発行
}

# ログイン済みセッション: token → username (再起動でリセット)
SESSIONS: dict = {}

# 削除済みアカウント (in-memory; /reset またはサーバー再起動で復元)
DELETED_ACCOUNTS: set = set()

# ------------------------------------------------------------------ #
# Bot 会話スクリプト（4パターン・ランダム選択）                         #
# 通常ユーザーと見分けがつかない自然な日本語で投稿される               #
# ------------------------------------------------------------------ #
BOT_SCRIPTS = [
    # ── Script 1: ランチ・日常の雑談 ─────────────────────────────────
    [
        ("田中 浩",    "おはようございます！"),
        ("鈴木 みゆき", "おはようございます〜！今日もいい天気ですね"),
        ("佐藤 大輔",  "おはようございます。少し蒸し暑いですね"),
        ("田中 浩",    "昨日より気温が上がってるみたいですよ。午後は30度超えそうで"),
        ("鈴木 みゆき", "えー、それはつらい…。ところで今日のランチどうしますか？"),
        ("佐藤 大輔",  "駅前にできた新しいカフェ、気になってたんですよね。一緒に行きませんか"),
        ("田中 浩",    "いいですね！何時ごろがいいですか"),
        ("鈴木 みゆき", "12時半ごろはどうでしょう〜"),
        ("佐藤 大輔",  "了解です！じゃあ12時半に集合ということで"),
        ("田中 浩",    "楽しみです〜！"),
        ("鈴木 みゆき", "そういえば先週の月例報告って提出しましたか？"),
        ("佐藤 大輔",  "昨晩ギリギリで出しました笑　少し疲れました"),
        ("田中 浩",    "お疲れさまです！私は午前中に出せてよかったです"),
        ("鈴木 みゆき", "えらい！締め切り今日の12時でしたもんね"),
        ("佐藤 大輔",  "ランチ前に終わらせられてすっきりしました。気持ちよく食べられそう笑"),
        ("田中 浩",    "最近何かいい映画見ましたか？週末暇で"),
        ("鈴木 みゆき", "先週サスペンスのやつ見たんですが、めちゃくちゃよかったですよ"),
        ("佐藤 大輔",  "気になります！タイトル何でしたっけ"),
        ("鈴木 みゆき", "あとで確認して送りますね〜、うろ覚えで"),
        ("田中 浩",    "ありがとうございます。ではランチ後に教えてください！"),
    ],
    # ── Script 2: 週末・アウトドア ────────────────────────────────────
    [
        ("鈴木 みゆき", "みなさん今週末って予定ありますか？"),
        ("田中 浩",    "家族と近くの公園に行こうと思ってます。久しぶりに"),
        ("佐藤 大輔",  "いいですね！最近キャンプも流行ってますよね"),
        ("田中 浩",    "キャンプ、興味あるんですが道具が全然なくて笑"),
        ("鈴木 みゆき", "レンタルできるサービスもありますよ〜。手ぶらで行けるやつ"),
        ("佐藤 大輔",  "私は先月行ったんですが、すごくよかったですよ"),
        ("田中 浩",    "それは羨ましい！どの辺ですか？"),
        ("佐藤 大輔",  "車で2時間くらいの川沿いのキャンプ場です。景色がよくて最高でした"),
        ("鈴木 みゆき", "それは素敵〜！来年は私も挑戦してみたいな"),
        ("田中 浩",    "じゃあ来年みんなで行きませんか笑"),
        ("佐藤 大輔",  "それ本気でいいですね！ぜひ計画しましょう"),
        ("鈴木 みゆき", "決定！楽しみにしてます〜"),
        ("田中 浩",    "春ごろがいいかな。暖かくなってきた頃"),
        ("佐藤 大輔",  "4月か5月あたりが気候もいいですよね"),
        ("鈴木 みゆき", "じゃあ4月で仮押さえしておきましょ！"),
    ],
    # ── Script 3: 仕事の話・プレゼン準備 ─────────────────────────────
    [
        ("佐藤 大輔",  "来月のプレゼン、準備進んでますか？"),
        ("田中 浩",    "なんとか資料はできてきました。あとはリハーサルだけです"),
        ("鈴木 みゆき", "私はまだ半分くらい…。数字をまとめるところが難しくて"),
        ("佐藤 大輔",  "そこわかります。去年も同じところで悩みました笑"),
        ("田中 浩",    "需要データのグラフ、自動更新にしたら一気に楽になりましたよ"),
        ("鈴木 みゆき", "それいい！教えてもらえますか？"),
        ("田中 浩",    "もちろんです。後でスプレッドシート共有しますね"),
        ("佐藤 大輔",  "ありがとうございます。当日うまくいくといいですね"),
        ("鈴木 みゆき", "絶対うまくいきます！みんなで頑張りましょう"),
        ("田中 浩",    "心強いです。ありがとうございます"),
        ("佐藤 大輔",  "発表は15分でしたっけ。質疑応答込みで"),
        ("鈴木 みゆき", "そうです。質問多そうで少し緊張してます笑"),
        ("田中 浩",    "想定問答を用意しておくといいですよ。去年の議事録が参考になります"),
        ("佐藤 大輔",  "それいいですね！議事録は共有フォルダにありますよ"),
        ("鈴木 みゆき", "ありがとうございます！チームっていいな〜と感じました笑"),
    ],
    # ── Script 4: グルメ・新しいラーメン屋 ───────────────────────────
    [
        ("田中 浩",    "昨日オープンしたラーメン屋さん、行った人います？"),
        ("鈴木 みゆき", "気になってました！どうでしたか？"),
        ("田中 浩",    "並んだ甲斐がありました。醤油ベースで濃厚でおいしかったですよ"),
        ("佐藤 大輔",  "それは食べてみたい！何時ごろ行ったんですか？"),
        ("田中 浩",    "11時半に並んで12時に入れました。早めに行くのがおすすめです"),
        ("鈴木 みゆき", "ランチタイムに行けそう〜"),
        ("佐藤 大輔",  "今週中に行ってみようかな"),
        ("田中 浩",    "おすすめは醤油ですけど、塩も人気みたいですよ"),
        ("鈴木 みゆき", "迷うな〜笑。両方食べたい"),
        ("佐藤 大輔",  "複数人で行って半分こにすれば解決ですね笑"),
        ("田中 浩",    "それは名案！では今週末みんなで行きますか"),
        ("鈴木 みゆき", "いいですね！行きましょう行きましょう！"),
        ("佐藤 大輔",  "確定！楽しみにしてます"),
        ("田中 浩",    "では土曜日11時半集合でどうですか"),
        ("鈴木 みゆき", "OK！カレンダーに入れました〜"),
    ],
    # ── Script 5: 健康・ウォーキング ────────────────────────────────
    [
        ("山田 花子",  "朝のウォーキング習慣つけようと思って、今週から始めました！"),
        ("伊藤 誠",   "いいですね！何時ごろ歩いてるんですか？"),
        ("山田 花子",  "6時半ごろです。まだ涼しくて気持ちいいですよ"),
        ("渡辺 さくら", "素敵〜！私も運動不足が気になってたんですよね"),
        ("伊藤 誠",   "近所に川沿いの遊歩道があって、そこを30分ほど歩いてます"),
        ("山田 花子",  "それは羨ましい！景色が良さそう"),
        ("渡辺 さくら", "私も試してみようかな。休日から始めれば習慣になりそう"),
        ("伊藤 誠",   "最初は週2〜3回でも十分ですよ。無理しないのがコツです"),
        ("山田 花子",  "先週3日続けただけで体が軽くなった気がします笑"),
        ("渡辺 さくら", "それは効果あり！モチベーション上がりますね"),
        ("伊藤 誠",   "スマホのステップカウンターで記録するのも楽しいですよ"),
        ("山田 花子",  "使ってます！昨日は8000歩でした"),
        ("渡辺 さくら", "すごい！私の目標は5000歩から始めようかな"),
        ("伊藤 誠",   "それで十分ですよ。継続が大事ですから"),
        ("山田 花子",  "みんなで一緒に歩く会とかできたら楽しいですよね"),
    ],
    # ── Script 6: 差し入れ・お土産 ──────────────────────────────────
    [
        ("加藤 美咲",  "出張のお土産でどら焼き持ってきたんですが、もしよければどうぞ〜"),
        ("小林 太郎",  "ありがとうございます！どこのお土産ですか？"),
        ("加藤 美咲",  "京都です。老舗のお店のやつです"),
        ("中村 健太",  "京都のどら焼き、聞いただけで美味しそうです笑"),
        ("小林 太郎",  "いただきます！あ、これは本当においしいですね"),
        ("加藤 美咲",  "よかった〜。評判が良くて選んだんです"),
        ("中村 健太",  "差し入れってありがたいですよね。職場の雰囲気が和みます"),
        ("加藤 美咲",  "私も差し入れもらうとすごく嬉しいので"),
        ("小林 太郎",  "来月私も出張があるので何か買ってきます"),
        ("中村 健太",  "楽しみにしてます笑"),
        ("加藤 美咲",  "どこに行くんですか？"),
        ("小林 太郎",  "福岡です。初めて行くので楽しみで"),
        ("中村 健太",  "福岡は食べ物が美味しいですよ！ラーメンや明太子"),
        ("加藤 美咲",  "通りもん！通りもんがおすすめですよ"),
        ("小林 太郎",  "メモしました笑　ありがとうございます"),
    ],
    # ── Script 7: 連休の過ごし方 ────────────────────────────────────
    [
        ("松本 愛",   "来月の連休、みなさん予定はありますか？"),
        ("山田 花子",  "家族で箱根に行こうと計画中です！"),
        ("中村 健太",  "いいですね〜！温泉ですか？"),
        ("山田 花子",  "そうです。子供たちが楽しみにしてます"),
        ("伊藤 誠",   "箱根は観光スポットも多くて飽きないですよね"),
        ("松本 愛",   "私は友達と長野に行く予定です。避暑がてら"),
        ("中村 健太",  "長野の夏は涼しくていいですね。軽井沢あたりですか？"),
        ("松本 愛",   "そうです！カフェ巡りしたいなと思って"),
        ("山田 花子",  "おしゃれ〜！インスタ映えしそうです"),
        ("伊藤 誠",   "私は今回は近場でゆっくりする予定です。図書館と映画館"),
        ("松本 愛",   "それもいい過ごし方ですね。リフレッシュできそう"),
        ("中村 健太",  "私はゲームの新作が出るので、家でやり込む予定です笑"),
        ("山田 花子",  "正直ですね笑！楽しい連休になりそう"),
        ("伊藤 誠",   "連休明けにお互いの旅行話を聞かせてください"),
        ("松本 愛",   "ぜひ！楽しみにしてます"),
    ],
]

# ボットセッション: name → token
BOT_SESSIONS: dict = {}
# 実行中フラグ（バックグラウンドスレッドが動作中かどうか）
BOT_RUNNING: bool = False
_BOT_LOCK = threading.Lock()
# 感染済みボットトークンを追跡（1セッションにつき1回のみ記録）
BOT_INFECTED: set = set()

# ボット感染シミュレーション用 User-Agent プール
_BOT_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
]

# ボット名の集合（管理パネルでのBot判定に使用）
_BOT_NAMES: set = {name for script in BOT_SCRIPTS for name, _ in script}


# 東京近郊の GPS 座標プール（デモ用フェイクデータ）
_GPS_POOL = [
    (35.6762,  139.6503, 12),   # 渋谷
    (35.6895,  139.6917, 8),    # 新宿
    (35.7101,  139.8107, 15),   # 上野
    (35.6581,  139.7016, 20),   # 品川
    (35.7281,  139.7186, 10),   # 池袋
    (35.6455,  139.7103, 18),   # 大崎
    (35.6683,  139.7454, 9),    # 恵比寿
    (35.6814,  139.7671, 14),   # 秋葉原
    (35.6329,  139.8804, 22),   # 葛西
    (35.7436,  139.6756, 11),   # 練馬
]


def _simulate_bot_xss(bot_name: str, bot_token: str):
    """
    ボットが掲示板を"閲覧"した際に XSS ペイロードに感染するシミュレーション。
    エスケープ・サニタイズが両方無効 かつ スクリプト系ペイロードが存在する場合のみ記録。
    1ボットにつき1回のみ（BOT_INFECTED でガード）。
    """
    global BOT_INFECTED
    if bot_token in BOT_INFECTED:
        return  # 感染済みのため二重記録しない
    s = _load_settings()
    if s.get("escape") or s.get("sanitize"):
        return
    msgs = _load(MESSAGES_FILE)
    has_payload = any(
        re.search(r"<script|onerror\s*=|javascript\s*:", m.get("body", ""), re.I)
        for m in msgs
    )
    if not has_payload:
        return
    BOT_INFECTED.add(bot_token)
    lat, lon, acc = random.choice(_GPS_POOL)
    lat  = round(lat  + random.uniform(-0.004, 0.004), 6)
    lon  = round(lon  + random.uniform(-0.004, 0.004), 6)
    loot = _load(LOOT_FILE)
    loot.append({
        "cookie":       f"session={bot_token}",
        "page_url":     "https://127.0.0.1:5000/board",
        "ip":           f"192.0.2.{random.randint(10, 250)}",
        "user_agent":   random.choice(_BOT_UA),
        "gps_lat":      str(lat),
        "gps_lon":      str(lon),
        "gps_accuracy": str(acc),
        "captured_at":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save(LOOT_FILE, loot)


def _run_bot_conversation(script: list):
    """
    バックグラウンドスレッドで会話を人間らしい速度で投稿する。
    メッセージごとに 4〜9 秒のランダムな間隔を挟む。
    各ボットは投稿前に掲示板を「閲覧」するため、その時点で XSS 感染チェックを行う。
    """
    global BOT_RUNNING
    try:
        for i, (bot_name, body) in enumerate(script):
            if not BOT_RUNNING:
                break
            # セッション発行（初回のみ）
            if bot_name not in BOT_SESSIONS:
                bot_token              = "usr_" + secrets.token_hex(12)
                BOT_SESSIONS[bot_name] = bot_token
                SESSIONS[bot_token]    = bot_name

            # 投稿前にページを"閲覧" → XSS 感染チェック（未感染の場合のみ記録）
            _simulate_bot_xss(bot_name, BOT_SESSIONS[bot_name])

            msgs = _load(MESSAGES_FILE)
            msgs.append({
                "id":         len(msgs) + 1,
                "author":     bot_name,
                "body":       body,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            _save(MESSAGES_FILE, msgs)

            # 次のメッセージまで人間らしい間隔で待つ
            if i < len(script) - 1:
                time.sleep(random.uniform(4, 9))
    finally:
        BOT_RUNNING = False


# ------------------------------------------------------------------ #
# セキュリティヘッダを after_request で動的に付与                      #
# ------------------------------------------------------------------ #
@app.after_request
def apply_security_headers(response):
    s = _load_settings()
    if s.get("csp"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
        )
    if s.get("x_frame_options"):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ------------------------------------------------------------------ #
# ルート                                                               #
# ------------------------------------------------------------------ #
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        acct = ACCOUNTS.get(username)
        if acct and acct["password"] == password and username not in DELETED_ACCOUNTS:
            token = acct["prefix"] + secrets.token_hex(12)
            SESSIONS[token] = username
            s = _load_settings()
            resp = make_response(redirect(url_for("board")))
            resp.set_cookie(
                "session", token,
                httponly=s.get("httponly", False),
                samesite="Strict" if s.get("samesite_strict") else "Lax",
            )
            return resp
        error = "ユーザー名またはパスワードが違います"
    return render_template("login.html", error=error)


@app.route("/guest-login", methods=["POST"])
def guest_login():
    """ゲストログイン: 毎回ランダムな gst_ トークンを発行。複数ゲスト同時利用可。"""
    token = "gst_" + secrets.token_hex(16)
    SESSIONS[token] = "guest"
    s = _load_settings()
    resp = make_response(redirect(url_for("board")))
    resp.set_cookie(
        "session", token,
        httponly=s.get("httponly", False),
        samesite="Strict" if s.get("samesite_strict") else "Lax",
    )
    return resp


@app.route("/board", methods=["GET", "POST"])
def board():
    messages = _load(MESSAGES_FILE)
    token    = request.cookies.get("session", "")
    role     = _role_from_token(token)
    username = _username_from_token(token)
    s        = _load_settings()

    if request.method == "POST":
        body = request.form.get("body", "")
        if s.get("sanitize"):
            body = _strip_tags(body)
        messages.append({
            "id":         len(messages) + 1,
            "author":     username,
            "body":       body,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        _save(MESSAGES_FILE, messages)
        return redirect(url_for("board"))

    return render_template(
        "board.html",
        messages=messages,
        role=role,
        username=username,
        token=token,
        escape_enabled=s.get("escape", False),
        settings=s,
        bot_running=BOT_RUNNING,
    )


@app.route("/collector", methods=["POST"])
def collector():
    """
    攻撃者が管理するサーバーを模したエンドポイント。
    実際の攻撃では攻撃者自身のインフラ上に置かれますが、
    このデモでは利便性のため同じアプリ内に同居させています。
    """
    data = request.get_json(silent=True) or {}
    gps  = data.get("gps") or {}
    loot = _load(LOOT_FILE)
    loot.append({
        "cookie":       data.get("cookie", ""),
        "page_url":     data.get("url", ""),
        "ip":           request.remote_addr,
        "user_agent":   request.headers.get("User-Agent", ""),
        "gps_lat":      gps.get("lat", ""),
        "gps_lon":      gps.get("lon", ""),
        "gps_accuracy": gps.get("accuracy", ""),
        "captured_at":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save(LOOT_FILE, loot)
    return {"status": "ok"}


@app.route("/attacker-dashboard")
def attacker_dashboard():
    return render_template("dashboard.html", loot=_load(LOOT_FILE))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    s        = _load_settings()
    token    = request.cookies.get("session", "")
    role     = _role_from_token(token)
    can_edit = role in ("admin", "staff")

    if not can_edit:
        return redirect(url_for("board"))

    key = None
    if request.method == "POST":
        key = request.form.get("key")
        if key in DEFAULT_SETTINGS:
            s[key] = not s.get(key, False)
            _save_settings(s)

    resp = make_response(render_template("settings.html", settings=s,
                                         role=role, can_edit=can_edit))

    if key in ("httponly", "samesite_strict"):
        if token in SESSIONS:
            resp.set_cookie(
                "session", token,
                httponly=s.get("httponly", False),
                samesite="Strict" if s.get("samesite_strict") else "Lax",
            )

    return resp


@app.route("/profile")
def profile():
    token    = request.cookies.get("session", "")
    username = _username_from_token(token)
    if username == "guest":
        return redirect(url_for("login"))
    role       = _role_from_token(token)
    is_deleted = username in DELETED_ACCOUNTS
    return render_template("profile.html",
                           username=username, role=role,
                           token=token, is_deleted=is_deleted)


@app.route("/profile/delete", methods=["POST"])
def profile_delete():
    token    = request.cookies.get("session", "")
    username = _username_from_token(token)
    if username != "guest":
        DELETED_ACCOUNTS.add(username)
        SESSIONS.pop(token, None)
    resp = make_response(redirect(url_for("login") + "?deleted=1"))
    resp.set_cookie("session", "", expires=0)
    return resp


@app.route("/profile/embed")
def profile_embed():
    """nav なしのプロフィールページ。クリックジャッキング用 iframe 向け。"""
    token      = request.cookies.get("session", "")
    username   = _username_from_token(token)
    role       = _role_from_token(token)
    is_deleted = username in DELETED_ACCOUNTS
    return render_template("profile_embed.html",
                           username=username, role=role,
                           token=token, is_deleted=is_deleted)


@app.route("/attacker-cj")
def attacker_cj():
    return render_template("attacker_cj.html")


@app.route("/attacker-cj/stage")
def attacker_cj_stage():
    return render_template("attacker_cj_stage.html")


# ------------------------------------------------------------------ #
# 管理パネル                                                           #
# ------------------------------------------------------------------ #
@app.route("/admin")
def admin_panel():
    """管理パネル — admin / staff のみアクセス可。"""
    token    = request.cookies.get("session", "")
    role     = _role_from_token(token)
    if role not in ("admin", "staff"):
        return redirect(url_for("board"))
    username = _username_from_token(token)
    msgs     = _load(MESSAGES_FILE)
    loot     = _load(LOOT_FILE)

    sessions_list = [
        {
            "username": u,
            "role":     _role_from_token(t),
            "token":    t,
            "is_bot":   u in _BOT_NAMES,
        }
        for t, u in SESSIONS.items()
    ]

    return render_template(
        "admin.html",
        role=role,
        username=username,
        sessions=sessions_list,
        message_count=len(msgs),
        loot_count=len(loot),
        bot_running=BOT_RUNNING,
        bot_names=sorted(_BOT_NAMES),
    )


@app.route("/bot/start", methods=["POST"])
def bot_start():
    """ボット会話をバックグラウンドで開始する。admin / staff のみ。"""
    global BOT_RUNNING
    token = request.cookies.get("session", "")
    role  = _role_from_token(token)
    if role not in ("admin", "staff"):
        return redirect(url_for("board"))

    with _BOT_LOCK:
        if BOT_RUNNING:
            return redirect(url_for("admin_panel"))
        BOT_RUNNING = True

    script = random.choice(BOT_SCRIPTS)
    t = threading.Thread(target=_run_bot_conversation, args=(script,), daemon=True)
    t.start()

    return redirect(url_for("board"))


@app.route("/bot/stop", methods=["POST"])
def bot_stop():
    """ボット会話を中断する。admin / staff のみ。"""
    global BOT_RUNNING
    token = request.cookies.get("session", "")
    role  = _role_from_token(token)
    if role not in ("admin", "staff"):
        return redirect(url_for("board"))
    BOT_RUNNING = False
    return redirect(url_for("admin_panel"))


@app.route("/bot/reset", methods=["POST"])
def bot_reset():
    """ボットセッションを破棄する。admin / staff のみ。"""
    global BOT_RUNNING
    token = request.cookies.get("session", "")
    role  = _role_from_token(token)
    if role not in ("admin", "staff"):
        return redirect(url_for("board"))
    BOT_RUNNING = False
    for t in list(BOT_SESSIONS.values()):
        SESSIONS.pop(t, None)
    BOT_SESSIONS.clear()
    BOT_INFECTED.clear()
    return redirect(url_for("admin_panel"))


@app.route("/reset")
def reset():
    global BOT_RUNNING
    BOT_RUNNING = False
    DELETED_ACCOUNTS.clear()
    for t in list(BOT_SESSIONS.values()):
        SESSIONS.pop(t, None)
    BOT_SESSIONS.clear()
    BOT_INFECTED.clear()
    _save(MESSAGES_FILE, [])
    _save(LOOT_FILE, [])
    return redirect(url_for("board"))


# ------------------------------------------------------------------ #
# ヘルパー                                                             #
# ------------------------------------------------------------------ #
def _role_from_token(token: str) -> str:
    if token.startswith("adm_"): return "admin"
    if token.startswith("stf_"): return "staff"
    if token.startswith("usr_"): return "user"
    if token.startswith("gst_"): return "guest"
    return "guest"


def _username_from_token(token: str) -> str:
    return SESSIONS.get(token, "guest")


if __name__ == "__main__":
    import socket as _socket

    def _get_local_ip() -> str:
        """起動中のマシンの LAN IP アドレスを自動取得する。"""
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))   # 実際には送信しない UDP トリック
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    _local_ip = _get_local_ip()

    print("=" * 70)
    print(" Stored XSS PoC Demo -- 教育・許可された検証専用")
    print(" インターネットに公開しないでください。")
    print("=" * 70)

    # ── HTTP (ローカル確認用) ────────────────────────────────────────────
    # app.run(host="127.0.0.1", port=5000, debug=True)

    # ── HTTPS / LAN デモ用 (gevent + mkcert 証明書) ─────────────────────
    from gevent import pywsgi
    server = pywsgi.WSGIServer(
        ("0.0.0.0", 5000), app,
        keyfile="key.pem",
        certfile="cert.pem",
    )
    print(f"HTTPS 起動: https://{_local_ip}:5000")
    server.serve_forever()
