#!/usr/bin/env python3
"""Add missing i18n keys (crawl.*, crossref.*, reg_upload.*) to all locale files."""

import json
import os
import sys

BASE = os.path.join(os.path.dirname(__file__), "..", "src", "chainlit_app", "locales")

# English reference values
EN = {
    "crawl.incomplete_title": "⚠️ **Regulatory Data Incomplete**\n",
    "crawl.incomplete_regions": "The following regions' regulatory data could not be fully retrieved online:\n",
    "crawl.upload_prompt": "\nPlease upload complete regulatory documents to ensure cross-reference accuracy.",
    "crawl.upload_btn": "📤 Upload Regulatory Document",
    "crawl.incomplete_fallback": "⚠️ Regulatory data incomplete. Please upload complete regulatory documents.",
    "crossref.feedback_msg": "---\n📝 **Cross-Reference Feedback**\n\n{name}, above are the 3-Country × ISO 13485 cross-reference results. If you believe any mapping needs correction, please enter your feedback below.\n\n**Feedback Examples:**\n- 'ISO 7.3.4 Taiwan mapping should be Medical Devices Act Article 23'\n- 'EU MDR ISO 4.2.4 mapping status should be partial, not full'\n- 'QMSR ISO 8.2.3 is missing the 21 CFR 820.198 reference'\n- 'Taiwan ISO 7.5.1 unique requirement should add GMP Article 17 production control'\n\nIf no corrections are needed, click the button below.",
    "crossref.confirm_no_change": "✅ Confirm No Changes Needed",
    "crossref.confirmed": "✅ Cross-reference results confirmed.",
    "crossref.analyzing_feedback": "🔄 Analyzing your cross-reference correction feedback...",
    "crossref.no_llm": "⚠️ LLM not configured. Please set up an LLM provider and model in settings first.",
    "crossref.llm_failed": "⚠️ LLM analysis failed: {error}",
    "crossref.parse_failed": "⚠️ Unable to parse LLM response. Please try describing your correction more clearly.",
    "crossref.no_corrections": "ℹ️ No specific corrections detected. Please refer to the examples and try again.",
    "crossref.reg_not_found": "Regulation {reg_id} not found",
    "crossref.clause_not_found": "ISO clause {iso_clause} not found",
    "crossref.unsupported_field": "Unsupported field {field_name}",
    "crossref.correction_title": "📋 **Cross-Reference Correction Results**\n",
    "crossref.applied_count": "✅ Applied {count} correction(s):",
    "crossref.failed_count": "\n❌ {count} correction(s) could not be applied:",
    "reg_upload.read_failed": "❌ Unable to read file: {file_name}",
    "reg_upload.reading": "🔄 Reading **{file_name}** ...",
    "reg_upload.read_error": "❌ File read failed: {error}",
    "reg_upload.too_short": "❌ File content too short or cannot be parsed: **{file_name}**",
    "reg_upload.not_regulatory": "❌ This file does not appear to be a regulatory document: **{file_name}**\n\nOnly ISO 13485, medical device regulations, and quality management documents are accepted.\nDetected keywords: {keywords}",
    "reg_upload.summary": "{name}, 📋 **Parse Summary**\n\n- File name: **{file_name}**\n- File size: {file_size}\n- Characters extracted: {char_count}\n- Detection: ✅ Quality regulatory document\n- Related keywords: {keywords}\n\n**Content Preview:**\n> {preview}...\n\nProceed with full analysis? LLM will analyze clauses and update the regulatory mapping table.",
    "reg_upload.confirm_btn": "✅ Confirm Parse",
    "reg_upload.cancel_btn": "❌ Cancel",
    "reg_upload.ask_upload": "{name}, 📤 **Please upload complete regulatory documents**\n\nSupported formats: PDF, Word (.docx), TXT, HTML, Markdown (.md)\nYou may upload up to 5 files at once.",
    "reg_upload.upload_cancelled": "⏭️ Upload cancelled.",
    "reg_upload.no_pending": "⚠️ No pending regulatory document found.",
    "reg_upload.llm_parsing": "🔄 Using LLM to analyze **{file_name}** ...\n\nThis may take 1-3 minutes.",
    "reg_upload.parse_success": "✅ **Regulatory Document Parsed**\n\n- Regulation ID: `{reg_id}`\n- Name: {name_zh} ({name_en})\n- Country: {country}\n- ISO 13485 mapped clauses: {mapped_count}\n- Country-specific requirements: {unique_count}\n- Saved to: `{filepath}`\n\nMapping table updated. Next cross-reference will include this regulation.",
    "reg_upload.parse_failed": "❌ LLM parsing failed. Could not extract regulatory structure from the document.\nPlease verify the document content is complete and regulatory in nature.",
    "reg_upload.parse_error": "❌ Error during parsing: {error}",
    "reg_upload.parse_cancelled": "✅ Regulatory document parsing cancelled.",
}

# Per-language translations
TRANSLATIONS = {}

TRANSLATIONS["zh-CN"] = {
    "crawl.incomplete_title": "⚠️ **法规数据抓取不完整**\n",
    "crawl.incomplete_regions": "以下国家/地区的法规数据无法从网络获取完整版本：\n",
    "crawl.upload_prompt": "\n请上传完整版法规文件以确保交叉比对准确度。",
    "crawl.upload_btn": "📤 上传法规文件",
    "crawl.incomplete_fallback": "⚠️ 法规数据抓取不完整，请上传完整版法规文件。",
    "crossref.feedback_msg": "---\n📝 **交叉比对反馈**\n\n{name}，以上是三国 × ISO 13485 交叉比对结果。如果您认为任何映射需要修正，请直接在下方输入您的意见。\n\n**反馈使用范例：**\n- 「ISO 7.3.4 的台湾法规映射应该是医疗器材管理法第23条」\n- 「EU MDR 的 ISO 4.2.4 映射状态应为部分对应，而非完全对应」\n- 「QMSR 的 ISO 8.2.3 缺少对应的 21 CFR 820.198 引用」\n- 「台湾的 ISO 7.5.1 独有需求应新增 GMP 第17条的生产管制要求」\n\n如果确认无需修改，请点击下方按钮。",
    "crossref.confirm_no_change": "✅ 确认无需修改",
    "crossref.confirmed": "✅ 交叉比对结果已确认。",
    "crossref.analyzing_feedback": "🔄 正在分析您的交叉比对修正意见...",
    "crossref.no_llm": "⚠️ 尚未设定 LLM，无法分析反馈。请先在设定中配置 LLM 提供商和模型。",
    "crossref.llm_failed": "⚠️ LLM 分析失败：{error}",
    "crossref.parse_failed": "⚠️ 无法解析 LLM 回应。请尝试更明确地描述您的修正意见。",
    "crossref.no_corrections": "ℹ️ 未检测到具体的修正项目。请参考范例格式重新输入。",
    "crossref.reg_not_found": "找不到法规 {reg_id}",
    "crossref.clause_not_found": "找不到 ISO 条款 {iso_clause}",
    "crossref.unsupported_field": "不支持的字段 {field_name}",
    "crossref.correction_title": "📋 **交叉比对修正结果**\n",
    "crossref.applied_count": "✅ 已应用 {count} 项修正：",
    "crossref.failed_count": "\n❌ {count} 项无法应用：",
    "reg_upload.read_failed": "❌ 无法读取文件：{file_name}",
    "reg_upload.reading": "🔄 正在读取 **{file_name}** ...",
    "reg_upload.read_error": "❌ 文件读取失败：{error}",
    "reg_upload.too_short": "❌ 文件内容太少或无法解析：**{file_name}**",
    "reg_upload.not_regulatory": "❌ 此文件似乎不是品质法规相关文件：**{file_name}**\n\n仅接受 ISO 13485、各国医疗器材法规等品质管理相关文件。\n检测到的关键字: {keywords}",
    "reg_upload.summary": "{name}，📋 **解析概况**\n\n- 文件名称：**{file_name}**\n- 文件大小：{file_size}\n- 提取字符数：{char_count} 字\n- 检测结果：✅ 品质法规文件\n- 相关关键字：{keywords}\n\n**内容预览：**\n> {preview}...\n\n确认要进行完整解析吗？解析后将使用 LLM 分析条文并更新法规映射表。",
    "reg_upload.confirm_btn": "✅ 确认解析",
    "reg_upload.cancel_btn": "❌ 取消",
    "reg_upload.ask_upload": "{name}，📤 **请上传完整版法规文件**\n\n支持格式：PDF、Word (.docx)、TXT、HTML、Markdown (.md)\n您可以同时上传多个文件（最多 5 个）。",
    "reg_upload.upload_cancelled": "⏭️ 已取消上传。",
    "reg_upload.no_pending": "⚠️ 找不到待解析的法规文件。",
    "reg_upload.llm_parsing": "🔄 正在使用 LLM 解析 **{file_name}** ...\n\n这可能需要 1-3 分钟。",
    "reg_upload.parse_success": "✅ **法规文件解析完成**\n\n- 法规ID: `{reg_id}`\n- 名称: {name_zh} ({name_en})\n- 国家: {country}\n- ISO 13485 映射条款数: {mapped_count}\n- 国家独有要求数: {unique_count}\n- 已保存至: `{filepath}`\n\n法规映射表已更新，下次交叉比对将包含此法规。",
    "reg_upload.parse_failed": "❌ LLM 解析失败，无法从文件中提取法规结构。\n请确认文件内容完整且为品质法规相关文件。",
    "reg_upload.parse_error": "❌ 解析过程中发生错误：{error}",
    "reg_upload.parse_cancelled": "✅ 已取消法规文件解析。",
}

TRANSLATIONS["ja-JP"] = {
    "crawl.incomplete_title": "⚠️ **法規データの取得が不完全です**\n",
    "crawl.incomplete_regions": "以下の国・地域の法規データをオンラインで完全に取得できませんでした：\n",
    "crawl.upload_prompt": "\n交差参照の正確性を確保するため、完全な法規文書をアップロードしてください。",
    "crawl.upload_btn": "📤 法規文書をアップロード",
    "crawl.incomplete_fallback": "⚠️ 法規データが不完全です。完全な法規文書をアップロードしてください。",
    "crossref.feedback_msg": "---\n📝 **交差参照フィードバック**\n\n{name}、上記は3カ国 × ISO 13485 の交差参照結果です。マッピングに修正が必要と思われる場合は、以下にフィードバックを入力してください。\n\n**フィードバック例：**\n- 「ISO 7.3.4 の台湾法規マッピングは医療機器管理法第23条であるべき」\n- 「EU MDR の ISO 4.2.4 マッピング状態は完全ではなく部分対応であるべき」\n- 「QMSR の ISO 8.2.3 に 21 CFR 820.198 の参照が欠けている」\n- 「台湾の ISO 7.5.1 固有要件に GMP 第17条の生産管理要件を追加すべき」\n\n修正が不要な場合は、下のボタンをクリックしてください。",
    "crossref.confirm_no_change": "✅ 修正不要を確認",
    "crossref.confirmed": "✅ 交差参照結果を確認しました。",
    "crossref.analyzing_feedback": "🔄 交差参照の修正フィードバックを分析中...",
    "crossref.no_llm": "⚠️ LLM が設定されていません。まず設定で LLM プロバイダーとモデルを設定してください。",
    "crossref.llm_failed": "⚠️ LLM 分析に失敗しました：{error}",
    "crossref.parse_failed": "⚠️ LLM の応答を解析できません。修正内容をより明確に記述してください。",
    "crossref.no_corrections": "ℹ️ 具体的な修正項目が検出されませんでした。例を参考にして再入力してください。",
    "crossref.reg_not_found": "法規 {reg_id} が見つかりません",
    "crossref.clause_not_found": "ISO 条項 {iso_clause} が見つかりません",
    "crossref.unsupported_field": "サポートされていないフィールド {field_name}",
    "crossref.correction_title": "📋 **交差参照修正結果**\n",
    "crossref.applied_count": "✅ {count} 件の修正を適用しました：",
    "crossref.failed_count": "\n❌ {count} 件の修正を適用できませんでした：",
    "reg_upload.read_failed": "❌ ファイルを読み取れません：{file_name}",
    "reg_upload.reading": "🔄 **{file_name}** を読み取り中...",
    "reg_upload.read_error": "❌ ファイル読み取り失敗：{error}",
    "reg_upload.too_short": "❌ ファイルの内容が少なすぎるか解析できません：**{file_name}**",
    "reg_upload.not_regulatory": "❌ このファイルは品質法規関連文書ではないようです：**{file_name}**\n\nISO 13485、各国医療機器法規などの品質管理関連文書のみ受け付けます。\n検出されたキーワード: {keywords}",
    "reg_upload.summary": "{name}、📋 **解析概要**\n\n- ファイル名：**{file_name}**\n- ファイルサイズ：{file_size}\n- 抽出文字数：{char_count} 文字\n- 検出結果：✅ 品質法規文書\n- 関連キーワード：{keywords}\n\n**内容プレビュー：**\n> {preview}...\n\n完全な解析を実行しますか？LLM が条文を分析し、法規マッピングテーブルを更新します。",
    "reg_upload.confirm_btn": "✅ 解析を確認",
    "reg_upload.cancel_btn": "❌ キャンセル",
    "reg_upload.ask_upload": "{name}、📤 **完全な法規文書をアップロードしてください**\n\n対応形式：PDF、Word (.docx)、TXT、HTML、Markdown (.md)\n最大5ファイルまで同時アップロード可能です。",
    "reg_upload.upload_cancelled": "⏭️ アップロードをキャンセルしました。",
    "reg_upload.no_pending": "⚠️ 解析待ちの法規文書が見つかりません。",
    "reg_upload.llm_parsing": "🔄 LLM で **{file_name}** を解析中...\n\n1〜3分かかる場合があります。",
    "reg_upload.parse_success": "✅ **法規文書の解析完了**\n\n- 法規ID: `{reg_id}`\n- 名称: {name_zh} ({name_en})\n- 国: {country}\n- ISO 13485 マッピング条項数: {mapped_count}\n- 国固有の要件数: {unique_count}\n- 保存先: `{filepath}`\n\nマッピングテーブルが更新されました。次回の交差参照にこの法規が含まれます。",
    "reg_upload.parse_failed": "❌ LLM 解析に失敗しました。文書から法規構造を抽出できません。\n文書の内容が完全で品質法規関連であることを確認してください。",
    "reg_upload.parse_error": "❌ 解析中にエラーが発生しました：{error}",
    "reg_upload.parse_cancelled": "✅ 法規文書の解析をキャンセルしました。",
}

TRANSLATIONS["ko-KR"] = {
    "crawl.incomplete_title": "⚠️ **규정 데이터 수집 불완전**\n",
    "crawl.incomplete_regions": "다음 국가/지역의 규정 데이터를 온라인에서 완전히 가져올 수 없었습니다:\n",
    "crawl.upload_prompt": "\n교차 참조의 정확성을 보장하기 위해 완전한 규정 문서를 업로드해 주세요.",
    "crawl.upload_btn": "📤 규정 문서 업로드",
    "crawl.incomplete_fallback": "⚠️ 규정 데이터가 불완전합니다. 완전한 규정 문서를 업로드해 주세요.",
    "crossref.feedback_msg": '---\n📝 **교차 참조 피드백**\n\n{name}, 위는 3개국 × ISO 13485 교차 참조 결과입니다. 매핑에 수정이 필요하다고 생각되시면 아래에 피드백을 입력해 주세요.\n\n**피드백 예시:**\n- "ISO 7.3.4의 대만 규정 매핑은 의료기기관리법 제23조여야 합니다"\n- "EU MDR의 ISO 4.2.4 매핑 상태는 완전이 아닌 부분 대응이어야 합니다"\n- "QMSR의 ISO 8.2.3에 21 CFR 820.198 참조가 누락되어 있습니다"\n- "대만의 ISO 7.5.1 고유 요구사항에 GMP 제17조 생산 관리 요구사항을 추가해야 합니다"\n\n수정이 필요 없으면 아래 버튼을 클릭해 주세요.',
    "crossref.confirm_no_change": "✅ 수정 불필요 확인",
    "crossref.confirmed": "✅ 교차 참조 결과가 확인되었습니다.",
    "crossref.analyzing_feedback": "🔄 교차 참조 수정 피드백을 분석 중...",
    "crossref.no_llm": "⚠️ LLM이 설정되지 않았습니다. 먼저 설정에서 LLM 제공자와 모델을 구성해 주세요.",
    "crossref.llm_failed": "⚠️ LLM 분석 실패: {error}",
    "crossref.parse_failed": "⚠️ LLM 응답을 구문 분석할 수 없습니다. 수정 내용을 더 명확하게 설명해 주세요.",
    "crossref.no_corrections": "ℹ️ 구체적인 수정 항목이 감지되지 않았습니다. 예시를 참고하여 다시 입력해 주세요.",
    "crossref.reg_not_found": "규정 {reg_id}을(를) 찾을 수 없습니다",
    "crossref.clause_not_found": "ISO 조항 {iso_clause}을(를) 찾을 수 없습니다",
    "crossref.unsupported_field": "지원되지 않는 필드 {field_name}",
    "crossref.correction_title": "📋 **교차 참조 수정 결과**\n",
    "crossref.applied_count": "✅ {count}건의 수정이 적용되었습니다:",
    "crossref.failed_count": "\n❌ {count}건의 수정을 적용할 수 없습니다:",
    "reg_upload.read_failed": "❌ 파일을 읽을 수 없습니다: {file_name}",
    "reg_upload.reading": "🔄 **{file_name}** 읽는 중...",
    "reg_upload.read_error": "❌ 파일 읽기 실패: {error}",
    "reg_upload.too_short": "❌ 파일 내용이 너무 적거나 구문 분석할 수 없습니다: **{file_name}**",
    "reg_upload.not_regulatory": "❌ 이 파일은 품질 규정 관련 문서가 아닌 것 같습니다: **{file_name}**\n\nISO 13485, 각국 의료기기 규정 등 품질 관리 관련 문서만 허용됩니다.\n감지된 키워드: {keywords}",
    "reg_upload.summary": "{name}, 📋 **분석 개요**\n\n- 파일 이름: **{file_name}**\n- 파일 크기: {file_size}\n- 추출 문자 수: {char_count}자\n- 감지 결과: ✅ 품질 규정 문서\n- 관련 키워드: {keywords}\n\n**내용 미리보기:**\n> {preview}...\n\n전체 분석을 진행하시겠습니까? LLM이 조문을 분석하고 규정 매핑 테이블을 업데이트합니다.",
    "reg_upload.confirm_btn": "✅ 분석 확인",
    "reg_upload.cancel_btn": "❌ 취소",
    "reg_upload.ask_upload": "{name}, 📤 **완전한 규정 문서를 업로드해 주세요**\n\n지원 형식: PDF, Word (.docx), TXT, HTML, Markdown (.md)\n최대 5개 파일을 동시에 업로드할 수 있습니다.",
    "reg_upload.upload_cancelled": "⏭️ 업로드가 취소되었습니다.",
    "reg_upload.no_pending": "⚠️ 분석 대기 중인 규정 문서를 찾을 수 없습니다.",
    "reg_upload.llm_parsing": "🔄 LLM으로 **{file_name}**을(를) 분석 중...\n\n1~3분 정도 소요될 수 있습니다.",
    "reg_upload.parse_success": "✅ **규정 문서 분석 완료**\n\n- 규정 ID: `{reg_id}`\n- 이름: {name_zh} ({name_en})\n- 국가: {country}\n- ISO 13485 매핑 조항 수: {mapped_count}\n- 국가 고유 요구사항 수: {unique_count}\n- 저장 위치: `{filepath}`\n\n매핑 테이블이 업데이트되었습니다. 다음 교차 참조에 이 규정이 포함됩니다.",
    "reg_upload.parse_failed": "❌ LLM 분석 실패. 문서에서 규정 구조를 추출할 수 없습니다.\n문서 내용이 완전하고 품질 규정 관련인지 확인해 주세요.",
    "reg_upload.parse_error": "❌ 분석 중 오류 발생: {error}",
    "reg_upload.parse_cancelled": "✅ 규정 문서 분석이 취소되었습니다.",
}

TRANSLATIONS["de-DE"] = {
    "crawl.incomplete_title": "⚠️ **Regulierungsdaten unvollständig**\n",
    "crawl.incomplete_regions": "Die Regulierungsdaten der folgenden Regionen konnten nicht vollständig online abgerufen werden:\n",
    "crawl.upload_prompt": "\nBitte laden Sie vollständige Regulierungsdokumente hoch, um die Genauigkeit der Querverweise sicherzustellen.",
    "crawl.upload_btn": "📤 Regulierungsdokument hochladen",
    "crawl.incomplete_fallback": "⚠️ Regulierungsdaten unvollständig. Bitte laden Sie vollständige Regulierungsdokumente hoch.",
    "crossref.feedback_msg": '---\n📝 **Querverweis-Feedback**\n\n{name}, oben sind die 3-Länder × ISO 13485 Querverweis-Ergebnisse. Wenn Sie der Meinung sind, dass eine Zuordnung korrigiert werden muss, geben Sie bitte Ihr Feedback unten ein.\n\n**Feedback-Beispiele:**\n- "ISO 7.3.4 Taiwan-Zuordnung sollte Medizinproduktegesetz Artikel 23 sein"\n- "EU MDR ISO 4.2.4 Zuordnungsstatus sollte teilweise sein, nicht vollständig"\n- "QMSR ISO 8.2.3 fehlt die 21 CFR 820.198 Referenz"\n- "Taiwan ISO 7.5.1 spezifische Anforderung sollte GMP Artikel 17 Produktionskontrolle hinzufügen"\n\nWenn keine Korrekturen erforderlich sind, klicken Sie auf die Schaltfläche unten.',
    "crossref.confirm_no_change": "✅ Keine Änderungen erforderlich bestätigen",
    "crossref.confirmed": "✅ Querverweis-Ergebnisse bestätigt.",
    "crossref.analyzing_feedback": "🔄 Analyse Ihres Querverweis-Korrektur-Feedbacks...",
    "crossref.no_llm": "⚠️ LLM nicht konfiguriert. Bitte richten Sie zuerst einen LLM-Anbieter und ein Modell in den Einstellungen ein.",
    "crossref.llm_failed": "⚠️ LLM-Analyse fehlgeschlagen: {error}",
    "crossref.parse_failed": "⚠️ LLM-Antwort konnte nicht analysiert werden. Bitte beschreiben Sie Ihre Korrektur deutlicher.",
    "crossref.no_corrections": "ℹ️ Keine spezifischen Korrekturen erkannt. Bitte beziehen Sie sich auf die Beispiele und versuchen Sie es erneut.",
    "crossref.reg_not_found": "Regulierung {reg_id} nicht gefunden",
    "crossref.clause_not_found": "ISO-Klausel {iso_clause} nicht gefunden",
    "crossref.unsupported_field": "Nicht unterstütztes Feld {field_name}",
    "crossref.correction_title": "📋 **Querverweis-Korrekturergebnisse**\n",
    "crossref.applied_count": "✅ {count} Korrektur(en) angewendet:",
    "crossref.failed_count": "\n❌ {count} Korrektur(en) konnten nicht angewendet werden:",
    "reg_upload.read_failed": "❌ Datei kann nicht gelesen werden: {file_name}",
    "reg_upload.reading": "🔄 **{file_name}** wird gelesen...",
    "reg_upload.read_error": "❌ Datei lesen fehlgeschlagen: {error}",
    "reg_upload.too_short": "❌ Dateiinhalt zu kurz oder kann nicht analysiert werden: **{file_name}**",
    "reg_upload.not_regulatory": "❌ Diese Datei scheint kein Regulierungsdokument zu sein: **{file_name}**\n\nNur ISO 13485, Medizinproduktevorschriften und Qualitätsmanagement-Dokumente werden akzeptiert.\nErkannte Schlüsselwörter: {keywords}",
    "reg_upload.summary": "{name}, 📋 **Analyse-Zusammenfassung**\n\n- Dateiname: **{file_name}**\n- Dateigröße: {file_size}\n- Extrahierte Zeichen: {char_count}\n- Erkennung: ✅ Qualitätsregulierungsdokument\n- Verwandte Schlüsselwörter: {keywords}\n\n**Inhaltsvorschau:**\n> {preview}...\n\nMit vollständiger Analyse fortfahren? LLM wird Klauseln analysieren und die regulatorische Zuordnungstabelle aktualisieren.",
    "reg_upload.confirm_btn": "✅ Analyse bestätigen",
    "reg_upload.cancel_btn": "❌ Abbrechen",
    "reg_upload.ask_upload": "{name}, 📤 **Bitte laden Sie vollständige Regulierungsdokumente hoch**\n\nUnterstützte Formate: PDF, Word (.docx), TXT, HTML, Markdown (.md)\nSie können bis zu 5 Dateien gleichzeitig hochladen.",
    "reg_upload.upload_cancelled": "⏭️ Upload abgebrochen.",
    "reg_upload.no_pending": "⚠️ Kein ausstehendes Regulierungsdokument gefunden.",
    "reg_upload.llm_parsing": "🔄 LLM analysiert **{file_name}**...\n\nDies kann 1-3 Minuten dauern.",
    "reg_upload.parse_success": "✅ **Regulierungsdokument analysiert**\n\n- Regulierungs-ID: `{reg_id}`\n- Name: {name_zh} ({name_en})\n- Land: {country}\n- ISO 13485 zugeordnete Klauseln: {mapped_count}\n- Länderspezifische Anforderungen: {unique_count}\n- Gespeichert in: `{filepath}`\n\nZuordnungstabelle aktualisiert. Der nächste Querverweis wird diese Regulierung einschließen.",
    "reg_upload.parse_failed": "❌ LLM-Analyse fehlgeschlagen. Regulierungsstruktur konnte nicht aus dem Dokument extrahiert werden.\nBitte überprüfen Sie, ob der Dokumentinhalt vollständig und regulatorischer Natur ist.",
    "reg_upload.parse_error": "❌ Fehler bei der Analyse: {error}",
    "reg_upload.parse_cancelled": "✅ Analyse des Regulierungsdokuments abgebrochen.",
}

TRANSLATIONS["es-ES"] = {
    "crawl.incomplete_title": "⚠️ **Datos regulatorios incompletos**\n",
    "crawl.incomplete_regions": "Los datos regulatorios de las siguientes regiones no pudieron obtenerse completamente en línea:\n",
    "crawl.upload_prompt": "\nPor favor, suba los documentos regulatorios completos para garantizar la precisión de las referencias cruzadas.",
    "crawl.upload_btn": "📤 Subir documento regulatorio",
    "crawl.incomplete_fallback": "⚠️ Datos regulatorios incompletos. Por favor, suba los documentos regulatorios completos.",
    "crossref.feedback_msg": '---\n📝 **Comentarios sobre referencias cruzadas**\n\n{name}, arriba están los resultados de referencias cruzadas de 3 países × ISO 13485. Si cree que algún mapeo necesita corrección, ingrese sus comentarios a continuación.\n\n**Ejemplos de comentarios:**\n- "El mapeo de Taiwán ISO 7.3.4 debería ser Ley de Dispositivos Médicos Artículo 23"\n- "El estado de mapeo ISO 4.2.4 de EU MDR debería ser parcial, no completo"\n- "Al QMSR ISO 8.2.3 le falta la referencia 21 CFR 820.198"\n- "El requisito único de Taiwán ISO 7.5.1 debería agregar control de producción GMP Artículo 17"\n\nSi no se necesitan correcciones, haga clic en el botón de abajo.',
    "crossref.confirm_no_change": "✅ Confirmar que no se necesitan cambios",
    "crossref.confirmed": "✅ Resultados de referencias cruzadas confirmados.",
    "crossref.analyzing_feedback": "🔄 Analizando sus comentarios de corrección de referencias cruzadas...",
    "crossref.no_llm": "⚠️ LLM no configurado. Configure primero un proveedor LLM y un modelo en la configuración.",
    "crossref.llm_failed": "⚠️ Análisis LLM fallido: {error}",
    "crossref.parse_failed": "⚠️ No se pudo analizar la respuesta del LLM. Intente describir su corrección más claramente.",
    "crossref.no_corrections": "ℹ️ No se detectaron correcciones específicas. Consulte los ejemplos e intente de nuevo.",
    "crossref.reg_not_found": "Regulación {reg_id} no encontrada",
    "crossref.clause_not_found": "Cláusula ISO {iso_clause} no encontrada",
    "crossref.unsupported_field": "Campo no soportado {field_name}",
    "crossref.correction_title": "📋 **Resultados de corrección de referencias cruzadas**\n",
    "crossref.applied_count": "✅ {count} corrección(es) aplicada(s):",
    "crossref.failed_count": "\n❌ {count} corrección(es) no pudo(ieron) aplicarse:",
    "reg_upload.read_failed": "❌ No se puede leer el archivo: {file_name}",
    "reg_upload.reading": "🔄 Leyendo **{file_name}** ...",
    "reg_upload.read_error": "❌ Error al leer el archivo: {error}",
    "reg_upload.too_short": "❌ Contenido del archivo demasiado corto o no se puede analizar: **{file_name}**",
    "reg_upload.not_regulatory": "❌ Este archivo no parece ser un documento regulatorio: **{file_name}**\n\nSolo se aceptan documentos ISO 13485, regulaciones de dispositivos médicos y gestión de calidad.\nPalabras clave detectadas: {keywords}",
    "reg_upload.summary": "{name}, 📋 **Resumen del análisis**\n\n- Nombre del archivo: **{file_name}**\n- Tamaño del archivo: {file_size}\n- Caracteres extraídos: {char_count}\n- Detección: ✅ Documento regulatorio de calidad\n- Palabras clave relacionadas: {keywords}\n\n**Vista previa del contenido:**\n> {preview}...\n\n¿Proceder con el análisis completo? El LLM analizará las cláusulas y actualizará la tabla de mapeo regulatorio.",
    "reg_upload.confirm_btn": "✅ Confirmar análisis",
    "reg_upload.cancel_btn": "❌ Cancelar",
    "reg_upload.ask_upload": "{name}, 📤 **Por favor, suba los documentos regulatorios completos**\n\nFormatos soportados: PDF, Word (.docx), TXT, HTML, Markdown (.md)\nPuede subir hasta 5 archivos a la vez.",
    "reg_upload.upload_cancelled": "⏭️ Carga cancelada.",
    "reg_upload.no_pending": "⚠️ No se encontró documento regulatorio pendiente.",
    "reg_upload.llm_parsing": "🔄 Usando LLM para analizar **{file_name}** ...\n\nEsto puede tardar de 1 a 3 minutos.",
    "reg_upload.parse_success": "✅ **Documento regulatorio analizado**\n\n- ID de regulación: `{reg_id}`\n- Nombre: {name_zh} ({name_en})\n- País: {country}\n- Cláusulas mapeadas ISO 13485: {mapped_count}\n- Requisitos específicos del país: {unique_count}\n- Guardado en: `{filepath}`\n\nTabla de mapeo actualizada. La próxima referencia cruzada incluirá esta regulación.",
    "reg_upload.parse_failed": "❌ Análisis LLM fallido. No se pudo extraer la estructura regulatoria del documento.\nVerifique que el contenido del documento sea completo y de naturaleza regulatoria.",
    "reg_upload.parse_error": "❌ Error durante el análisis: {error}",
    "reg_upload.parse_cancelled": "✅ Análisis del documento regulatorio cancelado.",
}

TRANSLATIONS["fr-FR"] = {
    "crawl.incomplete_title": "⚠️ **Données réglementaires incomplètes**\n",
    "crawl.incomplete_regions": "Les données réglementaires des régions suivantes n'ont pas pu être entièrement récupérées en ligne :\n",
    "crawl.upload_prompt": "\nVeuillez télécharger les documents réglementaires complets pour garantir la précision des références croisées.",
    "crawl.upload_btn": "📤 Télécharger un document réglementaire",
    "crawl.incomplete_fallback": "⚠️ Données réglementaires incomplètes. Veuillez télécharger les documents réglementaires complets.",
    "crossref.feedback_msg": '---\n📝 **Retour sur les références croisées**\n\n{name}, ci-dessus se trouvent les résultats de références croisées 3 pays × ISO 13485. Si vous pensez qu\'un mappage nécessite une correction, veuillez saisir votre retour ci-dessous.\n\n**Exemples de retour :**\n- "Le mappage Taiwan de l\'ISO 7.3.4 devrait être la Loi sur les dispositifs médicaux Article 23"\n- "Le statut de mappage ISO 4.2.4 de l\'EU MDR devrait être partiel, pas complet"\n- "L\'ISO 8.2.3 du QMSR manque la référence 21 CFR 820.198"\n- "L\'exigence unique Taiwan ISO 7.5.1 devrait ajouter le contrôle de production GMP Article 17"\n\nSi aucune correction n\'est nécessaire, cliquez sur le bouton ci-dessous.',
    "crossref.confirm_no_change": "✅ Confirmer aucune modification nécessaire",
    "crossref.confirmed": "✅ Résultats des références croisées confirmés.",
    "crossref.analyzing_feedback": "🔄 Analyse de votre retour de correction des références croisées...",
    "crossref.no_llm": "⚠️ LLM non configuré. Veuillez d'abord configurer un fournisseur LLM et un modèle dans les paramètres.",
    "crossref.llm_failed": "⚠️ Échec de l'analyse LLM : {error}",
    "crossref.parse_failed": "⚠️ Impossible d'analyser la réponse LLM. Veuillez décrire votre correction plus clairement.",
    "crossref.no_corrections": "ℹ️ Aucune correction spécifique détectée. Veuillez vous référer aux exemples et réessayer.",
    "crossref.reg_not_found": "Réglementation {reg_id} introuvable",
    "crossref.clause_not_found": "Clause ISO {iso_clause} introuvable",
    "crossref.unsupported_field": "Champ non pris en charge {field_name}",
    "crossref.correction_title": "📋 **Résultats de correction des références croisées**\n",
    "crossref.applied_count": "✅ {count} correction(s) appliquée(s) :",
    "crossref.failed_count": "\n❌ {count} correction(s) n'a/ont pas pu être appliquée(s) :",
    "reg_upload.read_failed": "❌ Impossible de lire le fichier : {file_name}",
    "reg_upload.reading": "🔄 Lecture de **{file_name}** ...",
    "reg_upload.read_error": "❌ Échec de la lecture du fichier : {error}",
    "reg_upload.too_short": "❌ Contenu du fichier trop court ou impossible à analyser : **{file_name}**",
    "reg_upload.not_regulatory": "❌ Ce fichier ne semble pas être un document réglementaire : **{file_name}**\n\nSeuls les documents ISO 13485, réglementations des dispositifs médicaux et gestion de la qualité sont acceptés.\nMots-clés détectés : {keywords}",
    "reg_upload.summary": "{name}, 📋 **Résumé de l'analyse**\n\n- Nom du fichier : **{file_name}**\n- Taille du fichier : {file_size}\n- Caractères extraits : {char_count}\n- Détection : ✅ Document réglementaire qualité\n- Mots-clés associés : {keywords}\n\n**Aperçu du contenu :**\n> {preview}...\n\nProcéder à l'analyse complète ? Le LLM analysera les clauses et mettra à jour la table de mappage réglementaire.",
    "reg_upload.confirm_btn": "✅ Confirmer l'analyse",
    "reg_upload.cancel_btn": "❌ Annuler",
    "reg_upload.ask_upload": "{name}, 📤 **Veuillez télécharger les documents réglementaires complets**\n\nFormats supportés : PDF, Word (.docx), TXT, HTML, Markdown (.md)\nVous pouvez télécharger jusqu'à 5 fichiers simultanément.",
    "reg_upload.upload_cancelled": "⏭️ Téléchargement annulé.",
    "reg_upload.no_pending": "⚠️ Aucun document réglementaire en attente trouvé.",
    "reg_upload.llm_parsing": "🔄 Analyse de **{file_name}** par LLM en cours...\n\nCela peut prendre 1 à 3 minutes.",
    "reg_upload.parse_success": "✅ **Document réglementaire analysé**\n\n- ID réglementation : `{reg_id}`\n- Nom : {name_zh} ({name_en})\n- Pays : {country}\n- Clauses mappées ISO 13485 : {mapped_count}\n- Exigences spécifiques au pays : {unique_count}\n- Enregistré dans : `{filepath}`\n\nTable de mappage mise à jour. La prochaine référence croisée inclura cette réglementation.",
    "reg_upload.parse_failed": "❌ Échec de l'analyse LLM. Impossible d'extraire la structure réglementaire du document.\nVeuillez vérifier que le contenu du document est complet et de nature réglementaire.",
    "reg_upload.parse_error": "❌ Erreur lors de l'analyse : {error}",
    "reg_upload.parse_cancelled": "✅ Analyse du document réglementaire annulée.",
}

# For the remaining 14 locales, use English values. The t() function falls back to zh-TW anyway,
# and having keys present (even in English) is better than missing keys for the key completeness test.
remaining_locales = [
    "vi-VN",
    "th-TH",
    "hi-IN",
    "ms-MY",
    "id-ID",
    "ar-SA",
    "it-IT",
    "pt-BR",
    "nl-NL",
    "pl-PL",
    "ru-RU",
    "tr-TR",
]

TRANSLATIONS["it-IT"] = {
    "crawl.incomplete_title": "⚠️ **Dati normativi incompleti**\n",
    "crawl.incomplete_regions": "I dati normativi delle seguenti regioni non sono stati completamente recuperati online:\n",
    "crawl.upload_prompt": "\nSi prega di caricare i documenti normativi completi per garantire l'accuratezza dei riferimenti incrociati.",
    "crawl.upload_btn": "📤 Carica documento normativo",
    "crawl.incomplete_fallback": "⚠️ Dati normativi incompleti. Si prega di caricare i documenti normativi completi.",
    "crossref.confirm_no_change": "✅ Conferma nessuna modifica necessaria",
    "crossref.confirmed": "✅ Risultati dei riferimenti incrociati confermati.",
    "crossref.analyzing_feedback": "🔄 Analisi del feedback di correzione dei riferimenti incrociati...",
    "crossref.no_llm": "⚠️ LLM non configurato. Si prega di configurare prima un provider LLM e un modello nelle impostazioni.",
    "crossref.llm_failed": "⚠️ Analisi LLM fallita: {error}",
    "crossref.parse_failed": "⚠️ Impossibile analizzare la risposta LLM. Si prega di descrivere la correzione in modo più chiaro.",
    "crossref.no_corrections": "ℹ️ Nessuna correzione specifica rilevata. Si prega di fare riferimento agli esempi e riprovare.",
    "crossref.reg_not_found": "Regolamento {reg_id} non trovato",
    "crossref.clause_not_found": "Clausola ISO {iso_clause} non trovata",
    "crossref.unsupported_field": "Campo non supportato {field_name}",
    "crossref.correction_title": "📋 **Risultati correzione riferimenti incrociati**\n",
    "crossref.applied_count": "✅ {count} correzione/i applicata/e:",
    "crossref.failed_count": "\n❌ {count} correzione/i non applicabile/i:",
    "reg_upload.read_failed": "❌ Impossibile leggere il file: {file_name}",
    "reg_upload.reading": "🔄 Lettura di **{file_name}** ...",
    "reg_upload.read_error": "❌ Lettura file fallita: {error}",
    "reg_upload.too_short": "❌ Contenuto del file troppo breve o non analizzabile: **{file_name}**",
    "reg_upload.not_regulatory": "❌ Questo file non sembra essere un documento normativo: **{file_name}**\n\nSolo documenti ISO 13485, normative sui dispositivi medici e gestione della qualità sono accettati.\nParole chiave rilevate: {keywords}",
    "reg_upload.summary": "{name}, 📋 **Riepilogo analisi**\n\n- Nome file: **{file_name}**\n- Dimensione file: {file_size}\n- Caratteri estratti: {char_count}\n- Rilevamento: ✅ Documento normativo qualità\n- Parole chiave correlate: {keywords}\n\n**Anteprima contenuto:**\n> {preview}...\n\nProcedere con l'analisi completa? LLM analizzerà le clausole e aggiornerà la tabella di mappatura normativa.",
    "reg_upload.confirm_btn": "✅ Conferma analisi",
    "reg_upload.cancel_btn": "❌ Annulla",
    "reg_upload.ask_upload": "{name}, 📤 **Si prega di caricare i documenti normativi completi**\n\nFormati supportati: PDF, Word (.docx), TXT, HTML, Markdown (.md)\nÈ possibile caricare fino a 5 file contemporaneamente.",
    "reg_upload.upload_cancelled": "⏭️ Caricamento annullato.",
    "reg_upload.no_pending": "⚠️ Nessun documento normativo in attesa trovato.",
    "reg_upload.llm_parsing": "🔄 Analisi LLM di **{file_name}** in corso...\n\nPotrebbe richiedere 1-3 minuti.",
    "reg_upload.parse_success": "✅ **Documento normativo analizzato**\n\n- ID regolamento: `{reg_id}`\n- Nome: {name_zh} ({name_en})\n- Paese: {country}\n- Clausole mappate ISO 13485: {mapped_count}\n- Requisiti specifici del paese: {unique_count}\n- Salvato in: `{filepath}`\n\nTabella di mappatura aggiornata. Il prossimo riferimento incrociato includerà questo regolamento.",
    "reg_upload.parse_failed": "❌ Analisi LLM fallita. Impossibile estrarre la struttura normativa dal documento.\nVerificare che il contenuto del documento sia completo e di natura normativa.",
    "reg_upload.parse_error": "❌ Errore durante l'analisi: {error}",
    "reg_upload.parse_cancelled": "✅ Analisi del documento normativo annullata.",
}
# Fill crossref.feedback_msg for it-IT (was missed)
TRANSLATIONS["it-IT"]["crossref.feedback_msg"] = EN["crossref.feedback_msg"]

TRANSLATIONS["pt-BR"] = {
    "crawl.incomplete_title": "⚠️ **Dados regulatórios incompletos**\n",
    "crawl.incomplete_regions": "Os dados regulatórios das seguintes regiões não puderam ser totalmente recuperados online:\n",
    "crawl.upload_prompt": "\nPor favor, envie os documentos regulatórios completos para garantir a precisão das referências cruzadas.",
    "crawl.upload_btn": "📤 Enviar documento regulatório",
    "crawl.incomplete_fallback": "⚠️ Dados regulatórios incompletos. Por favor, envie os documentos regulatórios completos.",
    "crossref.confirm_no_change": "✅ Confirmar que nenhuma alteração é necessária",
    "crossref.confirmed": "✅ Resultados das referências cruzadas confirmados.",
    "crossref.analyzing_feedback": "🔄 Analisando seu feedback de correção de referências cruzadas...",
    "crossref.no_llm": "⚠️ LLM não configurado. Configure primeiro um provedor LLM e um modelo nas configurações.",
    "crossref.llm_failed": "⚠️ Análise LLM falhou: {error}",
    "crossref.parse_failed": "⚠️ Não foi possível analisar a resposta do LLM. Tente descrever sua correção de forma mais clara.",
    "crossref.no_corrections": "ℹ️ Nenhuma correção específica detectada. Consulte os exemplos e tente novamente.",
    "crossref.reg_not_found": "Regulamento {reg_id} não encontrado",
    "crossref.clause_not_found": "Cláusula ISO {iso_clause} não encontrada",
    "crossref.unsupported_field": "Campo não suportado {field_name}",
    "crossref.correction_title": "📋 **Resultados da correção de referências cruzadas**\n",
    "crossref.applied_count": "✅ {count} correção(ões) aplicada(s):",
    "crossref.failed_count": "\n❌ {count} correção(ões) não pôde(puderam) ser aplicada(s):",
    "reg_upload.read_failed": "❌ Não foi possível ler o arquivo: {file_name}",
    "reg_upload.reading": "🔄 Lendo **{file_name}** ...",
    "reg_upload.read_error": "❌ Falha na leitura do arquivo: {error}",
    "reg_upload.too_short": "❌ Conteúdo do arquivo muito curto ou não pode ser analisado: **{file_name}**",
    "reg_upload.not_regulatory": "❌ Este arquivo não parece ser um documento regulatório: **{file_name}**\n\nApenas documentos ISO 13485, regulamentos de dispositivos médicos e gestão da qualidade são aceitos.\nPalavras-chave detectadas: {keywords}",
    "reg_upload.summary": "{name}, 📋 **Resumo da análise**\n\n- Nome do arquivo: **{file_name}**\n- Tamanho do arquivo: {file_size}\n- Caracteres extraídos: {char_count}\n- Detecção: ✅ Documento regulatório de qualidade\n- Palavras-chave relacionadas: {keywords}\n\n**Pré-visualização do conteúdo:**\n> {preview}...\n\nProsseguir com a análise completa? O LLM analisará as cláusulas e atualizará a tabela de mapeamento regulatório.",
    "reg_upload.confirm_btn": "✅ Confirmar análise",
    "reg_upload.cancel_btn": "❌ Cancelar",
    "reg_upload.ask_upload": "{name}, 📤 **Por favor, envie os documentos regulatórios completos**\n\nFormatos suportados: PDF, Word (.docx), TXT, HTML, Markdown (.md)\nVocê pode enviar até 5 arquivos de uma vez.",
    "reg_upload.upload_cancelled": "⏭️ Upload cancelado.",
    "reg_upload.no_pending": "⚠️ Nenhum documento regulatório pendente encontrado.",
    "reg_upload.llm_parsing": "🔄 Usando LLM para analisar **{file_name}** ...\n\nIsso pode levar de 1 a 3 minutos.",
    "reg_upload.parse_success": "✅ **Documento regulatório analisado**\n\n- ID do regulamento: `{reg_id}`\n- Nome: {name_zh} ({name_en})\n- País: {country}\n- Cláusulas mapeadas ISO 13485: {mapped_count}\n- Requisitos específicos do país: {unique_count}\n- Salvo em: `{filepath}`\n\nTabela de mapeamento atualizada. A próxima referência cruzada incluirá este regulamento.",
    "reg_upload.parse_failed": "❌ Análise LLM falhou. Não foi possível extrair a estrutura regulatória do documento.\nVerifique se o conteúdo do documento está completo e é de natureza regulatória.",
    "reg_upload.parse_error": "❌ Erro durante a análise: {error}",
    "reg_upload.parse_cancelled": "✅ Análise do documento regulatório cancelada.",
}
TRANSLATIONS["pt-BR"]["crossref.feedback_msg"] = EN["crossref.feedback_msg"]

TRANSLATIONS["ru-RU"] = {
    "crawl.incomplete_title": "⚠️ **Нормативные данные неполные**\n",
    "crawl.incomplete_regions": "Нормативные данные следующих регионов не удалось полностью получить онлайн:\n",
    "crawl.upload_prompt": "\nПожалуйста, загрузите полные нормативные документы для обеспечения точности перекрёстных ссылок.",
    "crawl.upload_btn": "📤 Загрузить нормативный документ",
    "crawl.incomplete_fallback": "⚠️ Нормативные данные неполные. Пожалуйста, загрузите полные нормативные документы.",
    "crossref.confirm_no_change": "✅ Подтвердить, что изменения не требуются",
    "crossref.confirmed": "✅ Результаты перекрёстных ссылок подтверждены.",
    "crossref.analyzing_feedback": "🔄 Анализ вашего отзыва по коррекции перекрёстных ссылок...",
    "crossref.no_llm": "⚠️ LLM не настроен. Сначала настройте поставщика LLM и модель в настройках.",
    "crossref.llm_failed": "⚠️ Анализ LLM не удался: {error}",
    "crossref.parse_failed": "⚠️ Не удалось разобрать ответ LLM. Попробуйте описать коррекцию более чётко.",
    "crossref.no_corrections": "ℹ️ Конкретные коррекции не обнаружены. Обратитесь к примерам и попробуйте снова.",
    "crossref.reg_not_found": "Регламент {reg_id} не найден",
    "crossref.clause_not_found": "Пункт ISO {iso_clause} не найден",
    "crossref.unsupported_field": "Неподдерживаемое поле {field_name}",
    "crossref.correction_title": "📋 **Результаты коррекции перекрёстных ссылок**\n",
    "crossref.applied_count": "✅ Применено {count} коррекция(й):",
    "crossref.failed_count": "\n❌ {count} коррекция(й) не удалось применить:",
    "reg_upload.read_failed": "❌ Не удалось прочитать файл: {file_name}",
    "reg_upload.reading": "🔄 Чтение **{file_name}** ...",
    "reg_upload.read_error": "❌ Ошибка чтения файла: {error}",
    "reg_upload.too_short": "❌ Содержимое файла слишком короткое или не может быть разобрано: **{file_name}**",
    "reg_upload.not_regulatory": "❌ Этот файл не является нормативным документом: **{file_name}**\n\nПринимаются только документы ISO 13485, нормативы медицинских изделий и управления качеством.\nОбнаруженные ключевые слова: {keywords}",
    "reg_upload.summary": "{name}, 📋 **Сводка анализа**\n\n- Имя файла: **{file_name}**\n- Размер файла: {file_size}\n- Извлечено символов: {char_count}\n- Обнаружение: ✅ Нормативный документ качества\n- Связанные ключевые слова: {keywords}\n\n**Предпросмотр содержимого:**\n> {preview}...\n\nПродолжить полный анализ? LLM проанализирует статьи и обновит таблицу сопоставления нормативов.",
    "reg_upload.confirm_btn": "✅ Подтвердить анализ",
    "reg_upload.cancel_btn": "❌ Отмена",
    "reg_upload.ask_upload": "{name}, 📤 **Пожалуйста, загрузите полные нормативные документы**\n\nПоддерживаемые форматы: PDF, Word (.docx), TXT, HTML, Markdown (.md)\nВы можете загрузить до 5 файлов одновременно.",
    "reg_upload.upload_cancelled": "⏭️ Загрузка отменена.",
    "reg_upload.no_pending": "⚠️ Нормативный документ в ожидании не найден.",
    "reg_upload.llm_parsing": "🔄 LLM анализирует **{file_name}** ...\n\nЭто может занять 1-3 минуты.",
    "reg_upload.parse_success": "✅ **Нормативный документ проанализирован**\n\n- ID регламента: `{reg_id}`\n- Название: {name_zh} ({name_en})\n- Страна: {country}\n- Сопоставленные статьи ISO 13485: {mapped_count}\n- Специфичные требования страны: {unique_count}\n- Сохранено в: `{filepath}`\n\nТаблица сопоставления обновлена. Следующая перекрёстная ссылка будет включать этот регламент.",
    "reg_upload.parse_failed": "❌ Анализ LLM не удался. Не удалось извлечь нормативную структуру из документа.\nУбедитесь, что содержимое документа полное и относится к нормативной сфере.",
    "reg_upload.parse_error": "❌ Ошибка во время анализа: {error}",
    "reg_upload.parse_cancelled": "✅ Анализ нормативного документа отменён.",
}
TRANSLATIONS["ru-RU"]["crossref.feedback_msg"] = EN["crossref.feedback_msg"]

# For the remaining locales, use English as fallback
for loc in [
    "vi-VN",
    "th-TH",
    "hi-IN",
    "ms-MY",
    "id-ID",
    "ar-SA",
    "nl-NL",
    "pl-PL",
    "tr-TR",
]:
    TRANSLATIONS[loc] = dict(EN)

# Now process each file
locale_map = {
    "zh-CN": "zh-CN.json",
    "ja-JP": "ja-JP.json",
    "ko-KR": "ko-KR.json",
    "vi-VN": "vi-VN.json",
    "th-TH": "th-TH.json",
    "hi-IN": "hi-IN.json",
    "ms-MY": "ms-MY.json",
    "id-ID": "id-ID.json",
    "ar-SA": "ar-SA.json",
    "fr-FR": "fr-FR.json",
    "de-DE": "de-DE.json",
    "es-ES": "es-ES.json",
    "it-IT": "it-IT.json",
    "pt-BR": "pt-BR.json",
    "nl-NL": "nl-NL.json",
    "pl-PL": "pl-PL.json",
    "ru-RU": "ru-RU.json",
    "tr-TR": "tr-TR.json",
}

needed_keys = list(EN.keys())

for locale_code, filename in locale_map.items():
    filepath = os.path.join(BASE, filename)

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    missing = [k for k in needed_keys if k not in data]
    if not missing:
        print(f"  {filename}: already has all keys, skipping")
        continue

    # Add missing keys with translations
    trans = TRANSLATIONS.get(locale_code, EN)
    for key in missing:
        data[key] = trans.get(key, EN[key])

    # Write back with sorted keys and proper formatting
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  {filename}: added {len(missing)} keys")

# Verify all files
print("\n=== Verification ===")
errors = 0
for filename in locale_map.values():
    filepath = os.path.join(BASE, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        missing = [k for k in needed_keys if k not in data]
        if missing:
            print(f"  FAIL {filename}: still missing {len(missing)} keys")
            errors += 1
        else:
            print(f"  OK   {filename}: all {len(needed_keys)} keys present")
    except json.JSONDecodeError as e:
        print(f"  FAIL {filename}: invalid JSON: {e}")
        errors += 1

if errors == 0:
    print(f"\n✅ All {len(locale_map)} locale files updated successfully!")
else:
    print(f"\n❌ {errors} file(s) had issues")
    sys.exit(1)
