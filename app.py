import streamlit as st
import google.generativeai as genai
import os
import re # 正規表現モジュールをインポート

from duckduckgo_search import DDGS
from googleapiclient.discovery import build # Google APIクライアントライブラリ


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

# --- VPCパース関数の例 (簡易版) ---
def parse_vpc_response(text):
    parsed_vpc_blocks = {}
    # VPCの6ブロックの想定される見出し (AIの出力に合わせる)
    # プロンプトで指定した見出し形式 "## 見出し名 (英語名)" を想定
    vpc_headings_map = {
        "顧客のジョブ": "顧客のジョブ (Customer Jobs)", # 表示名: プロンプト内の見出し名
        "ペイン": "顧客のペイン (Customer Pains)",
        "ゲイン": "顧客のゲイン (Customer Gains)",
        "製品・サービス": "製品・サービス (Products & Services)",
        "ペインリリーバー": "ペインリリーバー (Pain Relievers)",
        "ゲインクリエイター": "ゲインクリエイター (Gain Creators)"
    }
    # より頑健にするには正規表現の詳細化が必要
    current_heading_key = None
    current_content = []

    if not text: # textがNoneや空の場合の処理
        return parsed_vpc_blocks

    for line in text.splitlines():
        matched_heading = None
        for display_name, actual_heading_pattern in vpc_headings_map.items():
            # 見出し行を探す (行頭が ## で始まり、指定の見出し名を含むか)
            # AIの出力が "## 顧客のジョブ (Customer Jobs)" のような形式を期待
            if line.strip().startswith(f"## {actual_heading_pattern}"):
                matched_heading = display_name # 表示名をキーとして使う
                break
        
        if matched_heading:
            if current_heading_key and current_content:
                parsed_vpc_blocks[current_heading_key] = "\n".join(current_content).strip()
            current_heading_key = matched_heading
            current_content = []
        elif current_heading_key:
            current_content.append(line)
    
    # 最後のブロックを保存
    if current_heading_key and current_content:
        parsed_vpc_blocks[current_heading_key] = "\n".join(current_content).strip()

    # 想定されるキーが全て揃っているか確認し、なければ空文字で初期化
    for display_name in vpc_headings_map.keys():
        if display_name not in parsed_vpc_blocks:
            parsed_vpc_blocks[display_name] = ""

    return parsed_vpc_blocks
# --- VPCパース関数ここまで ---

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
    st.info("""
    AIがあなたの技術概要に基づいて、有望と思われるターゲット市場や具体的な顧客像のアイデアを提案します。
    これらのアイデアを元に、どの顧客層に焦点を当てるか検討し、一つ選択または自由記述してください。
    ここで選んだターゲットが、この後の分析の軸となります。
    """)
    st.caption("AIが提案したターゲット戦略のアイデア、またはご自身で考えるターゲットについて、顧客課題の整理に進みます。") # キャプション修正
    st.divider()

    st.subheader("AIによるターゲット戦略提案")
    if 'target_strategy_ideas' in st.session_state and st.session_state.target_strategy_ideas:
        st.markdown(st.session_state.target_strategy_ideas)

        # --- ↓↓↓ ターゲット選択UIを修正 ↓↓↓ ---
        st.divider()
        st.subheader("ターゲットの選択または入力")

        # target_strategy_ideas から選択肢を抽出
        target_options = []
        raw_ideas_text = st.session_state.target_strategy_ideas
        # "**ターゲット案X:**" で始まる行を抽出 (タイトル行全体)
        extracted_options = [line.strip() for line in raw_ideas_text.splitlines() if line.strip().startswith("**ターゲット案")]
        if extracted_options:
             target_options.extend(extracted_options)
        else:
             st.warning("AI提案から選択肢を抽出できませんでした。手動で入力してください。")

        # 「その他」選択肢を追加
        other_option = "その他（自由記述）"
        target_options.append(other_option)

        # ラジオボタンで選択
        selected_target_option = st.radio(
            "ターゲットを選択、または「その他」を選んで自由記述してください:",
            options=target_options,
            key="target_selection_radio",
            index=len(target_options)-1 # デフォルトで「その他」を選択状態にする場合
            # index=0 # デフォルトで最初の提案を選択状態にする場合
        )

        # 「その他」が選択されたら自由記述欄を表示
        manual_target_input = ""
        if selected_target_option == other_option:
            manual_target_input = st.text_area(
                "ターゲット顧客（セグメント、ペルソナなど）を具体的に記述してください:",
                key="manual_target_input",
                height=150
            )

        # 課題整理へ進むボタン
        if st.button("選択/入力したターゲットの課題整理へ進む", key="goto_problem_definition"):
            final_selected_target = ""
            valid_selection = False

            if selected_target_option == other_option:
                if manual_target_input.strip(): # 自由記述欄に入力があるか
                    final_selected_target = manual_target_input.strip()
                    valid_selection = True
                else:
                    st.warning("「その他」を選択した場合は、ターゲットを自由記述欄に入力してください。")
            else: # AI提案から選択された場合
                final_selected_target = selected_target_option # ラジオボタンの選択肢（タイトル行全体）をそのまま使う
                valid_selection = True

            if valid_selection:
                # 選択/入力されたターゲット情報をsession_stateに保存
                st.session_state.selected_target = final_selected_target
                # 課題リストはクリアしておく（ターゲットが変わったので再生成）
                if 'potential_problems' in st.session_state:
                    del st.session_state.potential_problems
                st.session_state.step = 1.2 # 次のサブステップへ
                st.rerun()
        # --- ↑↑↑ ターゲット選択UIを修正 ↑↑↑ ---

    else:
        st.warning("ターゲット戦略のアイデアがまだ生成されていません。ステップ0に戻ってください。")
        # (戻るボタンのロジックは変更なし)

    st.divider()
    # st.info("次のステップ（課題整理、VPC作成など）は未実装です。") # このinfoは不要になる

    # ナビゲーション（仮） - ステップ0に戻るボタンのみ残す
    if st.button("ステップ0（入力）に戻る"):
        st.session_state.step = 0
        if 'target_strategy_ideas' in st.session_state: del st.session_state.target_strategy_ideas
        if 'selected_target' in st.session_state: del st.session_state.selected_target
        st.rerun()

# --- ステップ1.2: 壁打ち - 課題整理 ---
elif st.session_state.step == 1.2:
    st.header("ステップ1: 壁打ち - 課題整理")
    st.info("""
    ステップ1で選択/入力したターゲット顧客が抱えている可能性のある「課題」や「ペイン（悩み・不満）」をAIがリストアップします。
    これらの課題の中から、あなたの技術で解決できそうな、特に重要だと考えるものを複数選択してください。
    ここで選んだ課題が、次のValue Proposition Canvas作成の重要なインプットになります。
    """)
    st.caption("AIがリストアップした課題の中から、特に重要だと思うもの、解決したいと思うものを選択してください。") # キャプション変更
    st.divider()

    # 選択されたターゲットを表示 (変更なし)
    selected_target = st.session_state.get('selected_target', '（ターゲットが選択されていません）')
    st.subheader("選択されたターゲット")
    st.write(selected_target)
    st.divider()

    # --- AIによる課題リスト生成 (変更なし) ---
    if 'potential_problems' not in st.session_state:
        # (AI呼び出しロジックは前回と同じ)
        st.info("AIが課題を分析中です...")
        tech_summary = st.session_state.get('tech_summary', '')
        if not tech_summary:
             st.error("技術概要がありません。ステップ0からやり直してください。")
             st.stop()
        if not selected_target or selected_target == '（ターゲットが選択されていません）':
             st.error("ターゲットが選択されていません。ステップ1に戻ってください。")
             st.stop()
       
       # --- ↓↓↓ プロンプトを修正 ↓↓↓ ---
        problem_prompt = f"""あなたは、新規事業のアイデアを検討するコンサルタントです。
        以下の「技術概要」と、その技術の「ターゲット候補」に関する情報を分析してください。
        そして、**このターゲット候補が抱えている可能性のある「課題」や「ペイン（悩み、不満、困りごと）」**を、できるだけ具体的に5～10個程度リストアップしてください。
        この分析は、これまでの会話とは独立した、今回提示された情報のみに基づいて行ってください。

        # 技術概要:
        {tech_summary}

        # ターゲット候補:
        {selected_target}

        # 出力形式 (マークダウンの箇条書き):
        * [具体的な課題やペイン1]
        * [具体的な課題やペイン2]
        * ...
        """
        # --- ↑↑↑ プロンプトを修正 ↑↑↑ ---

        try:
            with st.spinner("Geminiが課題を分析中..."):
                 response_problems = model.generate_content(problem_prompt)
                 st.session_state.potential_problems = response_problems.text
                 st.success("課題リストの生成が完了しました。")
                 st.rerun()
        except Exception as e:
            st.error(f"課題リスト生成中にエラーが発生しました: {e}")
            st.session_state.potential_problems = "課題リストの生成に失敗しました。"

    # --- ★★★ 課題リスト表示と選択UI ★★★ ---
    st.subheader("AIが考えたターゲットの課題リスト（複数選択可）")

    selected_problems_list = [] # 選択された課題を格納するリスト
    potential_problems_text = st.session_state.get('potential_problems', '')

    if potential_problems_text and potential_problems_text != "課題リストの生成に失敗しました。":
        # AI応答テキストを解析して課題リストを作成 (簡易版: 行ごとに分割し、'*'などを除去)
        problem_lines = [line.strip('* ') for line in potential_problems_text.splitlines() if line.strip() and line.strip().startswith('*')]
        if not problem_lines: # もし'*'で始まらない形式なら、空行以外をそのまま使う
             problem_lines = [line.strip() for line in potential_problems_text.splitlines() if line.strip()]

        if problem_lines:
            # 各課題に対してチェックボックスを表示
            for i, problem in enumerate(problem_lines):
                key = f"problem_select_{i}"
                # チェックボックスの状態は st.session_state に自動で保存される
                is_selected = st.checkbox(problem, key=key)
                if is_selected:
                    selected_problems_list.append(problem) # チェックされたらリストに追加
        else:
            st.warning("課題リストの解析に失敗したか、課題が見つかりませんでした。AIの応答を確認してください。")
            st.text(potential_problems_text) # 生の応答を表示

    else:
        st.info("課題リストを生成中です...")

    st.divider()

    # --- ナビゲーション ---
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("ステップ1（ターゲット選択）に戻る", key="back_to_step1_from_1_2"): # キー名を変更
            st.session_state.step = 1
            if 'potential_problems' in st.session_state: del st.session_state.potential_problems
            if 'selected_problems' in st.session_state: del st.session_state.selected_problems # 選択結果もクリア
            st.rerun()
    with col_nav2:
        # ↓↓↓ ボタンのロジックを修正 ↓↓↓
        if st.button("ステップ2 選択した課題でVPC作成へ進む", key="goto_vpc_from_1_2"): # ボタン名変更、キー名変更
            if selected_problems_list: # 課題が1つ以上選択されているかチェック
                # 選択された課題リストをsession_stateに保存
                st.session_state.selected_problems = selected_problems_list
                st.session_state.step = 1.3 # 次のステップへ
                # VPCドラフトはクリアしておく（インプットが変わるので再生成）
                if 'vpc_draft_text' in st.session_state: del st.session_state.vpc_draft_text
                if 'vpc_final_data' in st.session_state: del st.session_state.vpc_final_data # 編集データもクリア
                st.rerun()
            else:
                st.warning("VPC作成に進むには、少なくとも1つの課題を選択してください。")
        # --- ↑↑↑ ボタンのロジックを修正 ↑↑↑ ---

# --- ステップ1.3: 壁打ち - Value Proposition Canvas作成支援 ---
elif st.session_state.step == 1.3:
    st.header("ステップ1: 壁打ち - Value Proposition Canvas")
    st.info("""
    Value Proposition Canvas (VPC) を使って、顧客への提供価値を具体化します。
    AIが、これまでの情報（技術概要、ターゲット、選択された課題）を元にVPCの各ブロックのドラフトを作成しますので、
    それを参考に内容を編集・追記してください。
    """)
    with st.expander("💡 Value Proposition Canvasとは？"):
        st.markdown("""
        Value Proposition Canvasは、以下の2つの側面から顧客への価値提案を整理するフレームワークです。
        * **顧客セグメント (右側):** 顧客が誰で、何をしようとし（顧客のジョブ）、何に困っていて（ペイン）、何を得たいか（ゲイン）を明確にします。
        * **価値提案 (左側):** あなたの製品・サービスが、どのように顧客のペインを取り除き（ペインリリーバー）、ゲインを生み出すか（ゲインクリエイター）を定義します。
        これらの整合性を高めることが重要です。
        """)
    st.caption("AIが提案するドラフトを元に、顧客への提供価値を具体化しましょう。")
    st.divider()

    # ... (必要な情報取得は同じ) ...
    selected_target = st.session_state.get('selected_target', '')
    focused_problems_list = st.session_state.get('selected_problems', [])
    tech_summary = st.session_state.get('tech_summary', '')

    # --- AIによるVPCドラフト生成 (まだパース結果がなければ) ---
    if 'parsed_vpc_blocks' not in st.session_state: # パース後のデータがあるかで判断
        st.info("AIがVPCドラフトを作成中です...")
        
        # ... (vpc_prompt 作成は同じ。入力として focused_problems_list を使う) ...
        vpc_prompt = f"""あなたは事業開発の専門家です。以下の提供情報**のみ**に基づいて、「Value Proposition Canvas」の6つの構成要素について、具体的なアイデアを提案・記述してください。過去の会話の文脈は考慮せず、今回提示された情報だけで判断してください。

        # 提供情報
        ## 技術概要:
        {tech_summary}

        ## ターゲット候補:
        {selected_target}

        ## ターゲットの【主要な】課題リスト (ユーザー選抜済):
        {chr(10).join([f'* {p}' for p in focused_problems_list]) if focused_problems_list else "(ユーザーによって特に選択された課題はありません。ターゲット候補全般の一般的な課題を考慮してください。)"}

        # 作成するVPCの構成要素と記述内容の指示:
        1.  **顧客のジョブ (Customer Jobs):** ターゲット顧客が達成しようとしていること、解決したい仕事は何か？
        2.  **顧客のペイン (Customer Pains):** 顧客が現状感じている不満、障害、リスクは何か？（上記の【主要な】課題リストを最重要の参考情報として具体的に）
        3.  **顧客のゲイン (Customer Gains):** 顧客が期待する成果、メリット、喜びは何か？
        4.  **製品・サービス (Products & Services):** あなたの技術を元にした具体的な製品やサービス案は？
        5.  **ペインリリーバー (Pain Relievers):** その製品・サービスが、どのように顧客のペインを取り除くか？
        6.  **ゲインクリエイター (Gain Creators):** その製品・サービスが、どのように顧客のゲインを生み出すか？

        # 出力形式 (各要素を以下の見出しで明確に区切ってください):
        ## 顧客のジョブ (Customer Jobs)
        [ここに具体的な記述を複数箇条書きで]

        ## 顧客のペイン (Customer Pains)
        [ここに具体的な記述を複数箇条書きで]

        ## 顧客のゲイン (Customer Gains)
        [ここに具体的な記述を複数箇条書きで]

        ## 製品・サービス (Products & Services)
        [ここに具体的な記述を複数箇条書きで]

        ## ペインリリーバー (Pain Relievers)
        [ここに具体的な記述を複数箇条書きで]

        ## ゲインクリエイター (Gain Creators)
        [ここに具体的な記述を複数箇条書きで]

        マークダウン形式で記述してください。
        """

        try:
            with st.spinner("GeminiがVPCドラフトを作成中..."):
                response_vpc = model.generate_content(vpc_prompt)
                vpc_raw_text = response_vpc.text
                st.session_state.vpc_draft_text = vpc_raw_text # 生データも保存

                # ★★★ AI応答をパースして session_state に保存 ★★★
                if 'vpc_draft_text' in st.session_state and 'parsed_vpc_blocks' not in st.session_state: # まだパースされていなければ
                    vpc_raw_text = st.session_state.vpc_draft_text
                    if vpc_raw_text != "VPCドラフトの生成に失敗しました。": # エラーでない場合のみパース
                        parsed_data = parse_vpc_response(vpc_raw_text)
                        st.session_state.parsed_vpc_blocks = parsed_data
                        st.success("VPCドラフトの解析が完了しました。") # メッセージ変更
                        # st.rerun() # ここでのリランは不要

        
        except Exception as e:
            st.error(f"VPCドラフト生成中にエラーが発生しました: {e}")
            st.session_state.vpc_draft_text = "VPCドラフトの生成に失敗しました。"
            st.session_state.parsed_vpc_blocks = {} # エラー時は空の辞書

            
    # --- VPCフレームワークと編集UIの表示 ---
    st.subheader("Value Proposition Canvas （編集可）")

    if 'parsed_vpc_blocks' in st.session_state and st.session_state.parsed_vpc_blocks:
            vpc_edit_data = st.session_state.parsed_vpc_blocks

            col_vp, col_cs = st.columns(2)

            with col_vp:
                st.markdown("#### 価値提案 (Value Proposition)")
                # ↓↓↓ 'st.session_state.vpc_ps_edit =' を削除 ↓↓↓
                st.text_area(
                    "製品・サービス (Products & Services)",
                    value=vpc_edit_data.get("製品・サービス", ""), key="vpc_ps_edit", height=150
                )
                # ↓↓↓ 'st.session_state.vpc_pr_edit =' を削除 ↓↓↓
                st.text_area(
                    "ペインリリーバー (Pain Relievers)",
                    value=vpc_edit_data.get("ペインリリーバー", ""), key="vpc_pr_edit", height=150
                )
                # ↓↓↓ 'st.session_state.vpc_gc_edit =' を削除 ↓↓↓
                st.text_area(
                    "ゲインクリエイター (Gain Creators)",
                    value=vpc_edit_data.get("ゲインクリエイター", ""), key="vpc_gc_edit", height=150
                )

            with col_cs:
                st.markdown("#### 顧客セグメント (Customer Segment)")
                # ↓↓↓ 'st.session_state.vpc_cj_edit =' を削除 ↓↓↓
                st.text_area(
                    "顧客のジョブ (Customer Jobs)",
                    value=vpc_edit_data.get("顧客のジョブ", ""), key="vpc_cj_edit", height=150
                )
                # ↓↓↓ 'st.session_state.vpc_p_edit =' を削除 ↓↓↓
                st.text_area(
                    "ペイン (Pains)",
                    value=vpc_edit_data.get("ペイン", ""), key="vpc_p_edit", height=150
                )
                # ↓↓↓ 'st.session_state.vpc_g_edit =' を削除 ↓↓↓
                st.text_area(
                    "ゲイン (Gains)",
                    value=vpc_edit_data.get("ゲイン", ""), key="vpc_g_edit", height=150
                )
    else:
        st.info("VPCドラフトを表示するデータがありません。")

    st.divider()

    # --- ナビゲーション ---
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("ステップ1.2（課題整理）に戻る", key="back_to_step1_2_from_vpc"): # キー名変更
            st.session_state.step = 1.2
            if 'vpc_draft_text' in st.session_state: del st.session_state.vpc_draft_text
            if 'parsed_vpc_blocks' in st.session_state: del st.session_state.parsed_vpc_blocks
            # 編集中のデータをクリア
            for k in ["vpc_ps_edit", "vpc_pr_edit", "vpc_gc_edit", "vpc_cj_edit", "vpc_p_edit", "vpc_g_edit"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    with col_nav2:
        if st.button("ステップ2a（Lean Canvas）へ進む", key="goto_step2a_from_vpc"): # キー名変更
            # ★★★ 編集されたVPCの内容を st.session_state.vpc_final_data に保存 ★★★
            st.session_state.vpc_final_data = {
                "顧客のジョブ": st.session_state.get("vpc_cj_edit", ""),
                "ペイン": st.session_state.get("vpc_p_edit", ""),
                "ゲイン": st.session_state.get("vpc_g_edit", ""),
                "製品・サービス": st.session_state.get("vpc_ps_edit", ""),
                "ペインリリーバー": st.session_state.get("vpc_pr_edit", ""),
                "ゲインクリエイター": st.session_state.get("vpc_gc_edit", "")
            }
            # st.write("DEBUG: Saved VPC Data for Step 2a:", st.session_state.vpc_final_data) # デバッグ表示
            # st.info("VPCの内容を保存しました。")

            st.session_state.step = 2.1
            # Lean Canvas関連のデータをクリアして再生成させる
            if 'lean_canvas_raw_output' in st.session_state: del st.session_state.lean_canvas_raw_output
            if 'lean_canvas_score_text' in st.session_state: del st.session_state.lean_canvas_score_text
            if 'lean_canvas_parsed_blocks' in st.session_state: del st.session_state.lean_canvas_parsed_blocks
            st.rerun()
    
# --- ステップ2a (2.1): Lean Canvas Draft + Score ---
elif st.session_state.step == 2.1:
    st.header("ステップ2a: Lean Canvas ドラフト作成")
    st.info("""
    Lean Canvasを使って、ビジネスモデル全体の骨子を9つの要素で整理します。
    AIがこれまでの情報（技術概要、ターゲット、課題、VPCなど）を元にドラフトと品質スコアを提案します。
    各項目を具体的に記述し、ビジネスモデルとしての実現可能性や仮説を明確にしましょう。
    """)
    with st.expander("💡 Lean Canvasとは？"):
        st.markdown("""
        Lean Canvasは、特にスタートアップなどの新規事業に適したビジネスモデル構築・検証ツールです。以下の9つの要素で構成されます。
        1.  **課題 (Problem):** 解決すべき顧客の課題は何か？
        2.  **顧客セグメント (Customer Segments):** その課題を抱えるターゲット顧客は誰か？
        3.  **独自の価値提案 (Unique Value Proposition):** なぜ顧客はあなたを選ぶのか？シンプルで強力なメッセージ。
        4.  **解決策 (Solution):** 課題を解決する具体的な製品・サービス。
        5.  **チャネル (Channels):** 顧客に価値を届ける経路。
        6.  **収益の流れ (Revenue Streams):** どのように収益を上げるか。
        7.  **コスト構造 (Cost Structure):** 事業運営にかかる主要なコスト。
        8.  **主要指標 (Key Metrics):** ビジネスの成功を測る重要な指標。
        9.  **圧倒的優位性 (Unfair Advantage):** 競合が容易に模倣できない強み。
        これらの要素を埋めることで、ビジネスモデルの全体像と検証すべき仮説が見えてきます。
        """)
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
                # --- ★★★ 1. AIによる市場調査用検索キーワード生成 ★★★ ---
        market_search_keywords_generated = []
        web_search_for_market_summary = ""
        try:
            with st.spinner("AIが市場調査用の検索キーワードを生成中... (1/3)"):
                market_keyword_prompt = f"""以下の「技術概要」と「ターゲット顧客」に基づいて、この事業が参入する可能性のある市場の「市場規模」「最新トレンド」「主要な顧客セグメントの詳細」を調査するための効果的なGoogle検索キーワードを3つ提案してください。キーワードのみを箇条書きで出力してください。

                # 技術概要:
                {tech_summary}

                # ターゲット顧客:
                {selected_target}
                """
                response_market_keywords = model.generate_content(market_keyword_prompt)
                market_search_keywords_text = response_market_keywords.text
                market_search_keywords_generated = [kw.strip("* ").strip() for kw in market_search_keywords_text.splitlines() if kw.strip() and not kw.strip().startswith("Please provide")]
                st.write("DEBUG - AIが生成した市場調査用キーワード:", market_search_keywords_generated) # デバッグ用
        except Exception as e:
            st.warning(f"市場調査用キーワード生成中にエラー: {e}")

        # --- ★★★ 2. Web検索実行 (Google Custom Search API) ★★★ ---
        if market_search_keywords_generated:
            try:
                with st.spinner("市場情報をGoogle検索で収集中... (2/3)"):
                    google_api_key = st.secrets["GOOGLE_API_KEY"]
                    search_engine_id = st.secrets["SEARCH_ENGINE_ID"]
                    service = build("customsearch", "v1", developerKey=google_api_key)
                    market_search_snippets = []
                    for keyword in market_search_keywords_generated[:3]: # 上位3キーワード
                        res = service.cse().list(q=keyword, cx=search_engine_id, num=2).execute() # 各2件
                        if 'items' in res:
                            for item in res['items']:
                                title = item.get('title', '')
                                snippet = item.get('snippet', '').replace('\n', ' ')
                                market_search_snippets.append(f"- {title}: {snippet}")
                    if market_search_snippets:
                        web_search_for_market_summary = "\n".join(market_search_snippets)
                        st.write("DEBUG - 収集した市場情報（一部）:", web_search_for_market_summary[:200] + "...") # デバッグ用
            except Exception as e:
                st.warning(f"市場情報のWeb検索中にエラー: {e}")
        else:
            web_search_for_market_summary = "市場調査のためのキーワードが生成されなかったため、Web検索はスキップされました。"


        # --- ★★★ 3. Lean Canvas生成AIへの情報提供 (プロンプト修正) ★★★ ---
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

        lc_prompt = f"""以下の情報に基づいて、Lean Canvasの9つの構成要素のドラフトを作成してください。
        特に「顧客セグメント」と、市場規模を示唆する「主要指標」の項目については、提供された「市場調査のWeb検索結果」を最大限活用してください。
        さらに、作成したドラフト全体について、事業アイデアの初期段階としての「品質スコア」を100点満点で採点し、その主な理由も記述してください。
        **最終的な出力は、必ずLean Canvasの9ブロック全てと品質スコアを含めてください。**

        # 技術概要:
        {tech_summary}

        # ターゲット顧客:
        {selected_target}

        # Value Proposition Canvas の内容:
        {vpc_data}

        # 市場調査のWeb検索結果 (これを参考に市場規模や顧客セグメントを具体化):
        {web_search_for_market_summary if web_search_for_market_summary else "（Web検索結果なし。一般的な知識で補完してください。）"}

        # 作成するLean Canvasの構成要素 (9項目全て記述必須):
        1. 課題 (Problem)
        2. 顧客セグメント (Customer Segments)
        3. 独自の価値提案 (Unique Value Proposition)
        4. 解決策 (Solution)
        5. チャネル (Channels)
        6. 収益の流れ (Revenue Streams)
        7. コスト構造 (Cost Structure)
        8. 主要指標 (Key Metrics)
        9. 圧倒的優位性 (Unfair Advantage)

        # 品質スコアの評価観点: (前回と同じ)
        # ...

        # 出力形式 (マークダウン、各項目を見出しで明確に区切る):
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
            with st.spinner("Web検索情報を元にGeminiがLean Canvasを作成・評価中... (3/3)"):
                response_lc = model.generate_content(lc_prompt)
                raw_output = response_lc.text
                st.session_state.lean_canvas_raw_output = raw_output

                parsed_score, parsed_blocks = parse_lean_canvas_response(raw_output)
                st.session_state.lean_canvas_score_text = parsed_score
                st.session_state.lean_canvas_parsed_blocks = parsed_blocks
                st.success("市場調査とLean Canvasドラフト作成が完了しました。")
        except Exception as e:
            st.error(f"Lean Canvas作成中にエラーが発生しました: {e}")
   
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
    st.info("""
    このステップでは、Lean Canvasで描いたビジネスモデルの骨子を元に、さらに具体的な側面から事業アイデアを深掘りしていきます。
    MVP（実用最小限の製品）、SWOT（強み・弱み・機会・脅威）、4P（製品・価格・流通・販促）、3C（顧客・競合・自社）、
    そして初期的な財務計画について、AIの提案を参考にしながら検討を深めましょう。
    各分析結果は編集可能です。
    """)
    st.caption("Lean Canvasの内容などを元に、MVP、SWOTなどの分析を行います。")
    st.divider()

    # --- 必要な情報をsession_stateから取得 ---
    tech_summary = st.session_state.get('tech_summary', '')
    selected_target = st.session_state.get('selected_target', '')
    lc_parsed_blocks = st.session_state.get('lean_canvas_parsed_blocks', {})
    # ... (VPCデータや、編集されたLean Canvasの各ブロックの値も必要に応じて取得) ...
    # 例: lean_canvas_data = { key.replace('lc_', ''): st.session_state[key] for key in st.session_state if key.startswith('lc_') }
    lean_canvas_problem = st.session_state.get('lc_課題', '') # key名を正確に指定
    lean_canvas_solution = st.session_state.get('lc_解決策', '')
    lean_canvas_uvp = st.session_state.get('lc_独自の価値提案', '')
    lc_revenue = lc_parsed_blocks.get('収益の流れ', '')
    lc_cost = lc_parsed_blocks.get('コスト構造', '')
    
    if (
        'mvp_ideas_text' not in st.session_state or
        'swot_analysis_text' not in st.session_state or
        'four_p_analysis_text' not in st.session_state or
        'three_c_analysis_text' not in st.session_state or
        'financials_ideas_text' not in st.session_state
    ):
        st.info("AIが深掘り分析を実行中です。少々お待ちください...")
        all_analyses_successful = True
   
   
    # --- MVP検討セクション ---
    with st.expander("MVP (Minimum Viable Product) の検討", expanded=True):
        st.markdown("""
        **MVP（実用最小限の製品）とは、顧客に価値を提供できる最小限の機能だけを備えた製品・サービスのことです。**
        MVPを早期に構築し、実際の顧客に試してもらうことで、仮説を検証し、学習を重ねながら製品を改善していくことを目指します。
        AIの提案を参考に、あなたの技術で最初に検証すべき核となる価値と、それを実現するシンプルな製品アイデアを考えてみましょう。
        """)

        # AIにMVP案を提案させるボタン
        if 'mvp_ideas_text' not in st.session_state: 
            mvp_prompt = f"""
            以下の情報を元に、実現可能で価値検証に適したMVP（Minimum Viable Product）のアイデアを2～3個提案してください。それぞれのMVPについて、主要な機能、ターゲットユーザー、検証したい仮説を簡潔に記述してください。

                # 技術概要:
                {tech_summary}

                # ターゲット顧客:
                {selected_target}

                # Lean Canvas - 課題:
                {lean_canvas_problem if lean_canvas_problem else "（Lean Canvasの課題情報は提供されていません）"}

                # Lean Canvas - 解決策:
                {lean_canvas_solution if lean_canvas_solution else "（Lean Canvasの解決策情報は提供されていません）"}

                # Lean Canvas - 独自の価値提案:
                {lean_canvas_uvp if lean_canvas_uvp else "（Lean CanvasのUVP情報は提供されていません）"}

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
                    response_mvp = model.generate_content(mvp_prompt)
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
        st.markdown("""
        **SWOT分析は、事業を取り巻く環境を以下の4つの観点から整理・分析するフレームワークです。**
        * **強み (Strengths):** 目標達成に貢献する組織内部の強み。
        * **弱み (Weaknesses):** 目標達成の障害となる組織内部の弱み。
        * **機会 (Opportunities):** 目標達成に貢献する外部環境の機会。
        * **脅威 (Threats):** 目標達成の障害となる外部環境の脅威。
        AIが提案する各要素を参考に、自社の状況を客観的に把握しましょう。（クロスSWOT分析は今後のステップで検討します）
        """)

        if 'swot_analysis' not in st.session_state: 
            swot_prompt = f"""以下の情報を元に、この事業アイデアに関するSWOT分析（強み、弱み、機会、脅威）を行ってください。内部環境と外部環境の両面から、具体的な要素をリストアップしてください。

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
                        response_swot = model.generate_content(swot_prompt)
                        st.session_state.swot_analysis = response_swot.text # 結果を保存
            except Exception as e:
                st.error(f"SWOT分析中にエラー: {e}")
                st.session_state.swot_analysis = "SWOT分析の生成に失敗"

        # AIが生成したSWOT分析結果の表示
        if 'swot_analysis' in st.session_state:
            st.subheader("AIによるSWOT分析結果")
            st.markdown(st.session_state.swot_analysis)
            st.divider()

        # ユーザーコメント欄
        st.subheader("SWOT分析に関するコメント・考察")
        st.text_area("AIの分析結果に対する考察や、追加の要素などを記述してください。", height=150, key="swot_comments_user")


    # --- 4P分析セクション ---
    with st.expander("4P分析", expanded=False):
        st.markdown("""
        **4P分析は、マーケティング戦略を以下の4つの要素から具体化するフレームワークです。**
        * **Product（製品・サービス）:** どのような製品・サービスを提供するか？（品質、デザイン、ブランドなど）
        * **Price（価格）:** どのような価格で提供するか？（価格設定、価格帯、割引戦略など）
        * **Place（流通・チャネル）:** どのように顧客に届けるか？（販売場所、流通経路など）
        * **Promotion（販促・プロモーション）:** どのように顧客に知ってもらい、購入を促すか？（広告、広報、販売促進活動など）
        AIの提案を参考に、具体的なマーケティング施策のアイデアを練りましょう。
        """)

    # AIに4P分析を実行させるボタン
        if 'four_p_analysis_text' not in st.session_state: # MVPがまだ生成されていなければif st.button("4P分析をAIに実行させる", key="generate_4p"):
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
        st.markdown("""
        **3C分析は、事業成功の鍵となる3つの要素の現状を分析し、戦略を導き出すフレームワークです。**
        * **Customer（顧客・市場）:** ターゲット顧客は誰で、どのようなニーズを持っているか？市場規模や成長性は？
        * **Competitor（競合）:** 主要な競合は誰で、どのような強み・弱みを持っているか？
        * **Company（自社）:** 自社の経営資源（強み・弱み）は何か？顧客ニーズに応え、競合に勝つために何をすべきか？
        AIがこれまでの情報を統合して提案する分析結果を元に、自社の立ち位置と戦略の方向性を確認しましょう。
        """)

    # AIに3C分析を実行させる
        if 'three_c_analysis_text' not in st.session_state:
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
            lc_unfair_advantage = lc_parsed_blocks.get('lc_圧倒的優位性', '') # 競合情報含む可能性あり
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
            * 圧倒的優位性: {lc_unfair_advantage}

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
        st.markdown("""
        **ここでは、事業の初期段階における財務的な側面を大まかに捉えます。**
        詳細な事業計画ではなく、主要な収益源、コスト構造、そして初期に考慮すべき財務的なポイント（価格設定の考え方、初期投資、資金調達の必要性など）についてAIがアイデアを提案します。
        実現可能性のあるビジネスモデルを考える上での参考にしてください。
        """)

        # AIに財務計画の初期アイデアを提案させるボタン
        if 'financials_ideas_text' not in st.session_state:
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
    lc_competitors_input = st.session_state.get('lc_競合', '') # Lean Canvasの競合キーを確認
    lc_unfair_advantage = st.session_state.get('lc_圧倒的優位性', '') # Lean Canvasの優位性キーを確認
    swot_analysis = st.session_state.get('swot_analysis_text', '')

    # --- ステップ4のAI分析をここで実行 (まだ結果がなければ) ---
    if not st.session_state.get('step4_analyses_complete', False):
        st.info("AIが競合分析とMoat提案を実行中です。これには数分かかることがあります...")
        all_analyses_successful_step4 = True # エラー追跡用フラグ

    
    # --- 1. 競合分析 (Web検索あり) ---
        if 'competitor_analysis_text' not in st.session_state:
            web_search_results_summary = ""
            search_keywords_generated_by_ai = []        # --- 1. AIによる検索キーワード生成 ---
            try:
                with st.spinner("AIが検索キーワードを生成中... (ステップ4 - 1/4)"):
                    # ↓↓↓ キーワード生成プロンプトを修正 ↓↓↓
                    keyword_prompt = f"""あなたは市場調査の専門家です。
                    以下の「技術概要」と「既存の競合情報」のみに基づいて、詳細な競合分析を行うために効果的かつ具体的なGoogle検索キーワードを3～5個提案してください。
                    これまでの会話の文脈は考慮せず、今回提示された情報だけで判断してください。
                    キーワードのみを箇条書きで出力してください。

                    # 技術概要:
                    {tech_summary}

                    # 既存の競合情報（あれば）:
                    {lc_competitors_input if lc_competitors_input else "特になし"}
                    """
                    # ↑↑↑ キーワード生成プロンプトを修正 ↑↑↑
                    response_keywords = model.generate_content(keyword_prompt)
                    search_keywords_text = response_keywords.text
                    search_keywords_generated_by_ai = [kw.strip("* ").strip() for kw in search_keywords_text.splitlines() if kw.strip() and not kw.strip().startswith("Please provide")] # AIがエラーを返した場合の対策
                
                # 1b. Web検索実行 (Google Custom Search API)　
                if search_keywords_generated_by_ai:
                    st.subheader("AIが生成した検索キーワード:")
                    st.write(search_keywords_generated_by_ai)
                else:
                    st.warning("AIによる検索キーワード生成に失敗したか、キーワードがありませんでした。AIの応答を確認してください。")
                    st.text(search_keywords_text) # AIの応答そのものを表示

                # --- 2. Web検索の実行 (Google Custom Search API) ---
                if search_keywords_generated_by_ai:
                    with st.spinner("Google検索を実行し、関連情報を収集中... (ステップ4 - 2/4)"):
                        google_api_key = st.secrets["GOOGLE_API_KEY"]
                        search_engine_id = st.secrets["SEARCH_ENGINE_ID"]
                        service = build("customsearch", "v1", developerKey=google_api_key)
                        search_snippets = []

                        for keyword in search_keywords_generated_by_ai[:3]:
                            st.markdown(f"**'{keyword}' でGoogle検索中...**")
                            try:
                                res = service.cse().list(q=keyword, cx=search_engine_id, num=2).execute()
                                if 'items' in res:
                                    for item in res['items']:
                                        title = item.get('title', 'タイトルなし')
                                        link = item.get('link', '#')
                                        snippet = item.get('snippet', '概要なし').replace('\n', ' ')
                                        search_snippets.append(f"- タイトル: {title}\n  概要: {snippet}\n  URL: {link}\n")
                            except Exception as search_e:
                                st.warning(f"'{keyword}' のGoogle検索中にエラー: {search_e}") # エラーではなく警告
                        if search_snippets:
                            web_search_results_summary = "\n---\n".join(search_snippets)
                else:
                    web_search_results_summary = "検索キーワードがないか生成に失敗したため、Web検索はスキップされました。"

                # --- 1c.  AIによる最終的な競合分析 (変更なし、web_search_results_summary を使用) ---
                with st.spinner("Web検索結果を元にAIが最終分析中...(ステップ4 - 3/4)"):
                     competitor_prompt_final = f"""以下の「技術概要」、「Lean Canvas記載の競合情報」、および「Web検索からの関連情報」に基づいて、主要な競合企業（または代替技術）を特定し、それぞれの特徴、強み、弱み、市場での評判や最近の動向などを詳細に分析してください。

                    # 技術概要:
                    {tech_summary}

                    # Lean Canvas記載の競合情報（あれば）:
                    {lc_competitors_input if lc_competitors_input else "特になし"}

                    # Web検索からの関連情報:
                    {web_search_results_summary if web_search_results_summary else "Web検索結果なし"}

                    # 分析してほしい観点:
                    * 主要な競合企業/技術名
                    * 提供している製品/サービス
                    * 想定されるターゲット顧客
                    * 強み
                    * 弱み
                    * 価格帯やビジネスモデル（推測で可）
                    * 市場での評判や最近の動向（Web検索結果から推測できる場合）

                    # 出力形式 (マークダウン):
                    ## 競合分析結果 (Web調査加味)
                    ### 競合A: [企業名/技術名]
                    * 製品/サービス: ...
                    (以下、各観点について記述)
                    ### 競合B: [企業名/技術名]
                    ... (同様に)
                    """
                response_competitors = model.generate_content(competitor_prompt_final)
                st.session_state.competitor_analysis_text = response_competitors.text
            
            except Exception as e:
                st.error(f"競合分析プロセス中にエラー: {e}")
                st.session_state.competitor_analysis_text = "競合分析の生成に失敗"
                all_analyses_successful_step4 = False

           
    # --- 2. Moat提案 (まだなければ、かつ競合分析が（一応）終わっていれば) ---
        if 'moat_ideas_text' not in st.session_state:
            # Moat生成に必要なコンテキストを取得
            competitor_analysis_results_for_moat = st.session_state.get('competitor_analysis_text', '(競合分析結果なし)')
            
            moat_prompt = f"""以下の情報に基づいて、この事業の持続可能な競争優位性（Moat）となりうる要素を特定し、それを表現する簡潔なステートメント案を1～3個提案してください。なぜそれが競合にとって模倣困難なのか、理由も添えてください。

            # 技術概要:
            {tech_summary}

            # Lean Canvas - 圧倒的優位性（ユーザー記述）:
            {lc_unfair_advantage if lc_unfair_advantage else "（記述なし）"}

            # SWOT分析結果:
            {swot_analysis if swot_analysis else "（SWOT分析結果なし）"}

            # 競合分析結果 (Web調査加味):
            {competitor_analysis_results_for_moat}

            # 出力形式 (マークダウン):
            ## Moat（持続可能な競争優位性）の提案
            **Moat案1:** [Moatを表すステートメント]
            * 理由: [なぜ模倣困難かの説明]
            (最大3つまで)
            """
            try:
                with st.spinner("GeminiがMoatを分析中... (ステップ4 - 4/4)"):
                     response_moat = model.generate_content(moat_prompt)
                     st.session_state.moat_ideas_text = response_moat.text
            except Exception as e:
                st.error(f"Moat生成中にエラー: {e}")
                st.session_state.moat_ideas_text = "Moatの生成に失敗"
                all_analyses_successful_step4 = False
        
        if all_analyses_successful_step4:
            st.success("ステップ4のAI分析が完了しました。")
            st.session_state.step4_analyses_complete = True # 完了フラグを立てる
        else:
            st.warning("ステップ4のAI分析中に一部エラーが発生しました。")
        st.rerun() # 表示を確定させるためにリラン

    # --- 競合分析セクション (表示と編集) ---
    with st.expander("競合分析", expanded=True):
        st.markdown("主要な競合について、製品・サービス、強み・弱みなどを分析します。")
        # 個別の生成ボタンは削除
        if 'competitor_analysis_text' in st.session_state:
            st.subheader("AIによる競合分析結果 (Web検索加味)")
            st.markdown(st.session_state.competitor_analysis_text)
            st.divider()
        else:
            st.info("競合分析結果を生成中です...") # AI処理中に表示される可能性
        st.subheader("競合分析に関する追記・考察")
        st.text_area("AIの分析結果に対する考察や、追加の競合情報などを記述してください。", height=150, key="competitor_notes_user_step4")

    # --- Moat定義セクション (表示と編集) ---
    with st.expander("優位性（Moat）の整理", expanded=True):
        st.markdown("競合分析と自社の強みを踏まえ、持続可能な競争優位性（Moat）を定義します。")
        # (関連情報の表示 - lc_unfair_advantage, swot_analysis)
        st.markdown("**関連情報（参考）:**")
        st.markdown(f"* Lean Canvas - 圧倒的優位性: {lc_unfair_advantage if lc_unfair_advantage else '（記述なし）'}")
        if swot_analysis:
             st.markdown(f"* SWOT分析（強みなど）:\n {swot_analysis}")
        st.divider()
        # 個別の生成ボタンは削除

        # AIが生成したMoat案の表示と選択UI
        if 'moat_ideas_text' in st.session_state:
            st.subheader("AIによるMoat提案（参考にしてください）")
            raw_moat_text = st.session_state.moat_ideas_text
            moat_proposals = [] # パース結果を格納するリスト
            if raw_moat_text and raw_moat_text != "Moatの生成に失敗":
                # (ここにMoat案をパースするロジック - 前回実装したもの)
                split_parts = re.split(r'(\*\*Moat案\s?\d+:\*\*)', raw_moat_text)
                current_proposal = ""
                for i_moat, part_moat in enumerate(split_parts):
                    if part_moat.startswith("**Moat案"):
                        if current_proposal: moat_proposals.append(current_proposal.strip())
                        current_proposal = part_moat
                    elif current_proposal: current_proposal += part_moat
                if current_proposal: moat_proposals.append(current_proposal.strip())
            
            if moat_proposals:
                for i, proposal_text in enumerate(moat_proposals):
                    st.checkbox(f"Moat案 {i+1} を検討候補にする", key=f"moat_select_{i}")
                    st.markdown(proposal_text)
                    st.markdown("---")
            else:
                st.markdown(raw_moat_text) # パース失敗時は生データを表示
            st.divider()
        else:
            st.info("Moat提案を生成中です...")

        # ユーザーが最終的なMoatを記述する欄
        st.subheader("最終的なMoatの定義")
        st.text_area("AIの提案やこれまでの分析を踏まえ、この事業のMoatを定義してください。", height=150, key="moat_definition_user_step4")

    st.divider()
    # --- ナビゲーション ---
    col_nav1_step4, col_nav2_step4 = st.columns(2)
    with col_nav1_step4:
        if st.button("ステップ3（深掘り）に戻る", key="back_to_step3_from_4_auto"):
            st.session_state.step = 3
            # このステップで生成した主要データをクリア
            if 'competitor_analysis_text' in st.session_state: del st.session_state.competitor_analysis_text
            if 'moat_ideas_text' in st.session_state: del st.session_state.moat_ideas_text
            if 'step4_analyses_complete' in st.session_state: del st.session_state.step4_analyses_complete
            st.rerun()
    with col_nav2_step4:
        if st.button("ステップ5（ピッチ資料生成）へ進む", key="goto_step5_from_4_auto"):
            # 選択されたAI Moat案とユーザー定義Moatを保存
            selected_ai_moats = []
            # (再度Moat案パースロジック - またはsession_stateからパース済みリストを取得)
            # (上記表示部分の moat_proposals を使うのが理想だが、スコープの問題がある場合は再パース)
            raw_moat_text_for_saving = st.session_state.get('moat_ideas_text', '')
            parsed_moat_proposals_for_saving = [] # ここで再度パース処理が必要
            if raw_moat_text_for_saving and raw_moat_text_for_saving != "Moatの生成に失敗":
                # (Moat案パースロジックをここに再記述)
                split_parts_for_saving = re.split(r'(\*\*Moat案\s?\d+:\*\*)', raw_moat_text_for_saving)
                current_proposal_for_saving = ""
                for i_save, part_save in enumerate(split_parts_for_saving):
                    if part_save.startswith("**Moat案"):
                        if current_proposal_for_saving: parsed_moat_proposals_for_saving.append(current_proposal_for_saving.strip())
                        current_proposal_for_saving = part_save
                    elif current_proposal_for_saving: current_proposal_for_saving += part_save
                if current_proposal_for_saving: parsed_moat_proposals_for_saving.append(current_proposal_for_saving.strip())

            for i, _proposal_text in enumerate(parsed_moat_proposals_for_saving): # _proposal_textは使わない
                if st.session_state.get(f"moat_select_{i}", False):
                    selected_ai_moats.append(parsed_moat_proposals_for_saving[i]) # 正しい提案テキストを追加

            if selected_ai_moats:
                st.session_state.selected_ai_moats_text_final = "\n\n".join(selected_ai_moats)
            else:
                if 'selected_ai_moats_text_final' in st.session_state: del st.session_state.selected_ai_moats_text_final
            
            st.session_state.final_moat_definition_user = st.session_state.get("moat_definition_user_step4", "")
            
            st.session_state.step = 5
            # 次のステップで自動生成するので関連データをクリア
            if 'pitch_deck_draft_text' in st.session_state: del st.session_state.pitch_deck_draft_text
            if 'step4_analyses_complete' in st.session_state: del st.session_state.step4_analyses_complete # このステップの完了フラグもクリア
            st.rerun()

# --- ステップ5: ピッチ資料自動生成 (自動実行) ---
elif st.session_state.step == 5:
    st.header("ステップ5: ピッチ資料 自動生成")
    st.caption("これまでの分析結果を統合し、ピッチ資料の骨子をAIが自動生成します。")
    st.divider()

    # --- AIによるピッチ資料骨子生成 (まだ結果がなければ自動実行) ---
    if 'pitch_deck_draft_text' not in st.session_state:
        st.info("AIがピッチ資料骨子を生成中です... これまでの全情報を集約するため、少々お時間がかかります。")

        # --- 必要な情報をsession_stateから取得 ---
        tech_summary = st.session_state.get('tech_summary', '(技術概要の情報なし)')
        selected_target = st.session_state.get('selected_target', '(ターゲット顧客の情報なし)')
        selected_problems = st.session_state.get('selected_problems', []) # 選択された課題リスト
        focused_problems_text = "\n".join([f"* {p}" for p in selected_problems]) if selected_problems else "(特に選択/記述された課題なし)"
        
        vpc_data = st.session_state.get('vpc_final_data', {}) # 編集後のVPCデータ
        vpc_text = "\n".join([f"* {key}: {value}" for key, value in vpc_data.items() if value]) if vpc_data else "(VPC情報なし)"

        # Lean Canvas (編集後の各ブロックの値を取得)
        lc_keys = ["課題", "顧客セグメント", "独自の価値提案", "解決策", "チャネル", "収益の流れ", "コスト構造", "主要指標", "圧倒的優位性"]
        lean_canvas_content = "## Lean Canvas 内容:\n"
        for key_lc in lc_keys:
            session_key_lc = f"lc_{key_lc.replace(' ', '_')}"
            lean_canvas_content += f"### {key_lc}\n{st.session_state.get(session_key_lc, '(記述なし)')}\n\n"
        
        mvp_definition = st.session_state.get('mvp_definition_user_step3', '(MVP定義なし)')
        swot_analysis = st.session_state.get('swot_analysis_text', '(SWOT分析結果なし)')
        four_p_analysis = st.session_state.get('four_p_analysis_text', '(4P分析結果なし)')
        three_c_analysis = st.session_state.get('three_c_analysis_text', '(3C分析結果なし)')
        financials_ideas = st.session_state.get('financials_ideas_text', '(財務計画初期アイデアなし)')
        competitor_analysis = st.session_state.get('competitor_analysis_text', '(競合分析結果なし)')
        
        # Moat情報 (選択されたAI案とユーザー最終定義の両方を考慮)
        selected_ai_moats = st.session_state.get('selected_ai_moats_text_final', '')
        final_user_moat = st.session_state.get('final_moat_definition_user', '') # キー名を合わせる
        
        moat_info_for_prompt = ""
        if selected_ai_moats:
            moat_info_for_prompt += f"\nAI提案Moat(ユーザー選択):\n{selected_ai_moats}"
        if final_user_moat: # ユーザー定義Moatを優先または併記
            moat_info_for_prompt += f"\n最終Moat定義(ユーザー記述):\n{final_user_moat}"
        if not moat_info_for_prompt: # どちらも無い場合
            moat_info_for_prompt = "\nMoat（持続可能な競争優位性）:\n(ステップ4で定義されていません)"

        # --- AI呼び出しロジック (ピッチ資料生成用) ---
        full_context = f"""以下は、ある技術シーズの事業化検討プロセスで整理された情報です。
        これらの情報を戦略的に統合・要約し、指定された11項目のピッチ資料構成に沿った「発表用の骨子テキスト」を作成してください。
        各項目の記述には、可能であればその根拠となった分析要素（例：SWOT分析より、市場調査より等）を括弧書きで簡潔に示唆してください。

        # 提供情報サマリー
        ## 技術概要:
        {tech_summary}

        ## ターゲット顧客:
        {selected_target}

        ## 顧客の主要な課題 (ユーザー選抜済):
        {focused_problems_text}

        ## Value Proposition Canvas:
        {vpc_text}

        ## Lean Canvas:
        {lean_canvas_content}

        ## MVP定義:
        {mvp_definition}

        ## SWOT分析:
        {swot_analysis}

        ## 4P分析:
        {four_p_analysis}

        ## 3C分析:
        {three_c_analysis}

        ## 財務計画（初期アイデア）:
        {financials_ideas}

        ## 競合分析:
        {competitor_analysis}

        ## Moat（持続可能な競争優位性）:
        {moat_info_for_prompt}

        ---
        # 作成するピッチ資料構成（11項目 - 必ずこの見出しと順番で出力）:
        ## 1. タイトル
        [ここに事業タイトル案とキャッチコピー]

        ## 2. 顧客の課題
        [ここに記述。提供情報の「顧客の主要な課題」を元に、最も重要な課題を2-3点に絞り、箇条書き3点で具体的に記述]

        ## 3. 解決策
        [ここに記述。技術概要とVPCの「製品・サービス」「ペインリリーバー」「ゲインクリエイター」を元に、課題をどう解決するかを主要なポイントを箇条書きで明確に]

        ## 4. 市場規模
        [ここに記述。Lean Canvasの市場規模に関する情報を元に、具体的な市場規模と成長性、そのデータソースの示唆を箇条書きで]

        ## 5. 競合
        [ここに記述。競合分析の結果を元に、主要な競合とその特徴を簡潔に箇条書きで]

        ## 6. 差別化ポイント・優位性（Moat含む）
        [ここに記述。Moat情報、SWOTの強み、Lean Canvasの圧倒的優位性を元に、競合に対する明確なアドバンテージを箇条書きで簡潔に説明]

        ## 7. ビジネスモデル
        [ここに記述。Lean Canvasの収益の流れとコスト構造、4Pの価格戦略を元に、主要な収益化の方法を箇条書きで簡潔に説明]

        ## 8. なぜ今か
        [ここに記述。市場トレンド、技術的進展、社会情勢などを踏まえ、今この事業を始めるべき理由を完結に説明]

        ## 9. なぜ自分（この会社）か
        [ここに記述。技術的な強み、チームの専門性（あれば）、独自リソースなどを元に、この事業を成功させられる理由を箇条書きで簡潔に説明]

        ## 10. 事業計画の骨子（3年）
        [ここに記述。MVPから始め、段階的にどのようなマイルストーン（例：ユーザー獲得、製品開発、収益化）を目指すかの概要を箇条書きで簡潔に]

        ## 11. 収支計画の概算（3年）
        [ここに記述。主要な収益源とコスト構造から、非常に大まかな収益と費用の見通し、必要な初期投資の規模感などを示唆]

        ---
        各項目の内容は、投資家や経営層に伝えることを意識し、具体的で説得力のあるものにしてください。マークダウン形式で記述してください。
        """

        try:
            with st.spinner("Geminiがピッチ資料骨子を全力で生成中..."):
                response_pitch = model.generate_content(full_context)
                st.session_state.pitch_deck_draft_text = response_pitch.text
                st.success("ピッチ資料骨子の生成が完了しました。")
                st.rerun() # 表示を更新するためにリラン
        except Exception as e:
            st.error(f"ピッチ資料骨子生成中にエラー: {e}")
            st.session_state.pitch_deck_draft_text = "ピッチ資料骨子の生成に失敗しました。"
            # st.rerun() # エラーでも一度リランしてエラーメッセージを表示させる

    # --- 生成されたピッチ資料骨子の表示 ---
    if 'pitch_deck_draft_text' in st.session_state:
        st.subheader("生成されたピッチ資料骨子（案）")
        st.markdown(st.session_state.pitch_deck_draft_text)
        # コピーボタン (簡易版)
        if st.button("骨子をクリップボードにコピー", key="copy_pitch_final"):
             st.success("コピーしました！（実際にはテキストを選択してコピーしてください）") # Streamlit単体でのクリップボードアクセスは難しい
    else:
        # API呼び出し中や、何らかの理由でまだ結果がない場合に表示
        st.info("ピッチ資料骨子を準備中です。")


    st.divider()
    # --- ナビゲーション ---
    col_nav1_step5, col_nav2_step5 = st.columns(2)
    with col_nav1_step5:
        if st.button("ステップ4（競合/Moat）に戻る", key="back_to_step4_from_5"): # キー名変更
            st.session_state.step = 4
            if 'pitch_deck_draft_text' in st.session_state: del st.session_state.pitch_deck_draft_text
            st.rerun()
    with col_nav2_step5:
        if st.button("ステップ6（VCレビュー）へ進む", key="goto_step6_from_5"): # キー名変更
            st.session_state.step = 6
            # VCレビューはステップ6で自動生成するので、ここではクリア不要
            if 'vc_review_results_text' in st.session_state:
                del st.session_state.vc_review_results_text # 前回のVCレビュー結果があればクリア
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

        以下の「ピッチ資料骨子」をVCの視点から厳しく評価し、下記の形式で箇条書きで簡潔にフィードバックを出力してください。

        # 評価対象ピッチ資料骨子:
        ---
        {pitch_draft}
        ---

        # 出力形式:
        1.  **事業評価スコア（10点満点）:**
            * ビジネスとしての魅力度、ピッチ内容の完成度を総合的に10点満点で評価し、その主な根拠を箇条書きで簡潔に述べてください。
        2.  **課題リスト:**
            * このピッチ内容や事業計画における、特に問題となる点、リスク、さらなる深掘りや改善が必要な点を「課題」として具体的にリストアップしてください。各課題について、なぜそれが問題なのかをVC視点で箇条書きで簡潔に説明してください。
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