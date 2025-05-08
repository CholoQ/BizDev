import streamlit as st
import google.generativeai as genai
import os
import re # 正規表現モジュールをインポート

# --- 改善されたパース関数 ---
def parse_lean_canvas_response(text):
    parsed_blocks = {}
    score = "N/A"
    rationale = "N/A"
    score_text = f"スコア: {score}/100\n根拠: {rationale}" # デフォルト値

    # 1. 品質スコア部分を抽出・分離
    score_section = ""
    draft_section = text # まず全体をドラフト部分とする
    if "## 品質スコア" in text:
        parts = text.split("## 品質スコア", 1)
        draft_section = parts[0].strip() # スコアより前がドラフト
        score_section = parts[1].strip()

        # スコアと根拠を正規表現で抽出 (より柔軟に)
        score_match = re.search(r"\*\*スコア:\s*(\d+)\s*/\s*100", score_section)
        rationale_match = re.search(r"\*\*根拠:\s*(.*)", score_section, re.DOTALL)

        score = score_match.group(1) if score_match else "N/A"
        rationale = rationale_match.group(1).strip() if rationale_match else "N/A"
        score_text = f"スコア: {score}/100\n根拠: {rationale}"

    # 2. Lean Canvasドラフト部分から各ブロックを抽出
    # "### X. Heading Name" 形式の行と、それに続く内容を抽出
    # findall で (見出し行全体, 見出し名本体, 内容ブロック) をタプルとして取得
    block_matches = re.findall(r"(###\s*\d+\.\s*(.*?)\s*)\n(.*?)(?=\n###\s*\d+\.|\Z)", draft_section, re.DOTALL | re.MULTILINE)

    if block_matches:
        for _full_heading, heading_name, content_block in block_matches:
            # heading_name から括弧や前後の空白を除去してキーとする
            clean_key = re.sub(r"\(.*?\)", "", heading_name).strip()
            parsed_blocks[clean_key] = content_block.strip()
    else:
        # もしブロック抽出がうまくいかなかった場合
        parsed_blocks["解析エラー"] = draft_section # 解析できなかった部分全体を入れる

    return score_text, parsed_blocks # スコア文字列とブロック辞書を返す

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
    st.session_state.step = 0 # 現在のステップを管理
if 'tech_summary' not in st.session_state:
    st.session_state.tech_summary = ""
if 'initial_report_and_stories' not in st.session_state:
    st.session_state.initial_report_and_stories = ""
if 'selected_stories' not in st.session_state:
    st.session_state.selected_stories = {} # { 'ストーリー名': '内容' }

# --- Streamlit UI部分 ---
st.title("技術事業化支援サービス プロトタイプ")

# --- ステップ0: 技術概要の入力 ---
if st.session_state.step == 0:
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
        submitted = st.form_submit_button("ターゲット戦略のアイデアを見る") # ボタン名を変更

        if submitted:
            if tech_name and problem_to_solve and tech_features and application_areas:
                # 技術概要を保存
                st.session_state.tech_summary = f"""
                技術の名称: {tech_name}
                解決したい課題: {problem_to_solve}
                技術的な特徴・新規性: {tech_features}
                応用できそうな分野・用途: {application_areas}
                補足情報: {free_text if free_text else 'なし'}
                """

                # --- ★★★ 新しい処理: ターゲット戦略提案依頼 ★★★ ---
                st.info("AIがターゲット戦略のアイデアを考えています...")

                # プロンプト作成 (ターゲット戦略提案用)
                target_prompt = f"""以下の技術概要に基づいて、事業化が考えられる具体的なターゲット市場セグメント、またはターゲット顧客像のアイデアを3つ提案してください。
                それぞれのアイデアについて、なぜそれがターゲットとなり得るのか簡単な根拠も添えてください。

                # 技術概要:
                {st.session_state.tech_summary}

                # 出力形式例 (マークダウン):
                **ターゲット案1: [セグメント名や顧客像]**
                * 根拠: [簡単な理由]

                **ターゲット案2: [セグメント名や顧客像]**
                * 根拠: [簡単な理由]

                **ターゲット案3: [セグメント名や顧客像]**
                * 根拠: [簡単な理由]
                """

                try:
                        with st.spinner('Geminiがターゲット戦略を分析中...'):
                            response_target = model.generate_content(target_prompt)
                        st.session_state.target_strategy_ideas = response_target.text
                        st.session_state.step = 1
                        st.write("--- DEBUG: Step changed to 1. Preparing to rerun. ---")
                        st.rerun()

                except Exception as e:
                    st.write(f"--- DEBUG: API call FAILED: {e} ---")
                    st.error(f"ターゲット戦略生成中にエラーが発生しました: {e}")
# --- ★★★ ターゲット戦略提案依頼ここまで ★★★ ---

            else:
                st.warning("技術の基本情報（名称、課題、特徴、応用分野）は入力必須です。")

# --- ステップ1: 壁打ち - ターゲット戦略 ---
elif st.session_state.step == 1:
   
    st.header("ステップ1: 壁打ち - ターゲット戦略")
    st.caption("AIが提案したターゲット戦略のアイデアを確認してください。")
    st.divider()

    st.subheader("AIによるターゲット戦略提案")
    if 'target_strategy_ideas' in st.session_state and st.session_state.target_strategy_ideas:
        st.markdown(st.session_state.target_strategy_ideas) # ← ここで結果が表示されるはず
    else:
        st.warning("ターゲット戦略のアイデアがまだ生成されていません。ステップ0に戻ってください。")
    
    st.divider()
    st.subheader("ターゲットの選択")
    st.caption("提案された中から、最も有望だと思うターゲットを1つ選択してください。")

    # --- ↓↓↓ ターゲット選択UIを追加 ↓↓↓ ---
    # target_strategy_ideas が文字列の場合、パースしてリストにする必要がある
    # (簡易的なパース例： "**ターゲット案X:**" で始まる行を抽出)
    target_options = []
    if 'target_strategy_ideas' in st.session_state and st.session_state.target_strategy_ideas:
        # splitlines() で行に分割し、太字で始まる行をオプションとして抽出
        target_options = [line.strip() for line in st.session_state.target_strategy_ideas.splitlines() if line.strip().startswith("**ターゲット案")]
        # オプションがない場合の処理
        if not target_options:
             st.warning("ターゲット案の選択肢を抽出できませんでした。AIの応答形式を確認してください。")

   # ラジオボタンで選択肢を表示
    if target_options:
        selected_target_option = st.radio(
            "ターゲットを選択:",
            options=target_options,
            key="target_selection_radio",
            # label_visibility="collapsed" # ラベルを隠す場合
        )

        # 選択されたターゲットを表示（確認用）
        st.write(f"選択中: {selected_target_option}")

        # 課題整理へ進むボタン
        if st.button("選択したターゲットの課題整理へ進む", key="goto_problem_definition"):
            if selected_target_option:
                # 選択されたターゲット情報をsession_stateに保存
                st.session_state.selected_target = selected_target_option
                # ここで「課題整理」のためのAI呼び出し等を行うが、まずは画面遷移だけ実装
                st.session_state.step = 1.2 # 次のサブステップへ (仮番号)
                st.rerun()
            else:
                st.warning("ターゲットを選択してください。")
    # --- ↑↑↑ ターゲット選択UIを追加 ↑↑↑ ---


    st.divider()
    # st.info("次のステップ（VPC作成など）は未実装です。") # メッセージ更新

    # ナビゲーション（仮）
    if st.button("ステップ0（入力）に戻る"):
        st.session_state.step = 0
        # 必要に応じてsession_stateをクリア
        if 'target_strategy_ideas' in st.session_state:
            del st.session_state.target_strategy_ideas
        if 'selected_target' in st.session_state:
             del st.session_state.selected_target
        st.rerun()

# --- ステップ1.2: 壁打ち - 課題整理 ---
elif st.session_state.step == 1.2:
    st.header("ステップ1: 壁打ち - 課題整理")
    st.caption("選択したターゲットが抱えている可能性のある課題をAIがリストアップしました。")
    st.divider()

    # 選択されたターゲットを表示
    selected_target = st.session_state.get('selected_target', '（ターゲットが選択されていません）')
    st.subheader("選択されたターゲット")
    st.write(selected_target)
    st.divider()

    # --- AIによる課題リスト生成 (まだ生成されていなければ) ---
    if 'potential_problems' not in st.session_state:
        st.info("AIが課題を分析中です...")
        tech_summary = st.session_state.get('tech_summary', '')
        if not tech_summary:
             st.error("技術概要がありません。ステップ0からやり直してください。")
             st.stop()
        if not selected_target or selected_target == '（ターゲットが選択されていません）':
             st.error("ターゲットが選択されていません。ステップ1に戻ってください。")
             st.stop()

        # プロンプト作成 (課題リストアップ用)
        problem_prompt = f"""以下の「技術概要」と、その技術の「ターゲット候補」について分析してください。
        このターゲット候補が抱えている可能性のある「課題」や「ペイン（悩み、不満、困りごと）」を、できるだけ具体的に5～10個程度リストアップしてください。

        # 技術概要:
        {tech_summary}

        # ターゲット候補:
        {selected_target}

        # 出力形式 (マークダウンの箇条書き):
        * [具体的な課題やペイン1]
        * [具体的な課題やペイン2]
        * ...
        """

        try:
            with st.spinner("Geminiが課題を分析中..."):
                 # 注意: model変数が利用可能であること
                 response_problems = model.generate_content(problem_prompt)
                 st.session_state.potential_problems = response_problems.text
                 st.success("課題リストの生成が完了しました。")
                 # 結果を表示するためにリラン（必須ではないが表示がスムーズになる）
                 st.rerun()
        except Exception as e:
            st.error(f"課題リスト生成中にエラーが発生しました: {e}")
            st.session_state.potential_problems = "課題リストの生成に失敗しました。"


    # --- 生成された課題リストの表示 ---
    st.subheader("AIが考えたターゲットの課題リスト")
    if 'potential_problems' in st.session_state:
        st.markdown(st.session_state.potential_problems)
    else:
        # 通常は上記のAI生成ブロックが実行されるはず
        st.info("課題リストを生成しています...")

    st.divider()

    # --- ナビゲーション ---
    if st.button("ステップ1（ターゲット選択）に戻る", key="back_to_step1"):
        st.session_state.step = 1
        # 関連するsession_stateをクリア
        if 'potential_problems' in st.session_state:
            del st.session_state.potential_problems
        # selected_target はステップ1で再選択するのでクリア不要かも
        st.rerun()

    if st.button("次のステップ（VPC作成）へ進む", key="goto_vpc"): # 将来的に追加
        #ユーザーが選択・評価した課題情報を保存する処理など
        st.session_state.step = 1.3 # 仮のステップ番号
        st.rerun()

# --- ステップ1.3: 壁打ち - Value Proposition Canvas作成支援 ---
elif st.session_state.step == 1.3:
    st.header("ステップ1: 壁打ち - Value Proposition Canvas")
    st.caption("AIが提案するドラフトを元に、顧客への提供価値を具体化しましょう。")
    st.divider()

    # 必要な情報をsession_stateから取得
    selected_target = st.session_state.get('selected_target', '')
    potential_problems = st.session_state.get('potential_problems', '')
    tech_summary = st.session_state.get('tech_summary', '')

    # --- AIによるVPCドラフト生成 (まだ生成されていなければ) ---
    if 'vpc_draft_text' not in st.session_state:
        st.info("AIがVPCドラフトを作成中です...")
        if not selected_target or not potential_problems or not tech_summary:
             st.error("VPC作成に必要な情報（ターゲット、課題、技術概要）が不足しています。前のステップに戻ってください。")
             st.stop()

        # プロンプト作成 (VPC用)
        vpc_prompt = f"""以下の「技術概要」「ターゲット候補」「ターゲットの課題リスト」に基づいて、「Value Proposition Canvas」の6つの構成要素について、具体的なアイデアを提案・記述してください。

        # 技術概要:
        {tech_summary}

        # ターゲット候補:
        {selected_target}

        # ターゲットの課題リスト:
        {potential_problems}

        # 作成するVPCの構成要素と記述内容の指示:
        1.  **顧客のジョブ (Customer Jobs):** ターゲット顧客が達成しようとしていること、解決したい仕事は何か？
        2.  **顧客のペイン (Customer Pains):** 顧客が現状感じている不満、障害、リスクは何か？（上記の課題リストを参考に具体的に）
        3.  **顧客のゲイン (Customer Gains):** 顧客が期待する成果、メリット、喜びは何か？
        4.  **製品・サービス (Products & Services):** あなたの技術を元にした具体的な製品やサービス案は？
        5.  **ペインリリーバー (Pain Relievers):** その製品・サービスが、どのように顧客のペインを取り除くか？
        6.  **ゲインクリエイター (Gain Creators):** その製品・サービスが、どのように顧客のゲインを生み出すか？

        # 出力形式 (各要素を見出しで区切ってください):
        ## 顧客のジョブ (Customer Jobs)
        * [アイデア1]
        * [アイデア2]
        ...

        ## 顧客のペイン (Customer Pains)
        * [アイデア1]
        * [アイデア2]
        ...

        ## 顧客のゲイン (Customer Gains)
        * [アイデア1]
        * [アイデア2]
        ...

        ## 製品・サービス (Products & Services)
        * [アイデア1]
        * [アイデア2]
        ...

        ## ペインリリーバー (Pain Relievers)
        * [アイデア1]
        * [アイデア2]
        ...

        ## ゲインクリエイター (Gain Creators)
        * [アイデア1]
        * [アイデア2]
        ...

        マークダウン形式で記述してください。
        """

        try:
            with st.spinner("GeminiがVPCドラフトを作成中..."):
                response_vpc = model.generate_content(vpc_prompt)
                st.session_state.vpc_draft_text = response_vpc.text # 応答テキスト全体を保存
                st.success("VPCドラフトの生成が完了しました。")
                st.rerun() # 再実行して表示処理へ
        except Exception as e:
            st.error(f"VPCドラフト生成中にエラーが発生しました: {e}")
            st.session_state.vpc_draft_text = "VPCドラフトの生成に失敗しました。"
        
        st.divider()
        st.write("--- DEBUG: Checking session state before VPC display ---")
        st.write(f"--- DEBUG: 'vpc_draft_text' exists: {'vpc_draft_text' in st.session_state} ---")
        if 'vpc_draft_text' in st.session_state:
            st.write("--- DEBUG: Content of vpc_draft_text (first 500 chars): ---")
            # st.markdownだとエラーになる可能性があるのでst.textを使う
            st.text(st.session_state.vpc_draft_text[:500])
        st.divider()

    # --- VPCフレームワークと編集UIの表示 ---
    st.subheader("Value Proposition Canvas （編集可）")

    # --- ★★★ ここからVPC表示と編集UIの実装 ★★★ ---
    # (今回はまずAIの応答全体を表示する)
    if 'vpc_draft_text' in st.session_state:
        st.markdown("--- AIによるドラフト提案 ---")
        st.markdown(st.session_state.vpc_draft_text)
    else:
         st.info("VPCドラフトを生成しています...")

    # (将来的な実装イメージ：st.columns(2)とst.text_areaを6つ配置)
    # col1, col2 = st.columns(2)
    # with col1: # 価値提案側
    #     st.subheader("価値提案")
    #     products_services = st.text_area("製品・サービス", key="vpc_ps", height=150)
    #     pain_relievers = st.text_area("ペインリリーバー", key="vpc_pr", height=150)
    #     gain_creators = st.text_area("ゲインクリエイター", key="vpc_gc", height=150)
    # with col2: # 顧客セグメント側
    #     st.subheader("顧客セグメント")
    #     customer_jobs = st.text_area("顧客のジョブ", key="vpc_cj", height=150)
    #     pains = st.text_area("ペイン", key="vpc_p", height=150)
    #     gains = st.text_area("ゲイン", key="vpc_g", height=150)
    # --- ★★★ VPC表示と編集UIここまで ★★★ ---

    st.divider()

    # --- ナビゲーション ---
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("ステップ1.2（課題整理）に戻る", key="back_to_step1_2"):
            st.session_state.step = 1.2
            if 'vpc_draft_text' in st.session_state:
                del st.session_state.vpc_draft_text
            # vpc_final があればそれも消す
            if 'vpc_final_data' in st.session_state:
                del st.session_state.vpc_final_data
            st.rerun()
    with col_nav2:
        if st.button("ステップ2a（Lean Canvas）へ進む", key="goto_step2a"):
            # --- ↓↓↓ VPC内容の保存処理を追加 ↓↓↓ ---
            st.session_state.vpc_final_data = {
                "顧客のジョブ": st.session_state.get("vpc_cj", ""), # keyはVPCのtext_areaで指定したものに合わせる
                "ペイン": st.session_state.get("vpc_p", ""),
                "ゲイン": st.session_state.get("vpc_g", ""),
                "製品・サービス": st.session_state.get("vpc_ps", ""),
                "ペインリリーバー": st.session_state.get("vpc_pr", ""),
                "ゲインクリエイター": st.session_state.get("vpc_gc", "")
            }
            
            st.session_state.step = 2.1 # Lean Canvasを 2.1 とする
            st.rerun() # 次のステップへ

    
# --- ステップ2a (2.1): Lean Canvas Draft + Score ---
elif st.session_state.step == 2.1:
    st.header("ステップ2a: Lean Canvas ドラフト作成")
    st.caption("これまでの情報を元にAIがLean Canvasのドラフトを作成し、品質スコアを算出します。")
    st.divider()

    # --- AIによるLean Canvas Draft + Score生成 (まだなければ) ---
    if 'lean_canvas_raw_output' not in st.session_state:
        st.info("AIがLean Canvasドラフトと品質スコアを作成中です...")

        # 必要な情報をsession_stateから取得
        tech_summary = st.session_state.get('tech_summary', '')
        selected_target = st.session_state.get('selected_target', '')
        potential_problems = st.session_state.get('potential_problems', '') # 課題リストも追加
        vpc_data = st.session_state.get('vpc_final_data', {}) # Step 1.3で保存したVPCデータ

        if not tech_summary or not selected_target: # VPCと課題は任意入力から生成される可能性考慮
             st.error("Lean Canvas作成に必要な情報（技術概要、ターゲット）が不足しています。前のステップに戻ってください。")
             st.stop()

        # プロンプト作成 (入力をより明確に記述)
        input_context = f"""
        # 提供情報

        ## 技術概要:
        {tech_summary}

        ## 選抜されたターゲット顧客:
        {selected_target}

        ## ターゲットの主な課題・ペイン (AI提案/ユーザー編集):
        {potential_problems if potential_problems else "(情報なし)"}

        ## Value Proposition Canvas の内容:
        * 顧客のジョブ: {vpc_data.get('顧客のジョブ', '(情報なし)')}
        * ペイン: {vpc_data.get('ペイン', '(情報なし)')}
        * ゲイン: {vpc_data.get('ゲイン', '(情報なし)')}
        * 製品・サービス: {vpc_data.get('製品・サービス', '(情報なし)')}
        * ペインリリーバー: {vpc_data.get('ペインリリーバー', '(情報なし)')}
        * ゲインクリエイター: {vpc_data.get('ゲインクリエイター', '(情報なし)')}
        """

        lc_prompt = f"""{input_context}
        ---
        # 指示
        上記の提供情報に基づいて、Lean Canvasの9つの構成要素のドラフトを作成してください。
        さらに、作成したドラフト全体について、事業アイデアの初期段階としての「品質スコア」を100点満点で採点し、その主な理由も記述してください。

        # 作成するLean Canvasの構成要素:
        1. 課題 (Problem): 上記のペインや技術概要から最も重要と考えられる課題を3つ程度
        2. 顧客セグメント (Customer Segments): 上記ターゲット顧客をより具体的に
        3. 独自の価値提案 (Unique Value Proposition): 提供価値を一言で。競合との違いを意識。
        4. 解決策 (Solution): 製品・サービス、ペインリリーバー、ゲインクリエイターを元に具体的な解決策を記述。
        5. チャネル (Channels): 顧客セグメントに到達するための経路案。
        6. 収益の流れ (Revenue Streams): VPCや解決策から考えられる収益化のアイデア。
        7. コスト構造 (Cost Structure): 解決策提供に必要な主要コスト要素の推定。
        8. 主要指標 (Key Metrics): このビジネスの成功を測る初期指標案。
        9. 圧倒的優位性 (Unfair Advantage): 技術概要やVPCから考えられる模倣困難な強み。

        # 品質スコアの評価観点:
        * 各項目の一貫性
        * 価値提案の魅力度
        * 課題と解決策のマッチ度
        * 市場性のポテンシャル 等

        # 出力形式 (マークダウン):
        ## Lean Canvas Draft
        ### 1. 課題
        [記述]
        ### 2. 顧客セグメント
        [記述]
        ... (9まですべて) ...

        ## 品質スコア
        **スコア:** [点数]/100
        **根拠:** [簡単な理由]
        """

        try:
            with st.spinner("GeminiがLean Canvasを作成・評価中..."):
                response_lc = model.generate_content(lc_prompt)
                raw_output = response_lc.text
                st.session_state.lean_canvas_raw_output = raw_output # 生データ保存

                # ★★★ 改善されたパース関数を呼び出す ★★★
                parsed_score, parsed_blocks = parse_lean_canvas_response(raw_output)
                st.session_state.lean_canvas_score_text = parsed_score
                st.session_state.lean_canvas_parsed_blocks = parsed_blocks # パース結果を保存
                st.success("Lean Canvasドラフトと品質スコアの作成・解析が完了しました。")
                # st.rerun() # ここでは不要

        except Exception as e:
            st.error(f"Lean Canvas作成中にエラーが発生しました: {e}")
            st.session_state.lean_canvas_raw_output = "Lean Canvasの作成に失敗しました。"
            st.session_state.lean_canvas_score_text = "エラー"
            st.session_state.lean_canvas_parsed_blocks = {} # 空の辞書

    # --- Lean Canvas表示と編集UI ---
    st.subheader("Lean Canvas ドラフト （編集可）")

    # 品質スコア表示
    if 'lean_canvas_score_text' in st.session_state:
         st.markdown("**品質スコア**")
         # st.text だと改行が反映されない可能性があるので st.write や st.markdown を使う
         st.markdown(st.session_state.lean_canvas_score_text.replace('\n', '  \n')) # Markdown改行
         st.divider()

    # Lean Canvas 9ブロック表示 (編集可能)
    if 'lean_canvas_parsed_blocks' in st.session_state and st.session_state.lean_canvas_parsed_blocks:
         lc_data = st.session_state.lean_canvas_parsed_blocks
         # 9ブロックのキー名（パース後のキー名に合わせる）
         keys_ordered = [
             "課題", "顧客セグメント", "独自の価値提案", "解決策",
             "チャネル", "収益の流れ", "コスト構造", "主要指標", "圧倒的優位性"
         ]
         # 実際にパースされたキーのみを処理対象とする
         valid_keys = [k for k in keys_ordered if k in lc_data]

         # 9つのテキストエリアで表示・編集
         # (レイアウトは後で調整するとして、まずは順番に表示)
         for i, key in enumerate(valid_keys):
             block_content = lc_data.get(key, "") # パース結果を取得
             session_key = f"lc_{key.replace(' ', '_')}" # session_state用キー (スペースをアンダースコアに)
             # テキストエリアを作成 (valueにパース結果、keyを指定)
             edited_value = st.text_area(f"{i+1}. {key}", value=block_content, height=150, key=session_key)
             # 編集された値を即座に反映させる場合は不要だが、明示的に更新も可
             # st.session_state[session_key] = edited_value

         if len(valid_keys) < 9:
             st.warning("AI応答の解析が不完全か、一部項目が生成されませんでした。")
         if "解析エラー" in lc_data:
             st.warning("解析できなかったテキスト:")
             st.text(lc_data["解析エラー"])
         elif "不明 (Full Draft)" in lc_data: # 旧Fallbackキーも一応残す
             st.warning("解析できなかったドラフト部分:")
             st.text(lc_data["不明 (Full Draft)"])

    else:
        st.info("Lean Canvas ドラフトを表示するデータがありません。")

    st.divider()
    
    # --- ナビゲーション ---
    col_nav1, col_nav2, col_nav3 = st.columns(3)
    with col_nav1:
        if st.button("ステップ1.3（VPC）に戻る", key="back_to_step1_3"):
            st.session_state.step = 1.3
            # 関連するsession_stateをクリア
            if 'lean_canvas_raw_output' in st.session_state: del st.session_state.lean_canvas_raw_output
            if 'lean_canvas_score_text' in st.session_state: del st.session_state.lean_canvas_score_text
            if 'lean_canvas_parsed_blocks' in st.session_state: del st.session_state.lean_canvas_parsed_blocks
            # VPCデータは残しておく
            st.rerun()
    with col_nav2:
        if st.button("ステップ2b（顧客インタビュー）へ進む", key="goto_step2b"):
            # ★★★ ここで編集されたLean Canvasの内容をsession_stateに保存する処理が必要 ★★★
            # (st.text_areaのkeyで既に保存されているので、それを次のステップで読み込む)
            st.session_state.step = 2.2 # 顧客インタビューを 2.2 とする (仮)
            st.info("ステップ2b（顧客インタビュー）は未実装です。")
            # st.rerun()
    with col_nav3:
        if st.button("ステップ3（深掘り）へ進む", key="goto_step3"):
            # Lean Canvasの内容は st.session_state.lc_課題 などに保存されているはず
            st.session_state.step = 3 # ★ ステップ番号を 3 に設定 ★
            st.rerun() # ★ 再実行してステップ3へ遷移 ★
   
# --- ステップ3: 深掘り ---
elif st.session_state.step == 3:
    st.header("ステップ3: 深掘り分析")
    st.caption("Lean Canvasの内容などを元に、MVP、SWOTなどの分析を行います。")
    st.divider()

    # --- 必要な情報をsession_stateから取得 ---
    tech_summary = st.session_state.get('tech_summary', '')
    selected_target = st.session_state.get('selected_target', '')
    # ... (VPCデータや、編集されたLean Canvasの各ブロックの値も必要に応じて取得) ...
    # 例: lean_canvas_data = { key.replace('lc_', ''): st.session_state[key] for key in st.session_state if key.startswith('lc_') }
    lean_canvas_problem = st.session_state.get('lc_課題', '') # key名を正確に指定
    lean_canvas_solution = st.session_state.get('lc_解決策', '')
    lean_canvas_uvp = st.session_state.get('lc_独自の価値提案', '')
    # (他のLean Canvas項目も同様に取得)

    # --- MVP検討セクション ---
    with st.expander("MVP (Minimum Viable Product) の検討", expanded=True):
        st.markdown("最小限の機能で顧客に価値を提供できる製品・サービス案を検討します。")

        # AIにMVP案を提案させるボタン
        if st.button("MVP案をAIに提案させる", key="generate_mvp"):
            st.info("AIがMVP案を検討中です...")
            # --- AI呼び出しロジック (MVP用) ---
            mvp_context = f"""以下の情報を元に、実現可能で価値検証に適したMVP（Minimum Viable Product）のアイデアを2～3個提案してください。それぞれのMVPについて、主要な機能、ターゲットユーザー、検証したい仮説を簡潔に記述してください。

            # 技術概要:
            {tech_summary}

            # ターゲット顧客:
            {selected_target}

            # Lean Canvas - 課題:
            {lean_canvas_problem}

            # Lean Canvas - 解決策:
            {lean_canvas_solution}

            # Lean Canvas - 独自の価値提案:
            {lean_canvas_uvp}

            # 出力形式 (マークダウン):
            **MVP案1:**
            * 主要機能: ...
            * ターゲットユーザー（初期）: ...
            * 検証したい仮説: ...

            **MVP案2:**
            ... (同様に)
            """
            try:
                with st.spinner("GeminiがMVP案を分析中..."):
                    response_mvp = model.generate_content(mvp_context)
                    st.session_state.mvp_ideas_text = response_mvp.text # 結果を保存
            except Exception as e:
                st.error(f"MVP案生成中にエラー: {e}")
                st.session_state.mvp_ideas_text = "MVP案の生成に失敗"

        # AIが生成したMVP案の表示 (session_stateに保存後)
        if 'mvp_ideas_text' in st.session_state:
            st.subheader("AIによるMVP提案")
            st.markdown(st.session_state.mvp_ideas_text)
            st.divider()

        # ユーザーがMVP定義を記述する欄
        st.subheader("検討するMVPの定義")
        st.text_area("ここに検討するMVPの概要、主要機能、検証方法などを記述してください。", height=200, key="mvp_definition_user")

    # --- SWOT分析セクション ---
    with st.expander("SWOT分析", expanded=False):
        st.markdown("事業を取り巻く内部環境（強み・弱み）と外部環境（機会・脅威）を分析します。")

        # AIにSWOT分析を実行させるボタン
        if st.button("SWOT分析をAIに実行させる", key="generate_swot"):
            st.info("AIがSWOT分析を実行中です...")
            # --- AI呼び出しロジック (SWOT用) ---
            swot_context = f"""以下の情報を元に、この事業アイデアに関するSWOT分析（強み、弱み、機会、脅威）を行ってください。内部環境と外部環境の両面から、具体的な要素をリストアップしてください。

            # 技術概要:
            {tech_summary}

            # ターゲット顧客:
            {selected_target}

            # Lean Canvas (主要項目):
            * 課題: {lean_canvas_problem}
            * 解決策: {lean_canvas_solution}
            * 独自の価値提案: {lean_canvas_uvp}
            # (必要なら他のLean Canvas項目も追加)

            # 出力形式 (マークダウン):
            ## SWOT分析結果
            * **強み (Strengths):**
                * [要素1]
                * [要素2]
            * **弱み (Weaknesses):**
                * [要素1]
                * [要素2]
            * **機会 (Opportunities):**
                * [要素1]
                * [要素2]
            * **脅威 (Threats):**
                * [要素1]
                * [要素2]
            """
            try:
                with st.spinner("GeminiがSWOT分析を実行中..."):
                     response_swot = model.generate_content(swot_context)
                     st.session_state.swot_analysis_text = response_swot.text # 結果を保存
            except Exception as e:
                st.error(f"SWOT分析中にエラー: {e}")
                st.session_state.swot_analysis_text = "SWOT分析の生成に失敗"

        # AIが生成したSWOT分析結果の表示
        if 'swot_analysis_text' in st.session_state:
            st.subheader("AIによるSWOT分析結果")
            st.markdown(st.session_state.swot_analysis_text)
            st.divider()

        # ユーザーコメント欄
        st.subheader("SWOT分析に関するコメント・考察")
        st.text_area("AIの分析結果に対する考察や、追加の要素などを記述してください。", height=150, key="swot_comments_user")


    # --- 4P分析セクション ---
    with st.expander("4P分析", expanded=False):
        st.markdown("製品（Product）、価格（Price）、流通（Place）、販促（Promotion）の観点から戦略を検討します。")

        # AIに4P分析を実行させるボタン
        if st.button("4P分析をAIに実行させる", key="generate_4p"):
            st.info("AIが4P分析を実行中です...")
            # --- AI呼び出しロジック (4P用) ---
            # 必要なコンテキストを取得 (Lean Canvasの内容全体を使う例)
            lc_parsed_blocks = st.session_state.get('lean_canvas_parsed_blocks', {})
            lc_context = "\n".join([f"### {k}\n{v}" for k, v in lc_parsed_blocks.items()])
            mvp_definition = st.session_state.get('mvp_definition_user', '(未定義)') # MVP定義も参照

            four_p_prompt = f"""以下の情報に基づいて、この事業アイデアの4P分析を行い、具体的な戦略案を提案してください。

            # 技術概要:
            {tech_summary}

            # ターゲット顧客:
            {selected_target}

            # MVP定義 (ユーザー記述):
            {mvp_definition}

            # Lean Canvas Draft:
            {lc_context}

            # 分析する4P項目と指示:
            * **Product（製品・サービス）:** MVP案を踏まえ、どのような製品/サービス形態、品質、デザイン、ブランド名などが考えられるか？
            * **Price（価格）:** どのような価格設定（例：買い切り、サブスク）、価格帯、割引戦略などが考えられるか？ 顧客の価値認識やコスト構造も考慮。
            * **Place（流通・チャネル）:** Lean Canvasのチャネル案を元に、どのように顧客に製品/サービスを届けるか？（例：直販、代理店、オンライン）
            * **Promotion（販促・プロモーション）:** どのようにターゲット顧客に製品/サービスを知ってもらい、購入を促すか？（例：広告、広報、Webマーケティング、展示会）

            # 出力形式 (マークダウン):
            ## 4P分析結果
            ### Product（製品・サービス）
            * [提案1]
            * [提案2]
            ### Price（価格）
            * [提案1]
            * [提案2]
            ### Place（流通・チャネル）
            * [提案1]
            * [提案2]
            ### Promotion（販促・プロモーション）
            * [提案1]
            * [提案2]
            """
            try:
                with st.spinner("Geminiが4P分析を実行中..."):
                     response_4p = model.generate_content(four_p_prompt)
                     st.session_state.four_p_analysis_text = response_4p.text # 結果を保存
            except Exception as e:
                st.error(f"4P分析中にエラー: {e}")
                st.session_state.four_p_analysis_text = "4P分析の生成に失敗"

        # AIが生成した4P分析結果の表示
        if 'four_p_analysis_text' in st.session_state:
            st.subheader("AIによる4P分析結果")
            st.markdown(st.session_state.four_p_analysis_text)
            st.divider()

        # ユーザーコメント欄
        st.subheader("4P分析に関するコメント・考察")
        st.text_area("AIの分析結果に対する考察や、具体的な戦略案などを記述してください。", height=150, key="4p_comments_user")

    # --- 3C分析セクション ---
    with st.expander("3C分析", expanded=False):
        st.markdown("顧客（Customer）、競合（Competitor）、自社（Company）の3つの観点から事業環境を分析します。")

        # AIに3C分析を実行させるボタン
        if st.button("3C分析をAIに実行させる", key="generate_3c"):
            st.info("AIが3C分析を実行中です...")
            # --- AI呼び出しロジック (3C用) ---
            # 必要なコンテキストを収集 (より多くの情報を活用)
            tech_summary = st.session_state.get('tech_summary', '')
            selected_target = st.session_state.get('selected_target', '')
            potential_problems = st.session_state.get('potential_problems', '')
            vpc_data = st.session_state.get('vpc_final_data', {})
            lc_parsed_blocks = st.session_state.get('lean_canvas_parsed_blocks', {})
            swot_analysis = st.session_state.get('swot_analysis_text', '') # SWOT結果も活用

            # Lean Canvasから関連情報を抽出
            lc_customer = lc_parsed_blocks.get('顧客セグメント', '')
            lc_problem = lc_parsed_blocks.get('課題', '')
            lc_competitor_advantage = lc_parsed_blocks.get('圧倒的優位性', '') # 競合情報含む可能性あり
            lc_solution = lc_parsed_blocks.get('解決策', '')

            three_c_prompt = f"""以下の提供情報に基づいて、3C分析（顧客、競合、自社）を行ってください。各要素について、重要なポイントを整理し、簡潔に記述してください。

            # 提供情報
            ## 技術概要:
            {tech_summary}

            ## ターゲット顧客（初期案）:
            {selected_target}

            ## 顧客の課題リスト（AI提案）:
            {potential_problems}

            ## Value Proposition Canvas:
            {vpc_data}

            ## Lean Canvas Draft (抜粋):
            * 顧客セグメント: {lc_customer}
            * 課題: {lc_problem}
            * 解決策: {lc_solution}
            * 圧倒的優位性: {lc_competitor_advantage}

            ## SWOT分析結果:
            {swot_analysis}

            # 分析すべき3C項目と指示:
            * **Customer（顧客）:** ターゲット顧客は誰か？市場規模やニーズは？（既存情報を統合・整理）
            * **Competitor（競合）:** 主要な競合は誰か？競合の強み・弱みは？（既存情報に加え、推測や一般的な知見も加味）
            * **Company（自社）:** 自社の強み・弱みは？（技術、リソース、SWOTなどを考慮） どうすれば競合に勝てるか？

            # 出力形式 (マークダウン):
            ## 3C分析結果
            ### Customer（顧客）
            * [分析結果1]
            * [分析結果2]
            ### Competitor（競合）
            * [分析結果1]
            * [分析結果2]
            ### Company（自社）
            * [分析結果1]
            * [分析結果2]
            """
            try:
                with st.spinner("Geminiが3C分析を実行中..."):
                     response_3c = model.generate_content(three_c_prompt)
                     st.session_state.three_c_analysis_text = response_3c.text # 結果を保存
            except Exception as e:
                st.error(f"3C分析中にエラー: {e}")
                st.session_state.three_c_analysis_text = "3C分析の生成に失敗"

        # AIが生成した3C分析結果の表示
        if 'three_c_analysis_text' in st.session_state:
            st.subheader("AIによる3C分析結果")
            st.markdown(st.session_state.three_c_analysis_text)
            st.divider()

        # ユーザーコメント欄
        st.subheader("3C分析に関するコメント・考察")
        st.text_area("AIの分析結果に対する考察や、追加の情報を記述してください。", height=150, key="3c_comments_user")

    # --- 財務計画（初期）セクション ---
    with st.expander("財務計画（初期）", expanded=False):
        st.markdown("事業の主要な収益源、コスト構造、および初期段階で考慮すべき財務的なポイントを検討します。")

        # AIに財務計画の初期アイデアを提案させるボタン
        if st.button("財務計画（初期）のアイデアをAIに提案させる", key="generate_financials"):
            st.info("AIが財務計画の初期アイデアを検討中です...")
            # --- AI呼び出しロジック (財務初期用) ---
            # 必要なコンテキストを収集 (Lean Canvas, 4Pなど)
            tech_summary = st.session_state.get('tech_summary', '')
            lc_parsed_blocks = st.session_state.get('lean_canvas_parsed_blocks', {})
            four_p_analysis = st.session_state.get('four_p_analysis_text', '') # 4P分析結果も参照

            # Lean Canvasから関連情報を抽出
            lc_revenue = lc_parsed_blocks.get('収益の流れ', '')
            lc_cost = lc_parsed_blocks.get('コスト構造', '')
            lc_solution = lc_parsed_blocks.get('解決策', '')

            financial_prompt = f"""以下の提供情報に基づいて、この事業アイデアの初期段階における財務計画の「骨子」を提案してください。これは詳細な予測ではなく、主要な要素と考え方を整理するものです。

            # 提供情報
            ## 技術概要:
            {tech_summary}

            ## Lean Canvas Draft (抜粋):
            * 解決策: {lc_solution}
            * 収益の流れ: {lc_revenue}
            * コスト構造: {lc_cost}

            ## 4P分析結果 (抜粋):
            {four_p_analysis} # 価格戦略などが参考になる可能性

            # 提案してほしい項目と指示:
            * **主要な収益源 (Revenue Streams):** Lean Canvasのアイデアを元に、考えられる具体的な収益源をリストアップ。
            * **主要なコスト構造 (Cost Structure):** Lean Canvasのアイデアを元に、主な変動費・固定費の項目をリストアップ。
            * **初期の財務的考慮事項 (Initial Financial Considerations):** 価格設定の考え方、初期投資の主な項目、資金調達の必要性、最初に追うべき財務指標（例：損益分岐点、CAC）など、この段階で意識すべき点をいくつか提案。

            # 出力形式 (マークダウン):
            ## 財務計画（初期アイデア）
            ### 主要な収益源
            * [アイデア1]
            * [アイデア2]
            ### 主要なコスト構造
            * [アイデア1]
            * [アイデア2]
            ### 初期の財務的考慮事項
            * [ポイント1]
            * [ポイント2]
            """
            try:
                with st.spinner("Geminiが財務計画（初期）を分析中..."):
                     response_financials = model.generate_content(financial_prompt)
                     st.session_state.financials_ideas_text = response_financials.text # 結果を保存
            except Exception as e:
                st.error(f"財務計画（初期）の生成中にエラー: {e}")
                st.session_state.financials_ideas_text = "財務計画（初期）の生成に失敗"

        # AIが生成した財務計画（初期）アイデアの表示
        if 'financials_ideas_text' in st.session_state:
            st.subheader("AIによる財務計画（初期）アイデア")
            st.markdown(st.session_state.financials_ideas_text)
            st.divider()

        # ユーザーコメント欄
        st.subheader("財務計画に関するコメント・考察")
        st.text_area("AIの提案に対する考察や、具体的な数値目標の初期アイデアなどを記述してください。", height=150, key="financials_comments_user")

    # --- ナビゲーション ---
    col_nav1_step3, col_nav2_step3 = st.columns(2)
    with col_nav1_step3:
        if st.button("ステップ2a（Lean Canvas）に戻る", key="back_to_step2a"):
            st.session_state.step = 2.1
            # このステップで生成したデータをクリア
            if 'mvp_ideas_text' in st.session_state: del st.session_state.mvp_ideas_text
            if 'swot_analysis_text' in st.session_state: del st.session_state.swot_analysis_text
            # ユーザー入力もクリアするかどうかは要検討
            # if 'mvp_definition_user' in st.session_state: del st.session_state.mvp_definition_user
            # if 'swot_comments_user' in st.session_state: del st.session_state.swot_comments_user
            st.rerun()
    with col_nav2_step3:
        if st.button("ステップ4（競合分析→Moat）へ進む", key="goto_step4"):
            # ★★★ ここで編集されたMVP定義やSWOT考察を保存する処理が必要 ★★★
            # st.session_state.final_mvp = st.session_state.mvp_definition_user
            # st.session_state.final_swot = st.session_state.swot_comments_user
            st.session_state.step = 4 # ステップ4へ
            st.rerun()

# --- ステップ4: 競合分析 → 優位性 (Moat) 整理 ---
elif st.session_state.step == 4:
    st.header("ステップ4: 競合分析と優位性（Moat）の整理")
    st.caption("競合を分析し、自社の持続可能な競争優位性を明確にします。")
    st.divider()

    # --- 必要な情報をsession_stateから取得 ---
    tech_summary = st.session_state.get('tech_summary', '')
    # (Lean Canvas, SWOTなどのデータも取得)
    lc_competitors = st.session_state.get('lc_競合', '') # Lean Canvasの競合ブロックのキー名を確認
    lc_unfair_advantage = st.session_state.get('lc_圧倒的優位性', '')
    swot_analysis = st.session_state.get('swot_analysis_text', '') # SWOT分析の結果テキスト

    # --- 競合分析セクション ---
    with st.expander("競合分析", expanded=True):
        st.markdown("主要な競合について、製品・サービス、強み・弱みなどを分析します。")
        st.markdown("**Lean Canvasで挙げた競合（参考）:**")
        st.text(lc_competitors if lc_competitors else "（Lean Canvasでの記述なし）")
        st.divider()

        # AIに競合分析を依頼するボタン
        if st.button("競合の詳細分析をAIに依頼する", key="generate_competitor_analysis"):
            st.info("AIが競合分析を実行中です...")
            # --- AI呼び出しロジック (競合分析用) ---
            competitor_prompt = f"""以下の技術概要とLean Canvasで挙げられた競合情報を元に、主要な競合企業（または代替技術）を特定し、それぞれの特徴、強み、弱みを分析してください。

            # 技術概要:
            {tech_summary}

            # Lean Canvas記載の競合（参考）:
            {lc_competitors}

            # 分析してほしい観点:
            * 主要な競合企業/技術名
            * 提供している製品/サービス
            * 想定されるターゲット顧客
            * 強み
            * 弱み
            * 価格帯やビジネスモデル（推測で可）

            # 出力形式 (マークダウン):
            ## 競合分析結果
            ### 競合A: [企業名/技術名]
            * 製品/サービス: ...
            * ターゲット: ...
            * 強み: ...
            * 弱み: ...
            * 価格/ビジネスモデル: ...
            ### 競合B: [企業名/技術名]
            ... (同様に)
            """
            try:
                with st.spinner("Geminiが競合を分析中..."):
                    response_competitors = model.generate_content(competitor_prompt)
                    st.session_state.competitor_analysis_text = response_competitors.text # 結果を保存
            except Exception as e:
                st.error(f"競合分析中にエラー: {e}")
                st.session_state.competitor_analysis_text = "競合分析の生成に失敗"

        # AIが生成した競合分析結果の表示
        if 'competitor_analysis_text' in st.session_state:
            st.subheader("AIによる競合分析結果")
            st.markdown(st.session_state.competitor_analysis_text)
            st.divider()

        # ユーザーコメント欄
        st.subheader("競合分析に関する追記・考察")
        st.text_area("AIの分析結果に対する考察や、追加の競合情報などを記述してください。", height=150, key="competitor_notes_user")

    # --- Moat定義セクション ---
    with st.expander("優位性（Moat）の整理", expanded=True):
        st.markdown("競合分析と自社の強みを踏まえ、持続可能な競争優位性（Moat）を定義します。")
        st.markdown("**関連情報（参考）:**")
        st.markdown(f"* Lean Canvas - 圧倒的優位性: {lc_unfair_advantage if lc_unfair_advantage else '（記述なし）'}")
        # SWOTの強み部分を表示したいが、パースが必要なため、今は全体表示で代用
        if 'swot_analysis_text' in st.session_state:
             st.markdown(f"* SWOT分析（強みなど）:\n {st.session_state.swot_analysis_text}")
        st.divider()


        # AIにMoatの言語化を依頼するボタン
        if st.button("Moat（圧倒的優位性）の言語化をAIに依頼する", key="generate_moat"):
            st.info("AIがMoatの言語化を試みています...")
            # --- AI呼び出しロジック (Moat用) ---
            competitor_analysis_results = st.session_state.get('competitor_analysis_text', '') # 上で生成した競合分析結果

            moat_prompt = f"""以下の情報に基づいて、この事業の持続可能な競争優位性（Moat）となりうる要素を特定し、それを表現する簡潔なステートメント案を1～3個提案してください。なぜそれが競合にとって模倣困難なのか、理由も添えてください。

            # 技術概要:
            {tech_summary}

            # Lean Canvas - 圧倒的優位性（ユーザー記述）:
            {lc_unfair_advantage}

            # SWOT分析結果:
            {swot_analysis}

            # 競合分析結果:
            {competitor_analysis_results}

            # 出力形式 (マークダウン):
            ## Moat（持続可能な競争優位性）の提案
            **Moat案1:** [Moatを表すステートメント]
            * 理由: [なぜ模倣困難かの説明]

            **Moat案2:** [Moatを表すステートメント]
            * 理由: [なぜ模倣困難かの説明]
            ... (最大3つまで)
            """
            try:
                with st.spinner("GeminiがMoatを分析中..."):
                     response_moat = model.generate_content(moat_prompt)
                     st.session_state.moat_ideas_text = response_moat.text # 結果を保存
            except Exception as e:
                st.error(f"Moat生成中にエラー: {e}")
                st.session_state.moat_ideas_text = "Moatの生成に失敗"

        # AIが生成したMoat案の表示
        if 'moat_ideas_text' in st.session_state:
            st.subheader("AIによるMoat提案")
            st.markdown(st.session_state.moat_ideas_text)
            st.divider()

        # ユーザーが最終的なMoatを記述する欄
        st.subheader("最終的なMoatの定義")
        st.text_area("AIの提案やこれまでの分析を踏まえ、この事業のMoatを定義してください。", height=150, key="moat_definition_user")

    st.divider()
    
    # --- ナビゲーション ---
    col_nav1_step4, col_nav2_step4 = st.columns(2)
    with col_nav1_step4:
        if st.button("ステップ3（深掘り）に戻る", key="back_to_step3"):
            st.session_state.step = 3
            # このステップで生成したデータをクリア
            if 'competitor_analysis_text' in st.session_state: del st.session_state.competitor_analysis_text
            if 'moat_ideas_text' in st.session_state: del st.session_state.moat_ideas_text
            # ユーザー入力もクリアするかどうかは要検討
            st.rerun()
    
    with col_nav2_step4:
        if st.button("ステップ5（ピッチ資料生成）へ進む", key="goto_step5"):
            # ★★★ ここで最終的なMoat定義などを保存する処理が必要 ★★★
            # st.session_state.final_moat = st.session_state.moat_definition_user
            st.session_state.step = 5 # ステップ5へ
            st.rerun()

# --- ステップ5: ピッチ資料自動生成 ---
elif st.session_state.step == 5:
    st.header("ステップ5: ピッチ資料 自動生成")
    st.caption("これまでの分析結果を統合し、ピッチ資料の骨子をAIが生成します。")
    st.divider()

    # --- 必要な情報をsession_stateから取得 ---
    # (これまでのステップで保存した全ての関連データを取得)
    tech_summary = st.session_state.get('tech_summary', '')
    selected_target = st.session_state.get('selected_target', '')
    potential_problems = st.session_state.get('potential_problems', '')
    vpc_data = st.session_state.get('vpc_final_data', {})
    # Lean Canvas (個別のキーから取得またはパース結果辞書から)
    lc_parsed_blocks = st.session_state.get('lean_canvas_parsed_blocks', {})
    lc_score_text = st.session_state.get('lean_canvas_score_text','')
    # MVP, SWOT, 4P, 3C, Financials, Competitors, Moat
    mvp_definition = st.session_state.get('mvp_definition_user', '')
    swot_analysis = st.session_state.get('swot_analysis_text', '')
    four_p_analysis = st.session_state.get('four_p_analysis_text', '')
    three_c_analysis = st.session_state.get('three_c_analysis_text', '')
    financials_ideas = st.session_state.get('financials_ideas_text', '')
    competitor_analysis = st.session_state.get('competitor_analysis_text', '')
    moat_definition = st.session_state.get('moat_definition_user', '') # ユーザー定義のMoatを使う

    # --- ピッチ資料生成ボタン ---
    if st.button("ピッチ資料の骨子を生成する", key="generate_pitch"):
        st.info("AIがピッチ資料骨子を生成中です...")
        # --- AI呼び出しロジック (ピッチ資料生成用) ---
        # 全ての情報をプロンプトのコンテキストとして組み立てる
        full_context = f"""以下は、ある技術シーズの事業化検討プロセスで整理された情報です。
        これらの情報を統合・要約し、指定された11項目のピッチ資料構成に沿った骨子を作成してください。
        各項目の記述には、可能であればその根拠となった分析要素（例：SWOT分析、市場規模調査など）を括弧書きで示唆してください。

        # 技術概要:
        {tech_summary}

        # ターゲット顧客:
        {selected_target}

        # 顧客の課題リスト:
        {potential_problems}

        # Value Proposition Canvas:
        {vpc_data}

        # Lean Canvas Draft & Score:
        {st.session_state.get('lean_canvas_raw_output', '')}

        # MVP定義:
        {mvp_definition}

        # SWOT分析:
        {swot_analysis}

        # 4P分析:
        {four_p_analysis}

        # 3C分析:
        {three_c_analysis}

        # 財務計画（初期アイデア）:
        {financials_ideas}

        # 競合分析:
        {competitor_analysis}

        # Moat（持続可能な競争優位性）の定義:
        {moat_definition}

        ---
        # 作成するピッチ資料構成（11項目 - この見出しを使用）:
        ## 1. タイトル
        ## 2. 顧客の課題
        ## 3. 解決策
        ## 4. 市場規模
        ## 5. 競合
        ## 6. 差別化ポイント・優位性（Moat含む）
        ## 7. ビジネスモデル
        ## 8. なぜ今か
        ## 9. なぜ自分（この会社）か
        ## 10. 事業計画の骨子（3年）
        ## 11. 収支計画の概算（3年）

        マークダウン形式で記述してください。
        """

        try:
            with st.spinner("Geminiがピッチ資料骨子を生成中..."):
                response_pitch = model.generate_content(full_context)
                st.session_state.pitch_deck_draft_text = response_pitch.text # 結果を保存
                st.success("ピッチ資料骨子の生成が完了しました。")
        except Exception as e:
            st.error(f"ピッチ資料骨子生成中にエラー: {e}")
            st.session_state.pitch_deck_draft_text = "ピッチ資料骨子の生成に失敗"

    # --- 生成されたピッチ資料骨子の表示 ---
    if 'pitch_deck_draft_text' in st.session_state:
        st.divider()
        st.subheader("生成されたピッチ資料骨子（案）")
        st.markdown(st.session_state.pitch_deck_draft_text)
        # コピーボタンを追加すると便利
        if st.button("骨子をクリップボードにコピー", key="copy_pitch"):
             # pyperclipライブラリが必要になる場合がある (pip install pyperclip)
             # import pyperclip
             # pyperclip.copy(st.session_state.pitch_deck_draft_text)
             st.success("コピーしました！") # Note: Streamlitにはネイティブのコピーボタンはないため、外部ライブラリかJavaScriptを使う必要あり。これは簡易表示。


    st.divider()
    # --- ナビゲーション ---
    col_nav1_step5, col_nav2_step5 = st.columns(2)
    with col_nav1_step5:
        if st.button("ステップ4（競合/Moat）に戻る", key="back_to_step4"):
            st.session_state.step = 4
            if 'pitch_deck_draft_text' in st.session_state: del st.session_state.pitch_deck_draft_text
            st.rerun()
    with col_nav2_step5:
        if st.button("ステップ6（VCレビュー）へ進む", key="goto_step6"):
            st.session_state.step = 6 # ステップ6へ
            st.rerun()

# --- ステップ6: VC/役員レビュー ---
elif st.session_state.step == 6:
    st.header("ステップ6: VC/役員レビュー")
    st.caption("生成されたピッチ資料骨子をAI（VCペルソナ）がレビューし、フィードバックを提供します。")
    st.divider()

    # --- 評価対象ピッチ骨子の取得 ---
    pitch_draft = st.session_state.get('pitch_deck_draft_text', '')

    if not pitch_draft:
        st.warning("評価対象のピッチ資料骨子が見つかりません。ステップ5で生成してください。")
        if st.button("ステップ5に戻る"):
            st.session_state.step = 5
            st.rerun()
        st.stop()
    else:
        # ピッチ骨子を表示（長いためエキスパンダーに入れる）
        with st.expander("評価対象のピッチ資料骨子（AI生成案）", expanded=False):
            st.markdown(pitch_draft)
        st.divider()


    # --- VC評価の生成 (まだ結果がなければ実行) ---
    if 'vc_review_results_text' not in st.session_state: # 保存用キーを変更
        st.info("AI(VC)がピッチ資料をレビュー中です...")

        # プロンプト作成 (VC評価用 - 以前のものと同様)
        vc_review_prompt = f"""あなたは、革新的な技術シーズの事業化可能性を評価する、経験豊富で厳しい視点を持つベンチャーキャピタリスト（VC）です。ビジネスとしての「儲かるか」「スケールするか」「持続可能か」という観点を最も重視します。

        以下の「ピッチ資料骨子」をVCの視点から厳しく評価し、下記の形式でフィードバックを出力してください。

        # 評価対象ピッチ資料骨子:
        ---
        {pitch_draft}
        ---

        # 出力形式:
        1.  **事業評価スコア（10点満点）:**
            * ビジネスとしての魅力度、ピッチ内容の完成度を総合的に10点満点で評価し、その主な根拠を簡潔に述べてください。
        2.  **課題リスト:**
            * このピッチ内容や事業計画における、特に問題となる点、リスク、さらなる深掘りや改善が必要な点を「課題」として具体的にリストアップしてください。各課題について、なぜそれが問題なのかをVC視点で説明してください。
        3.  **Next Actionリスト:**
            * 上記の課題を解決し、事業化や資金調達に向けて次に行うべき具体的なアクションを優先度が高い順に提案してください。各アクションについて、それが「LLMに手伝ってもらえること」か「起業家/研究者自身が行う必要があること」かを明記してください。

        フィードバックは具体的かつ建設的であるべきですが、視点は厳しく保ってください。マークダウン形式で記述してください。
        """

        try:
            with st.spinner("Gemini(VC)がレビュー中..."):
                response_vc_review = model.generate_content(vc_review_prompt)
                st.session_state.vc_review_results_text = response_vc_review.text # 結果を保存
                st.success("VCレビューが完了しました！")
                st.rerun() # 表示のために再実行
        except Exception as e:
            st.error(f"VCレビュー中にエラーが発生しました: {e}")
            st.session_state.vc_review_results_text = "AIによるVCレビューに失敗しました。"

    # --- VC評価結果の表示 ---
    st.subheader("AI(VC)によるレビュー結果")
    if 'vc_review_results_text' in st.session_state:
        # !!! 本来はAI応答テキストをパースして項目ごとに表示する !!!
        # (今回は簡易的に応答全体を表示)
        st.markdown(st.session_state.vc_review_results_text)
    else:
        st.info("VCレビュー結果を生成中です...")


    # --- ナビゲーション ---
    st.divider()
    col_nav1_step6, col_nav2_step6 = st.columns(2)
    with col_nav1_step6:
        if st.button("ステップ5（ピッチ資料生成）に戻る", key="back_to_step5"):
            st.session_state.step = 5
            if 'vc_review_results_text' in st.session_state: del st.session_state.vc_review_results_text
            st.rerun()
    with col_nav2_step6:
        # アプリケーションの最後に到達
        st.success("全てのステップが完了しました！")
        # ここに最初に戻るボタンなどを置いても良い
        if st.button("最初からやり直す", key="restart_app"):
             # session_state をクリアする方法はいくつかあるが、ページをリロードさせるのが簡単
             # または、step=0 にして関連データを削除
             for key in list(st.session_state.keys()):
                 if key != 'step': # step以外を削除する場合（初期化処理に任せる）
                    del st.session_state[key]
             st.session_state.step = 0
             st.rerun()