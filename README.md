# BizDev - AI技術事業化支援プロトタイプ (第2版)

## 概要 (Overview)

このリポジトリは、企業や大学の研究者、技術系スタートアップ等が、保有する技術シーズの初期的な事業化検討を行うことを支援するためのStreamlitアプリケーションのプロトタイプです。
Google Gemini API を活用し、多段階の分析フレームワーク（ターゲット戦略、課題整理、Value Proposition Canvas、Lean Canvas、MVP検討、SWOT分析、4P分析、3C分析、初期財務計画、競合分析、Moat定義、ピッチ資料骨子生成、VC視点レビュー）を通じて、ユーザーの事業化検討を網羅的にサポートします。

## 主な機能 (Features)

本プロトタイプは、以下のステップで構成される機能を提供し、各ステップでAIによる分析・提案とユーザーによる編集・考察を組み合わせます。

1.  **ステップ0: 技術概要入力**
    * 検討対象となる技術の基本情報（名称、解決したい課題、特徴・新規性、応用分野、補足）を入力します。
2.  **ステップ1: 壁打ち（初期アイデア形成）**
    * **ターゲット戦略:** AIが技術概要に基づき、有望なターゲット市場や顧客像のアイデアを複数提案。ユーザーはそれを選択、または自由記述で独自のターゲットを設定。
    * **課題整理:** 選択されたターゲット顧客が抱える可能性のある課題をAIがリストアップ。ユーザーは特に注目する課題を選択。
    * **Value Proposition Canvas (VPC) 作成支援:** AIがこれまでの情報を元にVPCの6ブロックのドラフトを作成。ユーザーは内容を編集・追記。
3.  **ステップ2a: Lean Canvas ドラフト + 品質スコア**
    * AIが技術概要、ターゲット、選択された課題、VPCの内容を元にLean Canvasの9ブロックのドラフトを作成し、その品質スコア（AIによる評価）も提示。ユーザーは内容を編集可能。Web検索による市場調査情報も活用。
4.  **ステップ2b: 顧客インタビュー支援 (任意/スキップ可)**
    * (現バージョンではプレースホルダー、将来的にインタビュー候補や項目のAI提案、結果記録機能などを実装予定)
5.  **ステップ3: 深掘り分析**
    * 以下の各分析フレームワークについて、AIが初期案を自動生成。ユーザーは内容を確認し、考察を追記可能。
        * MVP (Minimum Viable Product) の検討
        * SWOT分析 (強み・弱み・機会・脅威)
        * 4P分析 (Product, Price, Place, Promotion)
        * 3C分析 (Customer, Competitor, Company)
        * 財務計画（初期アイデア：主要収益源、コスト構造、考慮事項）
6.  **ステップ4: 競合分析 → 優位性 (Moat) 整理**
    * **競合分析:** AIが検索キーワードを生成し、Google Custom Search APIを利用したWeb検索結果も加味して詳細な競合分析を実行。
    * **Moat定義:** AIがこれまでの分析に基づき、持続可能な競争優位性（Moat）のステートメント案を複数提案。ユーザーは参考にして最終的なMoatを定義。
7.  **ステップ5: ピッチ資料自動生成**
    * ステップ0〜4で整理・生成された全情報をAIが集約・要約。
    * 指定された11項目構成（タイトル、顧客課題、解決策、市場規模、競合、差別化/Moat、ビジネスモデル、なぜ今か、なぜ自分か、事業計画骨子、収支計画概算）のピッチ資料骨子を自動生成。（根拠の示唆を含む）
8.  **ステップ6: VC/役員レビュー**
    * 生成されたピッチ資料骨子を、AI（VCペルソナ）がレビュー。
    * 事業評価スコア、課題リスト、具体的なNext Actionをフィードバックとして自動生成。

## 技術スタック (Technology Stack)

* Python 3.10+
* Streamlit
* Google Generative AI (Gemini API)
* Google Custom Search JSON API (競合分析・市場調査用)
* `duckduckgo-search` (以前のバージョンで使用、現在はGoogle APIに移行)

## ローカルでの実行方法 (Local Setup)

1.  **リポジトリをクローン:**
    ```bash
    git clone [https://github.com/CholoQ/BizDev.git](https://github.com/CholoQ/BizDev.git)
    cd BizDev
    ```
2.  **仮想環境の作成と有効化:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **必要なライブラリのインストール:**
    ```bash
    pip install -r requirements.txt
    ```
    (`requirements.txt` には `streamlit`, `google-generativeai`, `google-api-python-client` などが含まれていることを確認してください。)
4.  **APIキーの設定:**
    * プロジェクトルートに `.streamlit` フォルダを作成します。
    * `.streamlit` フォルダ内に `secrets.toml` ファイルを作成します。
    * `secrets.toml` に以下のように記述します（キーはご自身のものに置き換えてください）:
        ```toml
        GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
        GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY_HERE"
        SEARCH_ENGINE_ID = "YOUR_Google Search_ENGINE_ID_HERE"
        ```
5.  **アプリの実行:**
    ```bash
    streamlit run app.py
    ```
    または
    ```bash
    python -m streamlit run app.py
    ```

## デプロイ (Deployment)

このアプリはStreamlit Community Cloudにデプロイされています。
（`https://bizdev-nnqlvf92cgc2fyj6pdhcc9.streamlit.app`）

## 今後の展望・課題 (Future Plans / Issues)

* 各分析結果のAI応答のパース精度向上と、よりインタラクティブな編集UIの実現。
* プロンプトエンジニアリングによるAI分析の質と一貫性の向上。
* 「Evidence バッジ」機能の具体的な実装。
* 顧客インタビュー支援機能（ステップ2b）の実装。
* 助成金マッチング機能の検討。
* 各ステップの解説文のさらなる充実。
* AI生成文章の視認性向上（箇条書き、表形式の積極的な活用）。
* クロスSWOT分析機能の追加。

---