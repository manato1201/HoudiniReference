# HoudiniReference

Houdini の Tips・ニュース・リファレンスを、公式のフィード/API から自動で集めて確認する静的サイトと、その収集器(Python 標準ライブラリのみ)。

> **出典と利用条件**: 各項目の題名・抜粋・動画などの権利は**それぞれの出典元**(SideFX・各 YouTube チャンネルなど)にあります。このリポジトリは題名・URL・出典名・日付・短い抜粋・タグだけを保存し、全文・画像・サムネイルは保存しません。内容は元のページで確認し、各サービスの利用規約・robots.txt に従ってください(このプロジェクトは SideFX 社とは無関係の非公式のものです)。

**できること**: ニュース / Tips / リファレンスの 3 タブ・検索・出典/種別/期間の絞り込み・お気に入り(ブラウザ内)・ライト/ダーク・最終更新と情報源の状態の表示。各項目は題名・出典名・日付・短い抜粋・元ページへのリンクだけ(全文・画像は保存しない)。

## 使い方

```powershell
python -m collector                       # 収集 → data/items.json と site/data/ を更新(Python 3.12・標準ライブラリのみ)
python -m collector --dry-run             # 取得せず、見込み(X の件数など)だけ表示
python -m unittest discover -s tests -t . # テスト(ネットワーク不要)
python -m http.server 8765 --directory site   # → http://127.0.0.1:8765/ を開く
```

`site/` は静的ファイルだけ(ビルド不要)。公開は Vercel(Git 連携。公開ディレクトリは `site/`)。毎日の自動実行は `.github/workflows/collect.yml`(**用意しただけ**・未有効)。push と PR のテストは `.github/workflows/ci.yml`。フッターの「関連サイト」(他の自作サイトへのリンク)の URL は `site/app.js` の `RELATED_SITES` に 1 か所だけ(このサイト自身はリンクにならず「いま見ているサイト」と出る)。お気に入り・テーマ・設定はサイトごとに別々に保存され、共有されません。

## 情報源と規約の注意

| 使う | 備考 |
|---|---|
| SideFX フォーラムのニュース・最新トピック(Atom) | sidefx.com の robots は `Crawl-delay: 5`。5 秒以上あけて取得 |
| SideFX 変更履歴 22.0 / 21.0(RSS) | リファレンスタブの「新着」 |
| YouTube 公開フィード(SideFX・Entagma・Junichiro Horikawa・Nine Between) | `data/sources.youtube.json`。**youtube.com の robots は `/feeds/videos.xml` を Disallow**(低頻度で使用) |
| YouTube Data API 検索(任意・既定は無効) | 環境変数 `YOUTUBE_API_KEY`。無ければスキップ |
| X 公式 API v2(任意・既定は無効) | 環境変数 `X_BEARER_TOKEN`。**従量課金**・月の予算上限つき・30 日で消す。単価は未確認。**公開リポジトリでは X の抜粋を公開しない既定**(下記) |

**X の抜粋は公開しない既定**: `data/sources.x.json` の `publish_public` は既定 `false`。false の間、公開物(`data/items.json` と `site/data/items.json`)に `kind: "x"` の項目は出ず、取得した分は**ローカル専用**の `data/items.x.local.json`(`.gitignore` 済み)にだけ置かれます。出したいときは `publish_public: true`(自己責任・X の規約を確認)。GitHub Actions(`collect.yml`)は `X_BEARER_TOKEN` を参照しないので、X は手元でだけ動かします。

使わないもの: スクレイピング、非公式の X 経路、版つきの公式ドキュメント本文(robots で禁止)。詳細と理由は [HoudiniReference_DESIGN.md](HoudiniReference_DESIGN.md)。キーやトークンはコードにもファイルにも書かない(環境変数だけ)。

## 状態

収集器・サイトは実装済み(実フィードで確認、テスト 42 件、Playwright で画面確認)。YouTube API と X は偽サーバーでテスト済みで、**実機は未確認**。Actions の有効化・X の利用可否は運営者が決める。
