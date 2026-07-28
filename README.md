# 返事きたで

複数のGoogleフォームに届いた問い合わせを、一括確認・対応管理できるWebアプリ。

## 解決する課題

複数のWebサービスでGoogle Formsを問い合わせフォームとして使っていると、
新しい回答を確認するためにフォームを1つずつ開いて「回答」タブへ移動する必要があります。

- どのフォームに新しい回答が届いたのか分からない
- 未確認か確認済みか分からない
- 未対応か返信済みかを管理しにくく、対応漏れが発生する

「返事きたで」は、管理対象のすべてのGoogleフォームに届いた回答を、
メールの受信箱のように1つの画面でまとめて確認・管理できるようにします。

## 主な機能

- Googleアカウントでログイン(OAuth 2.0)
- Google Drive APIによるGoogleフォーム一覧の取得
- 管理対象フォームの選択(追加・除外。除外してもデータは残る)
- 複数フォームの回答をGoogle Forms APIで一括取得し、新しい順に一覧表示
- 未読・既読管理(詳細を開くと自動で既読)
- 対応状況管理(未対応 / 対応中 / 対応済み / 保留)
- 重要マーク
- 管理者用メモ(自動保存)
- 検索と絞り込み(フォーム・状況・未読・重要・期間・キーワード)
- Google Forms push通知 + 画面へのリアルタイム反映(Server-Sent Events)
- 手動同期(responseIdによる重複登録防止。既読状態やメモは同期で上書きされない)
- モックモード(Google API・Firebase未設定でもUI確認可能)

## 画面構成

| 画面 | 内容 |
|---|---|
| ログイン | アプリ説明とGoogleログインボタン |
| 受信箱(トップ) | 3カラム構成。左:絞り込みナビ / 中央:問い合わせ一覧 / 右:詳細。上部に件数カードと「回答を更新」ボタン |
| フォーム管理 | Googleフォーム一覧と管理対象の追加・除外 |
| 設定 | アカウント情報・管理対象一覧・件数の再計算 |

スマートフォンでは一覧から詳細画面へ切り替わる1カラム表示になります。

## 使用技術

- バックエンド: Python / Flask / Jinja2
- フロントエンド: HTML / CSS / JavaScript(fetch API)
- データベース: Firebase Cloud Firestore(Firebase Admin SDK for Python)
- 認証: Google OAuth 2.0
- Google API: Google Drive API(フォーム一覧)/ Google Forms API(フォーム情報・回答)
- リアルタイム通知: Google Forms Watches API / Cloud Pub/Sub / Server-Sent Events
- CSRF対策: Flask-WTF
- 本番環境: Ubuntu VPS + Gunicorn + Nginx

## ディレクトリ構成

```
app/
  __init__.py          # アプリファクトリ・エラーハンドラ
  config.py            # 環境変数の読み込み
  constants.py         # ステータス定義など
  firebase_config.py   # Firebase Admin SDKの初期化(一元管理)
  extensions.py        # Flask-WTF CSRF
  auth/                # ログイン・OAuth・デコレーター
  dashboard/           # 受信箱・設定画面
  forms/               # フォーム管理・Drive/Forms API・同期処理
  responses/           # 回答一覧・詳細・更新API
  repositories/        # Firestoreの読み書き(Repository層)
  services/            # 回答解析・件数集計
  mock/                # モックモード用データとRepository
  templates/           # Jinja2テンプレート
  static/              # CSS / JavaScript
run.py
requirements.txt
firestore.indexes.json
.env.example
```

## 必要なPythonバージョン

Python 3.10以上を推奨します。

## ローカルでの起動方法

### 1. 仮想環境の作成とインストール

```bash
cd forms
python3 -m venv .venv
source .venv/bin/activate      # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. .envの作成

```bash
cp .env.example .env
```

まずはモックモードで起動するのが簡単です。`.env`で以下を設定します。

```
SECRET_KEY=適当なランダム文字列
FLASK_ENV=development
MOCK_MODE=true
SESSION_COOKIE_SECURE=false
```

### 3. 起動

```bash
python run.py
# または
flask --app run.py run --debug
```

http://localhost:5000 を開き、「Googleでログイン」を押すとモックユーザーでログインします。

## モックモードの使用方法

`.env`に `MOCK_MODE=true` を設定すると、以下の状態で動作します。

- Googleログインを省略(ボタンを押すとモックユーザーでログイン)
- Firebase・Google Drive API・Google Forms APIへ一切接続しない
- ダミーのフォーム3件と問い合わせ(未読・既読・各対応状況・重要・メモあり等)を表示
- ステータス変更・既読・重要・メモの操作をUI上で確認できる
- 「回答を更新」を押すと初回のみ新しい回答が1件追加される

本番モードとテンプレートは共通で、データ取得部分(Repository)だけが切り替わります。

## Firebaseの設定(本番モード)

### Firebaseプロジェクトの作成

1. https://console.firebase.google.com/ で「プロジェクトを追加」
2. プロジェクト名を入力して作成

### Cloud Firestoreの有効化

1. Firebaseコンソール →「Firestore Database」→「データベースを作成」
2. 本番モードを選択し、ロケーション(例: asia-northeast1)を選ぶ

※本アプリはFirebase Admin SDKでアクセスするため、Security Rulesは経由しません。
Flask側でログインユーザーIDとデータ所有者を必ず確認する設計です。
クライアントからの直接アクセスを防ぐため、ルールはすべて拒否にしておくのが安全です。

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} { allow read, write: if false; }
  }
}
```

### サービスアカウントの発行

1. Firebaseコンソール → 歯車アイコン →「プロジェクトの設定」→「サービスアカウント」
2. 「新しい秘密鍵の生成」を押してJSONをダウンロード
3. ダウンロードしたJSONを `firebase-service-account.json` という名前でプロジェクト直下へ置く
   (`.gitignore`で除外済み。**絶対にGitへコミットしないこと**)
4. `.env`へ設定

```
FIREBASE_PROJECT_ID=あなたのプロジェクトID
FIREBASE_CREDENTIALS_PATH=./firebase-service-account.json
```

## Google Cloud Consoleの設定(本番モード)

### APIの有効化

https://console.cloud.google.com/ でFirebaseと同じプロジェクトを選択し、
「APIとサービス」→「ライブラリ」から以下を有効化します。

- **Google Drive API**(フォーム一覧の取得に使用)
- **Google Forms API**(フォーム情報・回答の取得に使用)

### OAuth同意画面の設定

1. 「APIとサービス」→「OAuth同意画面」
2. User Typeは「外部」を選択(自分だけで使う場合はテストユーザーに自分のGmailを追加)
3. アプリ名(例: 返事きたで)、サポートメール等を入力
4. スコープは下記「使用するGoogle APIスコープ」を追加

### OAuthクライアントIDの作成

1. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuthクライアントID」
2. アプリケーションの種類:「ウェブアプリケーション」
3. 承認済みのリダイレクトURIへ以下を追加
   - ローカル: `http://localhost:5000/auth/callback`
   - 本番: `https://あなたのドメイン/auth/callback`
4. 発行されたクライアントIDとシークレットを`.env`へ設定

```
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxx
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback
MOCK_MODE=false
```

## リアルタイム更新の設定(Cloud Pub/Sub)

Googleフォームの回答をポーリングせずに受け取るには、Google Forms Watches APIとCloud Pub/Subを使います。

### Cloud Pub/Subの準備

1. Google Cloud Consoleで **Cloud Pub/Sub API** を有効化
2. Pub/Sub topicを作成(例: `google-forms-responses`)
3. topicへForms通知サービスアカウントのPublish権限を付与

付与するメンバー:

```
serviceAccount:forms-notifications@system.gserviceaccount.com
```

付与するロール:

```
Pub/Sub Publisher
```

### Push subscriptionの作成

Pub/Sub subscriptionはpush配信で作成し、エンドポイントを以下にします。

```
https://あなたのドメイン/api/pubsub/forms?token=十分に長いランダム文字列
```

`.env`へ同じ値を設定します。

```
GOOGLE_FORMS_PUBSUB_TOPIC=projects/your-project-id/topics/google-forms-responses
GOOGLE_FORMS_PUBSUB_PUSH_TOKEN=十分に長いランダム文字列
```

受信箱を開いた時、またはフォームを管理対象へ追加・再開した時に、各フォームへ `RESPONSES` watchを作成します。Googleから通知が届いたら、このアプリが対象フォームだけを同期し、開いている受信箱へServer-Sent Eventsで更新を流します。

### watchの期限更新

Google Formsのwatchは7日で期限切れになります。受信箱を開いた時にも更新しますが、常時アンテナを維持するため、本番では1日1回程度このコマンドをcronやsystemd timerで実行してください。

```bash
.venv/bin/flask --app run:app ensure-response-watches
```

## 使用するGoogle APIスコープ

必要最小限の読み取り専用スコープのみ要求します(フォームの作成・編集・削除の権限は要求しません)。

| スコープ | 用途 |
|---|---|
| `openid` / `userinfo.email` / `userinfo.profile` | ログインユーザーの識別 |
| `https://www.googleapis.com/auth/drive.metadata.readonly` | Googleフォーム一覧の取得(メタデータのみ) |
| `https://www.googleapis.com/auth/forms.body.readonly` | フォームの質問構成の取得 |
| `https://www.googleapis.com/auth/forms.responses.readonly` | フォームの回答の取得 |

## .envの設定例

`.env.example` を参照してください。実際の秘密情報はGitへコミットしないでください。

## Firestoreのデータ構成

```
users/{userId}
  google_user_id, email, name, picture_url, created_at, updated_at

users/{userId}/private/oauth_token
  token(暗号化済みOAuthトークン), updated_at

users/{userId}/managed_forms/{formId}
  google_form_id, title, is_active,
  response_count, unread_count, unhandled_count,
  last_synced_at,
  response_watch_id, response_watch_expire_at, response_watch_state,
  created_at, updated_at

form_watch_routes/{watchId}
  watch_id, user_id, form_id, event_type, updated_at

users/{userId}/managed_forms/{formId}/responses/{responseId}
  google_response_id, respondent_email, respondent_name,
  summary_text, search_text, submitted_at, answers,
  is_read, status, is_important, admin_memo,
  created_at, updated_at
```

- ドキュメントIDにGoogle FormsのformId / responseIdを使用し、再取得時の重複登録を防止
- `answers`は `{questionId: {question_id, question, answer, order}}` 形式。複数選択などは配列で保存
- 日時はFirestore Timestampで保存(文字列保存はしない)
- statusの値: `unhandled`(未対応) / `in_progress`(対応中) / `completed`(対応済み) / `on_hold`(保留)
- OAuthトークンはSECRET_KEYから導出した鍵でFernet暗号化して保存

## 必要なFirestore複合インデックス

対応状況・未読・重要で絞り込みつつ日時順に並べるため、以下の複合インデックスが必要です
(`firestore.indexes.json`に定義済み)。

| コレクション | フィールド1 | フィールド2 |
|---|---|---|
| responses | status (ASC) | submitted_at (DESC) |
| responses | is_read (ASC) | submitted_at (DESC) |
| responses | is_important (ASC) | submitted_at (DESC) |

Firebase CLIを使う場合: `firebase deploy --only firestore:indexes`

CLIを使わない場合は、絞り込みを実行した際にサーバーログへ出力される
「The query requires an index」エラー内のURLを開くと、コンソールから1クリックで作成できます。
インデックス作成前でも基本機能(全件表示・検索)は動作します。

## 本番環境(Ubuntu VPS)へのデプロイ

### 配置と起動確認

```bash
sudo mkdir -p /var/www/forms
cd /var/www/forms
# ソースを配置(git clone等。firebase-service-account.jsonは含めない)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Firebase認証情報を安全に配置する

```bash
sudo mkdir -p /var/www/forms/secrets
# サービスアカウントJSONをscp等で転送してから
sudo chmod 700 /var/www/forms/secrets
sudo chmod 600 /var/www/forms/secrets/firebase-service-account.json
```

`.env`(本番用)の例:

```
SECRET_KEY=本番用のランダムな長い文字列
FLASK_ENV=production
APP_BASE_URL=https://あなたのドメイン
GOOGLE_REDIRECT_URI=https://あなたのドメイン/auth/callback
FIREBASE_CREDENTIALS_PATH=/var/www/forms/secrets/firebase-service-account.json
GOOGLE_FORMS_PUBSUB_TOPIC=projects/your-project-id/topics/google-forms-responses
GOOGLE_FORMS_PUBSUB_PUSH_TOKEN=十分に長いランダム文字列
MOCK_MODE=false
SESSION_COOKIE_SECURE=true
```

### Gunicornでの起動

```bash
.venv/bin/gunicorn --workers 1 --worker-class gthread --threads 8 --timeout 120 --bind 127.0.0.1:8004 run:app
```

Server-Sent Eventsの接続とPub/Sub通知を同じプロセス内のイベントブローカーでつなぐため、Redis等を追加しない構成では `--workers 1` を推奨します。接続数は `--threads` で増やします。

※ポート8004が既存アプリと重複していないか `sudo ss -tlnp | grep 8004` で確認してください。

### systemdサービスの設定例

`/etc/systemd/system/henji.service`:

```ini
[Unit]
Description=Henji Google Forms Management App
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/var/www/forms
EnvironmentFile=/var/www/forms/.env
ExecStart=/var/www/forms/.venv/bin/gunicorn --workers 1 --worker-class gthread --threads 8 --timeout 120 --bind 127.0.0.1:8004 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now henji
```

watch期限更新をcronで実行する例:

```cron
15 3 * * * cd /var/www/forms && .venv/bin/flask --app app ensure-response-watches >> /var/log/henji-watch-renew.log 2>&1
```

### Nginxの設定例

`/etc/nginx/sites-available/henji`:

```nginx
server {
    listen 80;
    server_name あなたのドメイン;

    location / {
        proxy_pass http://127.0.0.1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 3600;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/henji /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# HTTPS化(certbot)
sudo certbot --nginx -d あなたのドメイン
```

本番ではHTTPS必須です(Secure Cookie・OAuthリダイレクトのため)。

## Google APIとの接続が切れた場合

アクセストークンの期限切れはrefresh_tokenで自動更新されます。
refresh_tokenも無効になった場合(パスワード変更・権限取り消し等)は
「Googleアカウントへの接続が切れました。もう一度ログインしてください」と表示されるので、
再度Googleログインしてください。トークンは再保存されます。

## よくあるエラーと対処方法

| 症状 | 原因と対処 |
|---|---|
| 起動時に「FIREBASE_CREDENTIALS_PATH が設定されていません」 | `.env`の設定漏れ。モック確認だけなら`MOCK_MODE=true`にする |
| 「サービスアカウントJSONが見つかりません」 | パスの誤り。`FIREBASE_CREDENTIALS_PATH`の実ファイルを確認 |
| ログイン後に`redirect_uri_mismatch` | Google CloudのリダイレクトURIと`GOOGLE_REDIRECT_URI`が不一致 |
| ログインが`access_denied`になる | OAuth同意画面が「テスト」状態で、テストユーザーに未登録 |
| 同期で「取得に失敗しました」 | Forms APIが未有効化、またはフォームへのアクセス権喪失。サーバーログを確認 |
| 絞り込みで500エラー | Firestore複合インデックス未作成。ログ内のURLから作成 |
| ログインしてもすぐログアウトされる | ローカルで`SESSION_COOKIE_SECURE=true`になっている。`false`へ変更 |
| 件数表示が実際と合わない | 設定画面の「件数を再計算する」を実行 |

## セキュリティ上の注意

- `firebase-service-account.json`・`.env`・OAuthシークレットは絶対にGitへコミットしない
- OAuthトークンは暗号化してFirestoreへ保存され、ログ・画面・APIレスポンスには出力しない
- FirestoreのデータはすべてログインユーザーIDのパス配下(`users/{userId}/...`)に分離
- すべてのAPIでセッションのユーザーIDのみを使用(URLのuserIdは信用しない)
- 回答内容の表示はすべてHTMLエスケープ(XSS対策)、POSTはCSRFトークン必須
