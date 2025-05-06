import streamlit as st
import google.generativeai as genai
import os
import re # 正規表現モジュールをインポート

# --- APIキーの設定 (変更なし) ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"APIキーの設定でエラーが発生しました。st.secretsを確認してください。エラー: {e}")
    st.stop()

# --- Session Stateの初期化 ---
# st.session_stateを初期化して、アプリの実行間でデータを保持できるようにする
if 'step' not in st.session_state:
    st.session_state.step = 1 # 現在のステップを管理
if 'tech_summary' not in st.session_state:
    st.session_state.tech_summary = ""
if 'initial_report_and_stories' not in st.session_state:
    st.session_state.initial_report_and_stories = ""
if 'selected_stories' not in st.session_state:
    st.session_state.selected_stories = {} # { 'ストーリー名': '内容' }

# --- Streamlit UI部分 ---
st.title("技術事業化支援サービス プロトタイプ")

# --- ステップ1: 技術概要の入力 ---
if st.session_state.step == 1:
    st.header("ステップ1: 技術概要の入力")
    st.caption("あなたの技術について教えてください。")

    with st.form(key='tech_input_form'):
        st.subheader("技術の基本情報")
        tech_name = st.text_input("技術の名称", key="tech_name")
        problem_to_solve = st.text_area("この技術で解決したい課題", height=100, key="problem")
        tech_features = st.text_area("技術的な特徴・新規性", height=150, key="features")
        application_areas = st.text_area("応用できそうな分野・用途", height=100, key="areas")

        st.subheader("補足情報")
        free_text = st.text_area("その他、市場や顧客に関するアイデア、特記事項など自由にお書きください", height=150, key="free_text")

        # レポート生成ボタン (フォーム内)
        submitted = st.form_submit_button("レポートとストーリー案を生成")

        if submitted:
            if tech_name and problem_to_solve and tech_features and application_areas:
                st.session_state.tech_summary = f"""
                技術の名称: {tech_name}
                解決したい課題: {problem_to_solve}
                技術的な特徴・新規性: {tech_features}
                応用できそうな分野・用途: {application_areas}
                補足情報: {free_text if free_text else 'なし'}
                """

                prompt = f"""(# ... (初期レポート生成の指示はそのまま) ...

                        ---
                        さらに、上記の情報（技術概要と初期レポートの内容）を踏まえ、具体的な「事業ストーリー案」を3つ提案してください。
                        各ストーリー案は、必ず以下の項目立てで、それぞれの内容を具体的に記述してください。

                        --- 事業ストーリー案フォーマット ---

                        **ストーリー案1:**
                        * **顧客（ターゲット）:** [具体的な顧客像やセグメント]
                        * **課題:** [ターゲット顧客が抱えている具体的な課題・ペイン]
                        * **この技術による解決法:** [あなたの技術がその課題をどのように解決するか]
                        * **この技術が与える価値:** [解決によって顧客が得られる具体的な価値・メリット]
                        * **選択優位性:** [競合と比較して、なぜこの技術・アプローチが選ばれるのか]

                        **ストーリー案2:**
                        * **顧客（ターゲット）:** [具体的な顧客像やセグメント]
                        * **課題:** [ターゲット顧客が抱えている具体的な課題・ペイン]
                        * **この技術による解決法:** [あなたの技術がその課題をどのように解決するか]
                        * **この技術が与える価値:** [解決によって顧客が得られる具体的な価値・メリット]
                        * **選択優位性:** [競合と比較して、なぜこの技術・アプローチが選ばれるのか]

                        **ストーリー案3:**
                        * **顧客（ターゲット）:** [具体的な顧客像やセグメント]
                        * **課題:** [ターゲット顧客が抱えている具体的な課題・ペイン]
                        * **この技術による解決法:** [あなたの技術がその課題をどのように解決するか]
                        * **この技術が与える価値:** [解決によって顧客が得られる具体的な価値・メリット]
                        * **選択優位性:** [競合と比較して、なぜこの技術・アプローチが選ばれるのか])""" # ここに前回の長いプロンプトが入る

                try:
                    with st.spinner('Geminiがレポートとストーリー案を生成中です...'):
                        response = model.generate_content(st.session_state.tech_summary + "\n" + prompt) # 技術概要もプロンプトに含める例
                        st.session_state.initial_report_and_stories = response.text
                        st.session_state.step = 1.5 # 次のステップへ
                        st.rerun() # 画面を再描画してステップ1.5を表示

                except Exception as e:
                    st.error(f"生成中にエラーが発生しました: {e}")
            else:
                st.warning("技術の基本情報（名称、課題、特徴、応用分野）は入力必須です。")

# --- ステップ1.5: ストーリー選抜・修正 ---
elif st.session_state.step == 1.5: # ← インデントレベル0
    # この下はすべてインデントレベル1以上
    st.header("ステップ1.5: ストーリー選抜・修正")
    st.caption("AIが提案したストーリー案を確認し、有望なものを選んで修正してください。")

    # --- デバッグ用表示 ---
    st.divider()
    st.subheader("【デバッグ用】APIからの生の応答")
    st.text_area("API Raw Response", st.session_state.initial_report_and_stories, height=300)
    st.divider()

    # --- ストーリー抽出ロジック (ここからインデント追加) ---
    st.subheader("生成された初期レポートと事業ストーリー案の抽出試行") # ← インデントレベル1

    edited_stories = {} # ← インデントレベル1
    selected_story_keys = [] # ← インデントレベル1
    story_data_to_display = [] # ← インデントレベル1

    current_story_title = None # ← インデントレベル1
    current_story_content = [] # ← インデントレベル1
    if st.session_state.initial_report_and_stories: # ← インデントレベル1
        lines = st.session_state.initial_report_and_stories.splitlines() # ← インデントレベル2
        for line in lines:
            if re.match(r"\*\*ストーリー案\d+:", line):
                # --- ↓↓↓ 以下の正しい抽出ロジックに置き換えてください ↓↓↓ ---
                current_story_title = None
                current_story_content = []
                story_data_to_display = [] # Initialize list
                # st.session_state.initial_report_and_storiesが存在するか確認
                if st.session_state.initial_report_and_stories:
                    lines = st.session_state.initial_report_and_stories.splitlines() # 応答を1行ずつに分割

                    for line in lines: # Loop through lines
                        line = line.strip()
                        # 新しいストーリー案のタイトル行か？ (太字形式を想定)
                        if line.startswith("**ストーリー案"): # ← '**'で始まるかチェック
                            # 前のストーリーが完了していればリストに追加
                            if current_story_title is not None and current_story_content:
                                story_data_to_display.append({ # <--- 辞書を追加
                                    "title": current_story_title,
                                    "content": "\n".join(current_story_content).strip()
                                })
                            # 新しいストーリーの情報を初期化
                            current_story_title = line # タイトル行全体を保持
                            current_story_content = []
                        # タイトルが見つかった後の内容行か？
                        elif current_story_title is not None and line: # 内容行を収集
                            current_story_content.append(line)

                    # 最後のストーリーをリストに追加
                    if current_story_title is not None and current_story_content:
                        story_data_to_display.append({ # <--- 辞書を追加
                            "title": current_story_title,
                            "content": "\n".join(current_story_content).strip()
                        })
                else:
                    st.warning("APIからの応答がありません。")
    # --- ↑↑↑ 正しい抽出ロジックはここまで ↑↑↑ ---
    else: # ← インデントレベル1
        st.warning("APIからの応答がありません。") # ← インデントレベル2

    if not story_data_to_display: # ← インデントレベル1
        st.warning("ストーリー案が見つかりませんでした。応答形式を確認してください。") # ← インデントレベル2

    # --- 選抜・修正フォーム ---
    with st.form(key='story_selection_form'): # ← インデントレベル1
        st.subheader("事業ストーリー案の選抜と修正") # ← インデントレベル2
        if not story_data_to_display: # ← インデントレベル2
            st.write("（表示できるストーリー案がありません）") # ← インデントレベル3

        # forループで各ストーリーのUI要素を表示
        for i, story_data in enumerate(story_data_to_display): # ← インデントレベル2
            # ↓↓↓ ループ内の完全なコードはここから ↓↓↓

            # titleから表示名（ストーリー案X）を抽出する試み
            # タイトルが '**ストーリー案X**' のような形式であることを想定
            story_name_match = re.search(r"\*\*(ストーリー案\s?\d+)\*\*", story_data["title"])
            story_display_name = story_name_match.group(1) if story_name_match else f"ストーリー {i+1}"

            st.markdown(f"---")
            st.write(story_data['title']) # 太字のタイトルを表示

            key_suffix = f"story_{i+1}" # 各ウィジェットを区別するためのキー接尾辞

            # st.session_stateに初期値を設定（初回のみ）
            # ユーザーが編集できるように、内容はここに保持
            if key_suffix not in st.session_state:
                st.session_state[key_suffix] = story_data["content"]

            # チェックボックスで選抜
            # is_selected変数には、チェックボックスがONかOFFか(True/False)が入る
            is_selected = st.checkbox(f"**{story_display_name}** を選抜する", value=False, key=f"select_{key_suffix}")

            # テキストエリアで修正可能にする
            # valueにはsession_stateの内容を表示し、編集されたらそれが反映される
            edited_content = st.text_area(f"内容（{story_display_name} - 編集可）:", value=st.session_state[key_suffix], height=250, key=f"edit_{key_suffix}")

            # 編集された内容をリアルタイムでsession_stateに反映（任意ですが、戻ってきたときに編集内容を保持できる）
            st.session_state[key_suffix] = edited_content

            # もしこのストーリーが選抜されたら、送信時に使う辞書に格納
            if is_selected:
                selected_story_keys.append(story_display_name) # どのストーリーが選ばれたか名前を記録（不要かも）
                # 重要なのは編集後の内容 (edited_content) を辞書に入れること
                edited_stories[story_display_name] = edited_content

            # --- ↑↑↑ ループ内の完全なコードはここまで ↑↑↑
        # <--- for ループはここで終わる

        # ↓↓↓ ボタンは for ループの外、with st.form の中に置く ↓↓↓
        submitted_selection = st.form_submit_button("選抜・修正を完了し、ステップ2へ進む") # ← インデントレベル2

        # ↓↓↓ この if も for ループの外、with st.form の中に置く ↓↓↓
        if submitted_selection: # ← インデントレベル2
            # --- ここに送信処理のコードが入る ---
            
            if not edited_stories:
                 st.warning(...)
            else:
                 st.session_state.selected_stories = edited_stories
                 st.session_state.step = 2
                 st.success(...)
                 st.rerun()
            # --- 送信処理はここまで ---
    # <--- with st.form(...) ブロックはここで終わる (インデントレベル1の終わり)

# --- ステップ2: 仮説レポート作成 ---
elif st.session_state.step == 2:
    st.header("ステップ2: 仮説レポート作成")
    st.caption("選抜したストーリーについて、詳細情報を入力（任意）し、AIによる深掘りレポートを作成します。")
    st.divider()

    # --- 選抜されたストーリーの表示 ---
    st.subheader("選抜・修正されたストーリー")
    if isinstance(st.session_state.selected_stories, dict) and st.session_state.selected_stories:
        for story_name, story_content in st.session_state.selected_stories.items():
            with st.expander(f"**{story_name}** の内容", expanded=False): # エキスパンダーで表示
                st.text_area(f"内容 ({story_name})", story_content, height=200, disabled=True, key=f"display_{story_name}_step2")
    else:
        st.warning("選抜されたストーリーがありません。ステップ1.5に戻ってください。")
        if st.button("ステップ1.5に戻る"):
            st.session_state.step = 1.5
            st.rerun()
        st.stop() # ストーリーがない場合はここで停止

    st.divider()

    # --- 仮説レポート作成フォーム ---
    st.subheader("詳細情報の入力（任意）")
    st.caption("各項目について、補足情報や具体的なアイデアがあれば入力してください。空欄の場合はAIが情報を補完します。")
# (ステップ2のelifブロック内)
# ... (選抜されたストーリー表示の後) ...

    with st.form(key='hypothesis_report_form_pitch_deck'):
        st.subheader("ピッチ資料項目別 詳細情報入力（任意）")
        st.caption("各項目について、補足情報や具体的なアイデアがあれば入力してください。空欄の場合はAIが情報を補完・提案します。")

        # ピッチ資料の項目に合わせた入力欄 (一部抜粋、必要に応じて追加・修正)
        user_input_customer_problem = st.text_area("2. 顧客の課題（さらに深掘りした内容など）", height=100)
        # user_input_solution = st.text_area("3. 解決策（ストーリーに基づく詳細）", height=150) # ストーリーからAIが主体的に生成する方が良いかも
        user_input_market_size = st.text_area("4. 市場規模（具体的なデータ、出典など）", height=100)
        user_input_competition = st.text_area("5. 競合（追加情報、分析など）", height=100)
        user_input_differentiation = st.text_area("6. 差別化ポイント・優位性（さらに具体的に）", height=150)
        user_input_business_model = st.text_area("7. ビジネスモデル（収益源、価格設定など具体的に）", height=150)
        user_input_why_now = st.text_area("8. なぜ今か（市場トレンド、技術的背景など）", height=100)
        user_input_why_us = st.text_area("9. なぜ自分か（チームの強み、独自リソースなど）", height=100)
        user_input_3yr_plan_notes = st.text_area("10. ３年間の事業計画（主要マイルストーン、KPIなどのアイデア）", height=150)
        user_input_3yr_finance_notes = st.text_area("11. ３年間の収支計画（概算の売上・費用目標などのアイデア）", height=150)

        submitted_pitch_report_gen = st.form_submit_button("ピッチ構成仮説レポートを作成")

        if submitted_pitch_report_gen:
            st.info("ピッチ構成仮説レポートの生成を開始します...")
            # ユーザー入力を辞書にまとめる
            user_all_inputs = {
                "顧客の課題": user_input_customer_problem,
                "市場規模": user_input_market_size,
                "競合": user_input_competition,
                "差別化ポイント": user_input_differentiation,
                "ビジネスモデル": user_input_business_model,
                "なぜ今か": user_input_why_now,
                "なぜ自分か": user_input_why_us,
                "事業計画メモ": user_input_3yr_plan_notes,
                "収支計画メモ": user_input_3yr_finance_notes,
            }

            all_pitch_reports = {}
            for story_name, story_content in st.session_state.selected_stories.items():
                st.write(f"'{story_name}' のピッチ構成レポートを生成中...")

                # AIへの指示プロンプト (大幅に詳細化)
                pitch_prompt = f"""以下の「技術概要」と「事業ストーリー」を元に、提示された「ユーザーからの補足情報」も最大限活用し、下記の13項目のピッチ資料構成に沿った「仮説レポート」を作成してください。
                各項目について、具体的かつ論理的な内容を記述してください。情報が不足している場合は、推測や一般的な知見に基づいて補完するか、さらなる調査が必要な点を指摘してください。
                「チーム」や「トラクション」など、事実に基づく情報はユーザー入力がない限り生成できませんが、その場合は「ユーザーによる記述が必要」と明記してください。

                # 技術概要:
                {st.session_state.tech_summary}

                # 事業ストーリー: {story_name}
                {story_content}

                # ユーザーからの補足情報:
                {chr(10).join([f"- {key}: {value}" for key, value in user_all_inputs.items() if value])}

                # 出力すべきピッチ資料構成項目 (この順番と見出しで出力してください):
                1. 表紙 (事業タイトル案を提案してください)
                2. 顧客の課題
                3. 解決策 (技術概要とストーリーを元に具体的に記述)
                4. 市場規模
                5. 競合のリストアップと分析
                6. 差別化ポイント、競合優位性、持続的選択優位性
                7. ビジネスモデル
                8. なぜ今か
                9. なぜ自分（この会社）か
                10. ３年間の事業計画の骨子 (主要マイルストーン、KPIなど)
                11. ３年間の収支計画の超概算 (主要な収益源とコスト構造のアイデア)

                各項目の内容は、具体的で説得力のあるものにしてください。マークダウン形式で記述してください。
                """

                try:
                    with st.spinner(f"'{story_name}' のピッチ構成をAIが分析中..."):
                        response_pitch_report = model.generate_content(pitch_prompt)
                        all_pitch_reports[story_name] = response_pitch_report.text
                except Exception as e:
                    st.error(f"'{story_name}' のピッチ構成レポート生成中にエラー: {e}")
                    all_pitch_reports[story_name] = "AIによるレポート生成に失敗しました。"

            st.session_state.pitch_hypothesis_reports = all_pitch_reports
            st.success("ピッチ構成仮説レポートの生成が完了しました！")

    # レポート表示部分も st.session_state.pitch_hypothesis_reports を使うように修正
    if 'pitch_hypothesis_reports' in st.session_state:
        st.divider()
        st.subheader("生成されたピッチ構成仮説レポート")
        for story_name, report_content in st.session_state.pitch_hypothesis_reports.items():
                with st.expander(f"**{story_name}** のピッチ構成仮説レポート", expanded=True):
                    st.markdown(report_content)
        # ... (ステップ3へのボタン)

        # --- ステップ3へのナビゲーション ---
        st.divider()
        if st.button("ステップ3：VC評価に進む"):
            st.session_state.step = 3
            # st.session_stateから不要なものを削除しても良いかも
            # del st.session_state.initial_report_and_stories
            # del st.session_state.hypothesis_reports # VC評価で使うなら消さない
            st.rerun()

# --- ステップ3: VC評価 ---
elif st.session_state.step == 3:
    st.header("ステップ3: VC評価")
    st.caption("AI（VCペルソナ）による評価結果を表示します。")
    st.divider()

    # --- 評価対象レポートの取得 ---
    reports_to_evaluate = st.session_state.get('pitch_hypothesis_reports', {})

    if not reports_to_evaluate:
        st.warning("評価対象のレポートが見つかりません。ステップ2でレポートを作成してください。")
        if st.button("ステップ2に戻る"):
            st.session_state.step = 2
            st.rerun()
        st.stop()

    # --- VC評価の生成 (まだ結果がなければ実行) ---
    if 'vc_evaluation_results' not in st.session_state:
        st.info("VC評価を実行中です...")
        vc_evaluations = {}
        evaluation_error = False # エラーフラグ

        # 各レポートに対してVC評価を実行
        for story_name, report_content in reports_to_evaluate.items():
            # --- プロンプト作成 (VCペルソナ設定、評価指示 - 前回と同じ) ---
            vc_prompt = f"""あなたは、革新的な技術シーズの事業化可能性を評価する、経験豊富で厳しい視点を持つベンチャーキャピタリスト（VC）です。ビジネスとしての「儲かるか」「スケールするか」「持続可能か」という観点を最も重視します。

            以下の「ピッチ構成仮説レポート」をVCの視点から厳しく評価し、下記の形式でフィードバックを出力してください。

            # 評価対象レポート: {story_name}
            ---
            {report_content}
            ---

            # 出力形式:
            1.  **事業評価スコア（10点満点）:**
                * ビジネスとしての魅力度を10点満点で評価し、その主な根拠を簡潔に述べてください。
            2.  **課題リスト:**
                * ビジネスとしての魅力を高める上で、特に問題となる点、リスク、深掘りが必要な点を「課題」として具体的にリストアップしてください。各課題について、なぜそれが問題なのかをVC視点で説明してください。
            3.  **Next Actionリスト:**
                * 上記の課題を解決し、事業化の解像度を上げるために、次に行うべき具体的なアクションを優先度が高い順に提案してください。各アクションについて、それが「LLMに手伝ってもらえること」か「研究者自身が行う必要があること（インタビュー、実験など）」かを明記してください。

            フィードバックは具体的かつ建設的であるべきですが、視点は厳しく保ってください。マークダウン形式で記述してください。
            """

            # --- Gemini API呼び出し ---
            try:
                with st.spinner(f"'{story_name}' をAI(VC)が評価中..."):
                    # 注意: model変数が利用可能であること
                    response_vc = model.generate_content(vc_prompt)
                    vc_evaluations[story_name] = response_vc.text # 応答テキストをそのまま保存
            except Exception as e:
                st.error(f"'{story_name}' のVC評価中にエラー: {e}")
                vc_evaluations[story_name] = "AIによるVC評価に失敗しました。"
                evaluation_error = True # エラー発生を記録

        # --- 評価結果をSession Stateに保存 ---
        st.session_state.vc_evaluation_results = vc_evaluations
        if not evaluation_error:
            st.success("VC評価が完了しました！")
        # 結果を表示するために再実行（必須ではないが表示がスムーズになる場合がある）
        st.rerun()

    # --- VC評価結果の表示 ---
    st.subheader("VC評価結果")
    if 'vc_evaluation_results' in st.session_state:
        for story_name, eval_content in st.session_state.vc_evaluation_results.items():
            with st.expander(f"**{story_name}** のVC評価結果", expanded=True):
                # !!! 本来はAI応答テキスト(eval_content)をパースして項目ごとに表示する !!!
                # (今回は簡易的に応答全体を表示)
                st.markdown(eval_content)
    else:
        # API呼び出し中などにここに到達する可能性あり
        st.info("VC評価結果を生成中です...")


    # --- ナビゲーション ---
    st.divider()
    if st.button("ステップ2に戻る (レポート再作成)", key="back_to_step2_from_3"):
        st.session_state.step = 2
        # レポート結果をクリアしてステップ2で再生成できるようにする
        if 'hypothesis_reports' in st.session_state: # pitch_hypothesis_reports の方が正しいかも？要確認
             del st.session_state.hypothesis_reports
        if 'pitch_hypothesis_reports' in st.session_state:
             del st.session_state.pitch_hypothesis_reports # こちらを使うべき
        if 'vc_evaluation_results' in st.session_state:
            del st.session_state.vc_evaluation_results
        st.rerun()

    # (アプリの最終形によっては「完了」ボタンなども考えられる)