# BizDev - 技術事業化支援AIプロトタイプ

## 概要 (Overview)

このリポジトリは、企業や大学の研究者、技術系スタートアップ等が、保有する技術シーズの初期的な事業化検討を行うことを支援するためのStreamlitアプリケーションのプロトタイプです。
Google Gemini API を活用し、対話的なプロセスを通じて事業アイデアの創出から事業性評価までをサポートします。

## 主な機能 (Features)

本プロトタイプは、以下のステップを通じてユーザーの事業化検討を支援します。

1.  **ステップ0: 技術概要入力:** 検討対象となる技術の基本情報を入力します。
2.  **ステップ1: 壁打ち:**
    * AIがターゲット戦略（市場セグメント/顧客像）のアイデアを提案します。
    * ユーザーがターゲットを選択し、AIがそのターゲットの潜在的な課題をリストアップします。
    * AIの支援を受けながらValue Proposition Canvasを作成・編集します。
3.  **ステップ2a: Lean Canvas:**
    * AIがこれまでの情報を元にLean Canvasのドラフトを作成し、品質スコアを提示します。
    * ユーザーは内容を編集できます。
4.  **ステップ2b: 顧客インタビュー (任意):** (現バージョンでは未実装のプレースホルダー)
5.  **ステップ3: 深掘り:**
    * AIがMVP（Minimum Viable Product）案を提案します。
    * AIがSWOT分析を実行します。
    * AIが4P分析（Product, Price, Place, Promotion）の戦略案を提案します。
    * AIが3C分析（Customer, Competitor, Company）を実行します。
    * AIが財務計画の初期的な考慮事項（収益源、コスト構造など）を提案します。
    * ユーザーは各分析結果を確認し、考察を追記できます。
6.  **ステップ4: 競合分析 → 優位性 (Moat) 整理:**
    * AIが競合の詳細分析を行います。
    * AIがこれまでの分析に基づき、持続可能な競争優位性（Moat）のステートメント案を提案します。
    * ユーザーは最終的なMoatを定義します。
7.  **ステップ5: ピッチ資料自動生成:**
    * AIがステップ0〜4の全情報を統合し、11項目構成のピッチ資料骨子を自動生成します。（根拠の示唆を含む）
8.  **ステップ6: VC/役員レビュー:**
    * AI（VCペルソナ）が生成されたピッチ資料骨子をレビューし、評価スコア、課題リスト、Next Actionを提示します。

## 技術スタック (Technology Stack)

* Python 3.10+
* Streamlit
* Google Generative AI (Gemini API)

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
    (もし `requirements.txt` がまだ無い場合は、`pip freeze > requirements.txt` で作成してください。)
4.  **APIキーの設定:**
    * プロジェクトルートに `.streamlit` フォルダを作成します。
    * `.streamlit` フォルダ内に `secrets.toml` ファイルを作成します。
    * `secrets.toml` に以下のように記述します（キーはご自身のものに置き換えてください）:
        ```toml
        GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
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

## 今後の展望 (Future Plans)

* 各ステップのAI応答のパース精度向上とUI改善
* プロンプトエンジニアリングによるAI分析の質向上
* 顧客インタビュー支援機能（ステップ2b）の実装
* 助成金マッチング機能の追加検討
* レポートのエクスポート機能

---