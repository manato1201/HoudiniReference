# HoudiniReference 設計書

作成日: 2026-11-18 / 状態の語彙: 実装済み・設計のみ・未確認

**目的**: Houdini の **Tips・ニュース・リファレンスを自動で集めて、確認できる**こと。読んで学ぶ「図鑑」ではなく、**集めて見に行く場所**(SYSTEM_MAP §5 の「Houdini 特化」)。個人・少人数の閲覧用で、認証は作らない。DevRAG は「聞く場所」、ここは「毎日の新着を見る場所」。

## 1. 機能の範囲(MVP)

| 区分 | 内容 | 状態 |
|---|---|---|
| **入れる** | 3 タブ(ニュース / Tips / リファレンス)・検索(クライアント側・AND)・出典/種別/**言語(日本語・English)**/期間の絞り込み・お気に入り(localStorage、読み書きは try/catch)・ライト/ダーク・「最終更新」と情報源の状態の表示・動きは読み込み時の 1 回きり(opacity と transform だけ、`prefers-reduced-motion` で停止) | 実装済み |
| **入れる** | RSS/Atom(SideFX フォーラム・変更履歴・日本語の技術記事 Qiita/Zenn)・**YouTube の公開フィード**(公式+定評あるチャンネル、日本語・英語)・**GitHub の公式 REST API の releases**(題名・URL・日付・タグだけ) | 実装済み |
| **入れる(任意・既定は無効)** | YouTube Data API の検索(`YOUTUBE_API_KEY`)・**X 公式 API v2**(`X_BEARER_TOKEN`、予算上限つき) | 実装済み・実機は**未確認**(キー/トークンが無い) |
| **入れない** | スクレイピング(本文の丸ごと取得、HTML ページの解析)・Nitter 等の非公式の X 経路・全文/画像/動画/サムネイルの保存・認証・コメント・通知・AI 要約・他サイトのコード/文章/デザインの流用 | — |
| **参考にするだけ** | 同種の他サイトの「ホーム→カテゴリ→一覧→検索」という**構造の考え方だけ**を参考にし、コード・文章・デザイン・デモは写さない | — |

新しいライブラリは増やさない(収集は Python 3.12 標準ライブラリの `urllib` と `xml.etree`、サイトは静的 HTML/CSS/JS)。

## 2. 情報源(2026-11-18 に実際に GET して確認。1 ホストあたり礼儀として間隔を空け、汎用 UA・個人情報なし)

| 情報源 | 取得方法 | 結果 | 判断 |
|---|---|---|---|
| SideFX ニュース(フォーラム 70 "News") | Atom `sidefx.com/forum/feeds/forum/70/` | 200・Atom・15 件・Last-Modified あり。サイトが `<link rel=alternate>` で公開しているフォーラムのフィード | **使う**(ニュース) |
| SideFX フォーラム(最新トピック) | Atom `…/forum/feeds/topics/` | 200・Atom・15 件 | **使う**(Tips)。投稿者名は保存しない |
| SideFX 変更履歴 22.0 / 21.0 | RSS `…/changelog/rss/22_0/`・`21_0` | 200・RSS 2.0・18 件 / 1 件 | **使う**(リファレンス=リリースノートの新着) |
| YouTube: Houdini (SideFX) / Entagma / Junichiro Horikawa / Nine Between | `youtube.com/feeds/videos.xml?channel_id=…` | 200・Atom・各 15 件。ID は `@ハンドル` のページ→`externalId` で取り、**フィードを GET して題名が一致することを確認** | **使う**(Tips)。下の「robots の注意」参照 |
| **(2026-11-19 の拡張)** SideFX フォーラムの分類別: 学習資料(10)・Solaris と Karma(82)・Copernicus(114)・日本語フォーラム(71) | Atom `…/forum/feeds/forum/<ID>/`(フォーラム一覧のページが `<link>` で公開している ID) | 200・Atom・各 15 件(投稿単位なので同じ題名が並ぶ → 題名で 1 件に) | **使う**(Tips)。`dedupe_title`。他の分類(技術討論・WIP など)は量が多く今回は入れない |
| Qiita のタグ `houdini` | Atom `qiita.com/tags/houdini/feed` | 200・Atom・4 件(新着のみ)。robots は `/api/*` `/search` 等だけを Disallow(フィードは対象外) | **使う**(Tips・日本語) |
| Zenn のトピック `houdini` | RSS `zenn.dev/topics/houdini/feed` | 200・RSS 2.0・20 件(初回は 502 が 1 回、再試行で 200)。robots は `/search` だけ | **使う**(Tips・日本語) |
| GitHub: SideFX Labs / Houdini Engine for Unreal / Houdini Engine for Unity / Houdini Niagara の releases | **REST API** `api.github.com/repos/sideeffects/<repo>/releases`(認証なし・60 回/時・ETag で条件付き) | 200・JSON・8 / 10 / 1 / 8 件。`sideeffects` 組織の 71 リポジトリを API で一覧し、releases がある公式リポジトリだけを選んだ | **使う**(リファレンス)。題名・URL・日付・タグだけ(本文は読まない)。Labs は毎日のプレリリース |
| YouTube: IndyZone(日本語)・USD VFXパイプライン解説と各種インタビュー(日本語)・Konstantin Magnus・Rohan Dalvi・Radu Cius | `youtube.com/feeds/videos.xml?channel_id=…` | 200・各 15 件。ID は `@ハンドル` のページ→`externalId` で取り、**フィードの題名が一致し Houdini の動画が並ぶことを確認** | **使う**(Tips)。IndyZone と Magnus は 15/15 が Houdini、Dalvi 14/15、Radu 15/15、USD VFX は 10/15(USD・Solaris・Karma) |
| YouTube: bubblepins | 上と同じ | 200・15 件(Houdini 15/15)だが**最新が 2025-10 で 1 年更新なし** | **使わない**(古い。更新が再開したら足す) |
| YouTube: Doxia Studio | 上と同じ | 200・15 件だが Houdini は 11/15(Illugen・リアルタイム VFX が主) | **使わない**(Houdini 特化ではない) |
| YouTube: Studio Satsuki(SideFX の日本語講座の制作者) | 上と同じ | 200・15 件だが最近の動画は数学・実装配信が中心(Houdini は 6/15) | **使わない**(最近は Houdini 以外が多い) |
| YouTube: Ben Watts | 上と同じ | 200 だがフィードの `entry` が **0 件** | **使わない**(取れない) |
| YouTube: `@IndiePixel` | 上と同じ | 200 だが 2012 年の私的な動画 1 件(Houdini のチャンネルではなかった) | **使わない**(別のチャンネル。ハンドルの推測は不可の見本) |
| SideFX 変更履歴 20.5 / 20.0 | RSS `…/changelog/rss/20_5/`・`20_0/` | 200 だが `item` が **0 件**(チャンネル情報だけ) | **使わない**(空) |
| dev.to のタグ `houdini` / `sidefx` | RSS `dev.to/feed/tag/houdini` | 200・12 件だが **CSS Houdini・暗号資産の Houdini Swap が大半**(Houdini ソフトは 2 件)。`sidefx` タグは 1 件(2023 年) | **使わない**(ノイズが多く、題名の絞り込みも脆い。robots は問題なし) |
| GitHub の `releases.atom` | Atom | github.com の robots.txt が `Disallow: /*.atom$` | **使わない**(代わりに REST API を使う) |
| GitHub: SideFX の他のリポジトリ(Houdini Engine for Maya / 3ds Max・Houdini USD Bridge・SideFX Labs Examples) | API | releases が **0 件**(空) | **使わない**。GameDevelopmentToolset は最後のリリースが 2020 年(Labs に置き換わった)で古い |
| Reddit(`r/Houdini` の `.rss` など) | RSS / API | `reddit.com/robots.txt` が **`User-agent: *` に `Disallow: /`**、公開コンテンツの利用方針あり | **使わない**(規約が明確に許す形ではない) |
| docs.sidefx.com / sidefx.com/docs の本文 | — | robots.txt が**版つきパス(`/docs/houdini22.0/` など)を Disallow** | **取らない**。`/docs/houdini/` 等の入口を**リンクするだけ**(§6) |
| SideFX ニュースページ(`/news/`・`/community/…`) | HTML のみ・フィードなし(`/feed/` `/rss/` は 404) | RSS/API が無い | **使わない**(スクレイピングになる) |
| CG Channel の Houdini タグのフィード | RSS | 返ったフィードの内容が 2024 年のままで古く、robots に AI 向けの Content-Signal もある | **使わない**(古い・規約が不明) |
| GitHub の SideFX リポジトリのリリース | Atom / REST | robots が「クロールは連絡」「API を使え」 | **今回は使わない**(MVP の範囲外。必要なら REST API で後から) |
| YouTube Data API 検索 | API(キー) | キーが無く実機は**未確認** | **任意・既定は無効**(`data/sources.youtube.json` の `api_search`) |
| X(公式 API v2) | API(Bearer) | トークンが無く実機は**未確認** | **任意・既定は無効**(§8) |

- **sidefx.com の robots.txt は `Crawl-delay: 5`**。コードで同ホストへの取得を **5 秒以上あける**(`collector/httpclient.py`)。`/forum/search/` などの Disallow 対象は取らない。利用規約(`/legal/terms-and-conditions/`)に、フィードの自動取得を禁じる文言は見つからなかった(要約確認。法的な確認ではない)。変更履歴フィードの `description` には「Information is confidential…」という定型文があるが、サイトが公開しているフィードで、保存するのは題名・URL・短い抜粋だけ。
- **拡張(2026-11-19)の確認**: 各フィードを**1 回ずつ**だけ GET(sidefx.com は 5 秒間隔)。qiita.com・zenn.dev・dev.to・api.github.com は robots.txt を読み、フィード/API のパスが Disallow でないことを確認(zenn.dev・qiita.com・dev.to は `/search` や `/api/` などだけ。api.github.com は robots.txt なし)。GitHub の上限は認証なし 60 回/時で、1 回の収集は 4 リクエスト(ETag の 304 は上限に数えない)。GitHub Actions の共有 IP では他の利用者の分と合算されて 403(上限)になることがあり、その場合は他の情報源を続けて失敗を記録する(`rate limited?`)。
- **YouTube の robots の注意**: `youtube.com/robots.txt` は `User-agent: *` に `Disallow: /feeds/videos.xml` を書いている。フィードは購読用の公開機能だが、**robots の文言とは食い違う**。運営者の判断で使うが、1 日 1 回・15 件・汎用 UA・条件付き GET の低頻度に絞る。気になるなら `data/sources.youtube.json` の `channels` を空にすれば止まる(`api_search` に切り替える)。

## 3. データの形(`data/items.json`、サイトは `site/data/items.json` のコピーを読む)

```json
{ "schema_version": 1, "generated_at": "ISO8601Z",
  "sources": [{ "id", "name", "kind": "rss|youtube|github|x", "tab", "ok": true|false|null,
                "fetched", "not_modified", "error", "skipped", "last_ok" }],
  "items":   [{ "id", "tab": "news|tips|reference", "kind": "rss|youtube|github|x",
                "source_id", "source", "title", "url", "published", "excerpt",
                "tags": [], "lang": "ja|en", "first_seen", "handle"(X のみ) }] }
```

- 保存するのは**題名(200 字以内)・URL・出典名・日付・抜粋(200 字以内)・タグ**だけ。X は加えて投稿 ID(`id` = `x:<ID>`)とハンドル。
- `id`: RSS は正規化 URL の SHA-1 先頭 16 桁、YouTube は `yt:<videoId>`、X は `x:<postId>`。
- `lang` は設定(`lang`)があればそれ、無ければ題名・抜粋のかな・漢字の有無で判定(補助。過去に保存した項目にも収集のたびに付ける)。GitHub の `id` は正規化 URL の SHA-1。
- `data/` の他のファイル: `sources.json`(RSS)・`sources.github.json`(GitHub のリリース。`repo` は `owner/name` の形だけ受け付ける)・`sources.youtube.json`(チャンネル・API 検索の設定)・`sources.x.json`(X の設定)・`reference.json`(§6)・`fetch_state.json`(ETag / Last-Modified)・`x_usage.json`(X の月ごとの使用量と `since_id`。使った時だけ作られる)。

## 4. 収集の流れ(`python -m collector`)

取得(情報源ごとのアダプタ。ETag / Last-Modified があれば条件付き GET)→ 正規化(HTML タグ・script/style の除去、実体参照の復元、制御文字の除去、200 字に切る、`http(s)` 以外の URL は捨てる)→ **重複除去**(`id` 一致。同じ動画がフィードと API にあればフィード側を残す)→ タグ付け(キーワード表。VEX・Solaris・Karma・APEX・バージョン `H22.0` など)→ `items.json`。

**重複除去の追加(2026-11-19)**: Web(rss)の項目は、題名が同じなら(記号・大文字小文字の違いは無視。6 文字未満は対象外)別の情報源から来ても **1 件**にする(残すのは設定の並びが先の情報源 → 同じ情報源なら新しい方)。SideFX フォーラムの「最新トピック」と分類別、Qiita と Zenn の転載などが対象。投稿単位のフィード(フォーラムの分類別)は `dedupe_title` で、その 1 回の取得の中でも同じ題名を 1 件にする。YouTube は動画 ID、GitHub は URL で重複を判定し、題名では判定しない。**タグ**は英語に加え日本語の語彙(流体・破壊・コペルニクス・シミュレーション・プロシージャル…)でも付く(`VEXの` のように日本語が続いても境界が働く)。

**所要時間**: 情報源は 23 本(YouTube API 検索と X は既定で無効)。**取得の順番はホストを交互にする**ので、sidefx.com の 5 秒の間隔の間に他のホスト(YouTube・Qiita・Zenn・GitHub)を取れて、全体は約 40 秒(2026-11-19 の実測 37 秒。sidefx.com は 8 リクエスト × 5 秒が下限)。1 つの情報源あたり 15〜20 件(Labs・Niagara は 8 件)の上限を設けている。

**失敗時の扱い**: 1 つの情報源が落ちても他は続ける。失敗は `sources[].error`(トークン/キー/URL のクエリを含まない短い文)と `last_ok` に記録し、**古いデータは消さない**(消えるのは、情報源ごとの保持上限を超えたものと、API 由来の保持期限(X・YouTube API は 30 日)を過ぎたもの、削除された X の投稿だけ)。全部が失敗した時だけ終了コード 1(Actions で気付ける)。XML は 2 MB 上限・DOCTYPE/ENTITY を拒否(実体展開攻撃の対策)。

## 5. サイトの構成(`site/`、静的・ビルド不要)

`index.html` / `style.css` / `app.js`。ヘッダ(最終更新・テーマ)→ 3 タブ(URL ハッシュ `#news` `#tips` `#reference`)→ 検索と絞り込み(種別: すべて/Web/YouTube/GitHub/X、**言語: すべて/日本語/English**、出典(**種別ごとのグループ**)、期間、お気に入りのみ)→ カード一覧。各カードに**出典名・種別バッジ・言語(JA/EN)・日付・元ページへのリンク(`rel="noopener noreferrer"`)**。タブの振り分け: YouTube・フォーラム・Qiita・Zenn=Tips、SideFX ニュース=ニュース、変更履歴と GitHub のリリース=リファレンス、X は設定で Tips / ニュース。データが空・読み込み失敗・絞り込みの結果なしは、それぞれ別のエンプティステート。**データ中の文字列は `textContent` だけで入れる**(`innerHTML` 不使用、`javascript:` の URL はリンクにしない)。CSS は `:root` のトークン(色・余白・タイプスケール)+ダーク 2 通り。390px〜1900px で横スクロールなし。

## 6. リファレンスの扱い

**リファレンスタブ = ①手で整えた公式ドキュメントの入口のリンク集(`data/reference.json`、2026-11-18 に到達確認)+ ②変更履歴の新着(自動)**。ドキュメントの本文は取らない(robots が版つきパスを禁止し、DevRAG が別途取り込んでいる)。リンクは増やし過ぎない(今は 13 本)。

## 7. ホスティングと毎日の実行

- `site/` は静的ファイルだけ。**Cloudflare Pages / Vercel / GitHub Pages のどれでも置ける。どこに置くかは運営者が決める**(2026-11-18 に Vercel を選択)。公開ディレクトリは `site/`。
- `.github/workflows/collect.yml`(**用意しただけ**。毎日 JST 06:17、テスト→収集→`data/` と `site/data/` をコミット)。リポジトリの作成・push・Actions の有効化は運営者。secret `X_BEARER_TOKEN` / `YOUTUBE_API_KEY` は**任意**(無くても動く)。
- **公開リポジトリ向けの安全装置**: リポジトリが公開だと `data/` の中身も公開される。そのため `data/sources.x.json` の **`publish_public`(既定 `false`)** が false の間は、公開物(`data/items.json`・`site/data/items.json`)に `kind: "x"` の項目を**出さない**。X を取得した場合はローカル専用の `data/items.x.local.json`(`.gitignore` 済み)にだけ出す。`true`(厳密に真偽値の true)にした時だけ公開物に含める(自己責任・X の規約を確認)。`collect.yml` は `X_BEARER_TOKEN` を**参照しない**(公開リポジトリでは X は手元でだけ動かす)。テストあり(false で公開物に出ない・true で出る・ローカルに出る・過去に公開物へ入っていた分も外れる)。
- **CI**: `.github/workflows/ci.yml` が push(main)と PR で `python -m unittest discover -s tests -t .` を回す(Python 3.12・権限は `contents: read`)。`collect.yml` とは別。
- **フッターの「関連サイト」**: 他の自作サイト(The-Algorithm-Illustrated・FoundationsEncyclopedia・ColorEncyclopedia)へのリンクと、「いま見ているサイト」としてこのサイト自身(`aria-current`・リンクにしない)を並べる。URL は `site/app.js` の定数 `RELATED_SITES` の 1 か所だけ。自サイトの `url` も入れてあるが、自分自身はリンクにならない(`self: true` か URL の origin が現在地と一致するとき)。同じタブで開く・`rel="noopener"`・動きなし。注記「お気に入り・テーマ・設定はサイトごとに別々に保存され、共有されません。」

## 8. YouTube と X

**YouTube**: 基本は公開フィード(キー不要)。任意で Data API 検索(「Houdini tutorial」「Houdini tips」の直近 7 日、`max_requests_per_run` 既定 5。`search.list` は **1 回 100 ユニット・無料枠は 1 日 10,000 = 1 日 100 回まで**。この収集は 5 回 = 500 ユニット)。保存は題名・動画 URL・チャンネル名・公開日・説明の先頭 200 字・タグだけ。サムネイルは使わない。API 由来のデータは **30 日で消す**(YouTube API Services の保存期間の規定は**未確認**。実装は安全側)。

**X(公式 API v2 のみ。スクレイピング・Nitter・非公式の中継は使わない)**
- **公開しない既定**: 公開リポジトリでは X の抜粋を公開しない。出したいときは `publish_public: true`(自己責任・規約を確認)。false の間の置き場は `data/items.x.local.json`(§7)。
- 動作: `data/sources.x.json` の `enabled: true` **かつ** 環境変数 `X_BEARER_TOKEN` がある時だけ動く。無ければ何もせず終える(エラーにしない)。トークンは読み出して表示・ログ・保存しない。取得は直近検索(`/2/tweets/search/recent`)を `tweet.fields=created_at,lang` + 投稿者の `username` だけで行う。追跡アカウントは検索の `from:<handle>` で扱う(`sidefx` は SideFX 公式サイトのフッターのリンク `twitter.com/sidefx` から確認)。`since_id` を `x_usage.json` に持ち、同じ投稿を再び読まない。
- **費用の安全装置**: ①1 回の実行で読む投稿の上限 `max_posts_per_run`(既定 50)②月の上限 `monthly_post_budget`(既定 1500)と `data/x_usage.json`(年月ごと。超えたらその月は X をスキップして記録)③ドライラン `python -m collector --dry-run`(取得せず見込みの件数と仮の金額だけ出す)。削除の照会も予算に数える。
- **単価は未確認**: 従量課金(クレジットを先に購入して消費)。第三者の記事に「読み取り 1 投稿あたり約 US$0.005」とあるが、公式の post-cap ページには単価の記載が無い(エンドポイント・操作・データの範囲で変わる。**開発者コンソールで運営者が確認**)。`assumed_usd_per_post` は仮の値。月間キャップは 300 万投稿の読み取り(公式ページ)。
- **保存と保持**: 投稿 ID・URL・ハンドル・日付・本文の先頭 200 字・タグ。**30 日で消す**。**削除への追従**: 毎回、保存している 30 日以内の投稿 ID を 100 件ずつ照会し、**返ってこないもの(削除・非公開)は `items.json` から消す**。照会に失敗した時は何も消さない。
- **表示**: 各項目に「X」の出典名・ハンドル・日付・元の投稿へのリンクを出し、「X の投稿は削除・変更されることがあります。元の投稿で確認してください。」を付ける。X のロゴは使わず文字の「X」だけ。
- **規約の要約(公式ドキュメント)**: 表示要件(`https://docs.x.com/developer-terms/display-requirements`、2026-11-18 に確認)は、投稿者のアイコン・表示名・@ユーザー名をプロフィールにリンクして出す/本文を**改変せず**出す/日時を投稿のパーマリンクにする/各投稿の右上か一覧の先頭に**公式の X ロゴ**を出す/返信・リポスト・いいねは Web Intents かログイン済みの API、または「View on X」を日時の横に出す、など。**削除への追従は、このページには書かれておらず**、開発者契約・ポリシー(`https://developer.x.com/en/developer-terms/agreement-and-policy` を運営者が確認)に従う想定(**未確認**)。課金と上限は `https://docs.x.com/x-api/fundamentals/post-cap`。
- **この実装が満たしていない点(リスク)**: 本文を 200 字で切っている(表示要件は「改変なし」)・アイコンと公式ロゴを出していない(運営者の判断)。**個人+少人数の閲覧用で、元の投稿へのリンクを必ず付ける**ことで割り切っているが、規約に完全に沿うわけではない。気になるなら X を無効のままにする。

**運営者が決めること(X を使う場合の手順)**
1. X の開発者アカウントを作る(`https://developer.x.com`)→ アプリを作り、**Bearer トークン**を発行する。
2. 開発者コンソールで**単価を確認**し、クレジットを購入する(上限の金額を決める)。月の上限 `monthly_post_budget` を、その金額に見合う投稿数に直す。
3. 手元で試す: `python -m collector --dry-run`(取得しない)→ `$env:X_BEARER_TOKEN="…"`(PowerShell。履歴に残さない)→ `data/sources.x.json` の `enabled` を `true` → `python -m collector`。
4. Actions では X を動かさない(`collect.yml` は `X_BEARER_TOKEN` を参照しない)。X は手元でだけ動かす。公開物にも載せたい場合だけ `publish_public: true`(自己責任)。

## 9. 状態

| 項目 | 状態 |
|---|---|
| 収集器(RSS/Atom・YouTube フィード・GitHub リリース API・正規化・重複除去(URL・動画 ID・題名)・日英のタグと言語・失敗に強い・条件付き GET・ホスト交互の取得) | 実装済み(実フィード/実 API で確認、63 テスト) |
| YouTube Data API 検索 | 実装済み(偽サーバーでテスト)・実機は**未確認** |
| X 公式 API | 実装済み(偽サーバーでテスト)・実機は**未確認**(トークン無し) |
| サイト(3 タブ・検索・絞り込み・お気に入り・テーマ・エンプティ・XSS 対策) | 実装済み(Playwright で確認) |
| Actions のワークフロー(`collect.yml`・`ci.yml`) | ファイルのみ・**未確認**(有効化していない) |
| X の公開物からの除外(`publish_public`)・関連サイトのフッター | 実装済み(テスト 63 件・Playwright で確認) |
| ホスティング | **実装済み**(Vercel。`site/` を公開ディレクトリにして Git 連携) |
| `git init` 済み・commit なし | — |
