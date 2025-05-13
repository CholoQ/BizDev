# ------app.pyのシンプル版、技術概要を入れるとピッチ資料を自動作成--------

import streamlit as st
import google.generativeai as genai
import os
# import re # 正規表現モジュールをインポート

# --- APIキーの設定 (変更なし) ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"APIキーの設定でエラーが発生しました。st.secretsを確認してください。エラー: {e}")
    st.stop()

# --- Session Stateの初期化 (簡易版用にシンプルに) ---
if 'tech_summary_simple' not in st.session_state:
    st.session_state.tech_summary_simple = ""
if 'simple_pitch_deck_text' not in st.session_state:
    st.session_state.simple_pitch_deck_text = ""

# --- Streamlit UI部分 ---
st.title("技術概要からピッチ資料骨子を自動生成")

# ↓↓↓ 項目1: 注意喚起の追加 ↓↓↓
st.warning("""
**【重要】入力情報に関するご注意**\n
本サービスはAIによる分析支援プロトタイプです。機密情報や個人を特定できる情報は絶対に入力しないでください。
入力された情報は、本サービスのAI分析処理にのみ利用されます。
""")
# ↑↑↑ 項目1: 注意喚起の追加 ↑↑↑

st.caption("あなたの技術について教えてください。AIが必要な分析を内部的に行い、ピッチ資料の骨子を生成します。")
st.divider()

# --- 技術概要入力フォーム ---
with st.form(key='tech_input_form_simple'):
    st.subheader("技術の基本情報（必須4項目）")
    tech_name = st.text_input("技術の名称", key="simple_tech_name")
    problem_to_solve = st.text_area("この技術で解決したい課題", height=100, key="simple_problem")
    tech_features = st.text_area("技術的な特徴・新規性", height=150, key="simple_features")
    application_areas = st.text_area("応用できそうな分野・用途", height=100, key="simple_areas")

    st.subheader("補足情報（任意）")
    free_text = st.text_area("その他、市場や顧客に関するアイデア、特記事項など自由にお書きください", height=150, key="simple_free_text")

    # ピッチ資料生成ボタン
    submitted_simple = st.form_submit_button("AIにピッチ資料骨子を生成させる")

    if submitted_simple:
        if tech_name and problem_to_solve and tech_features and application_areas:
            # 技術概要をsession_stateに保存
            st.session_state.tech_summary_simple = f"""
            技術の名称: {tech_name}
            解決したい課題: {problem_to_solve}
            技術的な特徴・新規性: {tech_features}
            応用できそうな分野・用途: {application_areas}
            補足情報: {free_text if free_text else 'なし'}
            """
            st.session_state.simple_pitch_deck_text = "" # 前回の結果をクリア

            # --- ★★★ ここからAI呼び出しと包括的プロンプト作成 ★★★ ---
            st.info("AIがピッチ資料骨子を生成中です... しばらくお待ちください。")
# (app_simple.py の if submitted_simple: ブロック内)

            # 包括的プロンプトの設計
            comprehensive_prompt = f"""あなたは経験豊富な事業開発コンサルタント兼ピッチ資料作成の専門家です。
            提供された「技術概要」のみを元に、あなた自身の知識と推論を最大限に活用し、以下の11項目から成る事業ピッチ資料の骨子を作成してください。
            各項目について、市場調査、競合分析、ビジネスモデル検討、SWOT分析などの観点を内部的に考慮し、**主要なポイントを簡潔な箇条書き中心で**記述してください。
            Web検索機能は利用できません。提供された技術概要から論理的に導き出せる範囲で、可能な限り質の高い提案をお願いします。

            # 提供された技術概要:
            {st.session_state.tech_summary_simple}

            # 作成するピッチ資料の構成項目 (必ずこの11項目と順番で、各項目を見出しとして記述。各項目の内容は箇条書きを基本とする):
            ## 1. タイトル
            * [事業タイトル案を1つ提案]
            * [そのタイトルを補足するキャッチコピーを1つ提案]

            ## 2. 顧客の課題
            [技術概要から推測されるターゲット顧客が抱える最も重要な課題を**箇条書きで3点**具体的に記述]

            ## 3. 解決策
            [技術概要を元に、上記の課題をどのように解決するのか、その解決策の**主要なポイントを箇条書きで**明確に記述]

            ## 4. 市場規模
            [技術の応用分野から推測される市場の魅力度や規模感について、主要なポイントやデータを示唆する形で**箇条書きで**記述。具体的な数値が不明な場合はその旨と、調査すべき点を記載]

            ## 5. 競合
            [技術概要から想定される主要な競合（代替手段含む）とその特徴を**箇条書きで2-3社（または2-3タイプ）**簡潔に記述。不明な場合は「詳細な競合調査が必要」と付記]

            ## 6. 差別化ポイント・優位性（Moat含む）
            [技術的な特徴や新規性を元に、競合に対する明確なアドバンテージや模倣困難性を**箇条書きで3-5点**説明]

            ## 7. ビジネスモデル
            [考えられる主要な収益化の方法（例：製品販売、ライセンス、サービス提供など）と、そのビジネスモデルの**骨子を箇条書きで**説明。主要な収益源とターゲット顧客ごとの価格設定の考え方を含む]

            ## 8. なぜ今か
            [市場トレンド、技術的進展、社会情勢などを一般的な知見から推測し、今この事業を始めるべき理由を**箇条書きで3点**説明]

            ## 9. なぜ自分（この会社）か
            [提供された技術概要の強みを元に、この事業を（仮の主体として）成功させられる理由を**箇条書きで3点**記述]

            ## 10. 事業計画の骨子（3年）
            [MVP開発から始め、段階的にどのようなマイルストーン（例：ユーザー獲得、製品開発、収益化達成など）を目指すかの概要を**主要な段階ごとに箇条書きで**提案]

            ## 11. 収支計画の概算（3年）
            [主要な収益源と想定されるコスト構造から、非常に大まかな収益と費用の見通し、必要な初期投資の規模感など、**考慮すべき主要項目を箇条書きで**示唆。具体的な数値予測ではなく、構造と考え方を示す]

            ---
            各項目の内容は、投資家や経営層に伝えることを意識し、**全体として簡潔でポイントが明確になるように**してください。マークダウン形式で記述してください。
            """

            try:
                with st.spinner("Geminiが全力でピッチ資料を生成中..."):
                    response_pitch = model.generate_content(comprehensive_prompt)
                    st.session_state.simple_pitch_deck_text = response_pitch.text
                    st.success("ピッチ資料骨子の生成が完了しました！")
            except Exception as e:
                st.error(f"ピッチ資料骨子生成中にエラーが発生しました: {e}")
                st.session_state.simple_pitch_deck_text = "ピッチ資料骨子の生成に失敗しました。"
            # --- ★★★ AI呼び出しここまで ★★★ ---
        else:
            st.warning("技術の基本情報（名称、課題、特徴、応用分野）は入力必須です。")
       
        # --- 生成されたピッチ資料骨子の表示 ---
if st.session_state.simple_pitch_deck_text:
    st.divider()
    st.subheader("生成されたピッチ資料骨子（AIによる全自動生成）")
    st.markdown(st.session_state.simple_pitch_deck_text)
    # コピーボタン (簡易版)
    if st.button("骨子をクリップボードにコピー", key="copy_simple_pitch"):
         st.success("コピーしました！（実際にはテキストを選択してコピーしてください）")
    
    # ↓↓↓ 項目2 & 4: アンケートと有料版誘導の追加 ↓↓↓
    st.divider()
    st.subheader("フィードバックにご協力ください")
    st.markdown("""
    本プロトタイプをお試しいただきありがとうございます。今後のサービス改善のため、ぜひ簡単なアンケートにご協力ください。
    
    [アンケートに回答する](https://docs.google.com/forms/d/1FVC1RTx6dFhrYdPlLFS2IQTMe86vewdfW6Hlb98ysbQ/edit)
    """) # ★実際のURLに置き換えてください★

    st.info("""
    **お知らせ:** より詳細な市場分析、競合分析、専門家によるレビュー機能などを含む多機能版・有料版を現在開発中です。
    ご興味のある方は、アンケート内でメールアドレスをご登録ください。
    """)
    # ↑↑↑ 項目2 & 4: アンケートと有料版誘導の追加 ↑↑↑


# ↓↓↓ 項目3 & 5: プライバシーポリシー/ログ非保存の明示、利用規約 & 免責表示の追加 ↓↓↓
st.divider()
with st.expander("ご利用にあたっての注意・免責事項（必ずお読みください）"):
    st.markdown("""
    **本サービス利用上の注意**

    * **機密情報の非入力:** 本サービスに入力する情報に、個人情報、企業の機密情報、その他公開を意図しない情報を含めないでください。入力された情報はAIモデルの分析処理に使用されますが、その過程での情報の取り扱いについて、開発者は一切の責任を負いません。
    * **ログの非保存:** ユーザー様が入力した技術概要やAIとのやり取りに関する具体的な内容は、本サービスのサーバー等には一切保存されません。ブラウザを閉じるか、セッションが終了すると、入力された情報は失われます。
    * **AI生成内容の正確性:** AIが生成する内容は、あくまで提案やアイデアのたたき台であり、その正確性、完全性、特定目的への適合性を保証するものではありません。生成された情報を利用する際は、必ずご自身の責任において内容を検証・判断してください。
    * **著作権等:** 入力する情報が第三者の著作権やその他の権利を侵害しないよう十分ご注意ください。

    **免責事項**

    * 本サービスの利用により、利用者または第三者が被ったいかなる不利益または損害について、理由を問わず開発者は一切の責任を負わないものとします。
    * 本サービスは、予告なく内容の変更、中断、または終了することがあります。

    **利用規約への同意**

    * 本サービスを利用することにより、上記の利用上の注意および免責事項に同意したものとみなします。
    """)
# ↑↑↑ 項目3 & 5: プライバシーポリシー/ログ非保存の明示、利用規約 & 免責表示の追加 ↑↑↑