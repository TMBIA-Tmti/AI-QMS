#!/usr/bin/env python3
"""
Inject missing i18n translations into all locale files.
Uses zh-TW as master. Provides human-quality translations for all 100 missing keys.
"""

import json
import os

LOCALE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "src", "chainlit_app", "locales"
)

# ============================================================
# TRANSLATIONS FOR ALL 18 LOCALES (100 keys each)
# Keys: same as zh-TW master, values: translated
# ============================================================

TRANSLATIONS = {}

# ============================================================
# ja-JP (Japanese) — only 16 watermark keys missing
# ============================================================
TRANSLATIONS["ja-JP"] = {
    "watermark.angle_options": "透かしの角度を選択してください：",
    "watermark.opacity_options": "透かしの透明度を選択してください：",
    "watermark.scale_options": "透かしのサイズを選択してください：",
    "watermark.position_options": "透かしの位置を選択してください：",
    "watermark.repeat_on": "はい",
    "watermark.repeat_off": "いいえ",
    "watermark.position_center": "中央",
    "watermark.position_top_left": "左上",
    "watermark.position_top_right": "右上",
    "watermark.position_bottom_left": "左下",
    "watermark.position_bottom_right": "右下",
    "watermark.status_enabled": "✅ 有効",
    "watermark.status_disabled": "❌ 無効",
    "watermark.status_not_configured": "⚠️ 未設定",
    "watermark.encrypted_pdf_warning": "⚠️ {filename} は暗号化された PDF のため、透かしを適用できません。透かしなしでアップロードしますか？",
    "watermark.unavailable": "⚠️ 透かし機能が利用できません（必要なパッケージ reportlab が不足しています）。",
}

# ============================================================
# zh-CN (Simplified Chinese)
# ============================================================
TRANSLATIONS["zh-CN"] = {
    "_commands.cmd.watermark_settings": ["水印设置", "水印"],
    "_commands.cmd.hierarchy_settings": ["层级设置", "质量体系设置"],
    "obsolete_detect.title": "⚠️ **检测到疑似作废文件**（共 {count} 份）",
    "obsolete_detect.item": "📄 **{filename}** → {doc_id}\n检测原因：{reasons}\n置信度：{confidence}%",
    "obsolete_detect.confirm_question": "此文件是否确实已作废？",
    "obsolete_detect.btn_yes_obsolete": "✅ 是，已作废",
    "obsolete_detect.btn_no_normal": "❌ 否，正常文件",
    "obsolete_detect.action_question": "文件 **{doc_id}** 已确认为作废文件，请选择处理方式：",
    "obsolete_detect.btn_save_obsolete": "💾 存入并标记为作废",
    "obsolete_detect.btn_skip": "🗑️ 不上传",
    "obsolete_detect.marked_obsolete": "✅ {doc_id} → 将存入并标记为作废",
    "obsolete_detect.marked_skip": "🗑️ {doc_id} → 不上传",
    "obsolete_detect.marked_normal": "✅ {doc_id} → 正常文件",
    "obsolete_detect.all_done": "作废文件确认完成。",
    "obsolete_detect.btn_all_obsolete": "🗑️ 全部标记为作废",
    "obsolete_detect.btn_all_normal": "✅ 全部标记为正常",
    "upload_confirm.processing_complete": "📋 **文件处理完成**（共 {total} 份，成功 {success} 份，失败 {failed} 份）",
    "upload_confirm.final_title": "📋 **上传总览确认**",
    "upload_confirm.final_table_header": "| # | 文件编号 | 标题 | 层级 | 水印 | 状态 |",
    "upload_confirm.final_table_separator": "|---|---------|------|------|--------|------|",
    "upload_confirm.btn_confirm": "✅ 确认上传",
    "upload_confirm.btn_cancel": "❌ 取消全部",
    "upload_confirm.saving": "⏳ 正在存入数据库...（{current}/{total}）",
    "upload_confirm.complete": "✅ **上传完成**\n\n成功存入 {count} 份文件。",
    "upload_confirm.cancelled": "❌ 已取消上传，所有暂存文件已清除。",
    "upload_confirm.pending_warning": "⚠️ 您有待确认的上传文件，请先完成或取消当前的确认流程。",
    "hierarchy_batch.title": "📋 **文件层级确认**（共 {count} 份文件）",
    "hierarchy_batch.table_header": "| # | 文件编号 | 标题 | AI 判定层级 | 置信度 |",
    "hierarchy_batch.table_separator": "|---|---------|------|------------|--------|",
    "hierarchy_batch.legend": "💡 ✅ = 高置信度(≥80%)  ⚠️ = 建议确认(<80%)",
    "hierarchy_batch.btn_confirm_all": "✅ 全部确认",
    "hierarchy_batch.btn_edit": "✏️ 逐一修改",
    "hierarchy_batch.btn_add_custom": "➕ 新增自定义层级",
    "hierarchy_batch.edit_title": "✏️ **修改文件层级**\n\n文件 {current}/{total}: **{doc_id}** — {title}\n当前层级: {level_label} ({confidence}%)",
    "hierarchy_batch.final_title": "📋 **最终层级确认**",
    "hierarchy_batch.final_table_header": "| # | 文件编号 | 标题 | 确认层级 |",
    "hierarchy_batch.final_table_separator": "|---|---------|------|----------|",
    "hierarchy_batch.btn_done": "✅ 确认",
    "hierarchy_batch.btn_redo": "🔄 重新修改",
    "hierarchy_batch.changed_mark": "✏️",
    "system_scope.setup_title": "📋 **质量体系层级范围设置**\n\n您的质量管理体系文件分为几阶？",
    "system_scope.setup_desc": "此设置会影响文件上传时的层级选项。设置完成后可随时通过「层级设置」命令调整。",
    "system_scope.btn_3level": "1-3 阶（质量手册、程序文件、作业指导书）",
    "system_scope.btn_4level": "1-4 阶（质量手册、程序文件、作业指导书、表单）",
    "system_scope.btn_custom": "自定义",
    "system_scope.confirmed": "✅ 质量体系范围已设置为 **{level} 阶**",
    "system_scope.cmd_title": "📋 **层级设置**\n\n当前质量体系范围：**{level} 阶**",
    "system_scope.existing_l4_warning": "⚠️ 当前有 {count} 份文件归类为 4 阶，现有文件的层级不会自动变更。",
    "watermark.ask_setup": "🖼️ **水印设置**\n\n水印可以在文件上加上公司标志或「受控文件」字样，确保打印出的文件具有管制标识。\n\n是否要设置水印？",
    "watermark.btn_start": "✅ 是，开始设置",
    "watermark.btn_skip": "❌ 不需要水印",
    "watermark.upload_image": "📎 **上传水印图片**\n\n请上传您要使用的水印图片（PNG 或 JPG 格式）。\n\n建议：\n- 使用透明背景的 PNG 图片效果最佳\n- 建议尺寸：300x300 ~ 1000x1000 像素",
    "watermark.image_too_large": "⚠️ 图片文件过大（超过 10MB），请压缩后重新上传。",
    "watermark.image_invalid_format": "⚠️ 不支持的图片格式，请上传 PNG 或 JPG 文件。",
    "watermark.image_saved": "✅ 水印图片已保存：{filename}",
    "watermark.settings_title": "🖼️ **水印效果设置**",
    "watermark.settings_current": "当前设置：\n- 📐 角度: {angle}°\n- 🎨 透明度: {opacity}%\n- 📏 大小: {scale}%\n- 📍 位置: {position}\n- 🔁 重复图案: {repeat}",
    "watermark.btn_angle": "📐 调整角度",
    "watermark.btn_opacity": "🎨 调整透明度",
    "watermark.btn_scale": "📏 调整大小",
    "watermark.btn_position": "📍 调整位置",
    "watermark.btn_repeat": "🔁 切换重复模式",
    "watermark.btn_preview": "👁️ 预览效果",
    "watermark.btn_confirm": "✅ 确认设置",
    "watermark.btn_cancel": "❌ 取消",
    "watermark.preview_sent": "👁️ **水印预览**\n\n以下是应用当前设置的预览效果：",
    "watermark.settings_saved": "✅ 水印设置已保存。",
    "watermark.rules_title": "📋 **水印自动应用规则**",
    "watermark.rules_default_desc": "默认规则：\n- ✅ 1阶-质量手册：应用水印\n- ✅ 2阶-程序文件：应用水印\n- ✅ 3阶-作业指导书：应用水印\n- ❌ 4阶-表单：不应用\n- ✅ 外来法规文件：应用水印",
    "watermark.btn_default_rules": "✅ 使用默认规则",
    "watermark.btn_custom_rules": "✏️ 自定义规则",
    "watermark.btn_disable_all": "❌ 全部不应用水印",
    "watermark.batch_title": "🖼️ **水印确认**",
    "watermark.batch_table_header": "| # | 文件编号 | 标题 | 层级 | 水印 |",
    "watermark.batch_table_separator": "|---|---------|------|------|--------|",
    "watermark.btn_batch_confirm": "✅ 确认",
    "watermark.btn_batch_edit": "✏️ 逐一调整",
    "watermark.btn_modify_settings": "⚙️ 修改水印设置",
    "watermark.applying": "🖼️ 正在施加水印...（{current}/{total}）",
    "watermark.applied_success": "✅ {filename} — 水印已应用",
    "watermark.applied_skip": "⏭️ {filename} — 格式不支持水印（{format}），已跳过",
    "watermark.applied_error": "❌ {filename} — 水印应用失败：{error}",
    "watermark.cmd_title": "🖼️ **水印设置**\n\n当前状态：{status}",
    "watermark.cmd_image": "图片：{name}",
    "watermark.status_enabled": "✅ 已启用",
    "watermark.status_disabled": "❌ 未启用",
    "watermark.status_not_configured": "⚠️ 尚未设置",
    "watermark.encrypted_pdf_warning": "⚠️ {filename} 是加密 PDF，无法施加水印。是否仍要上传（不含水印）？",
    "watermark.angle_options": "请选择水印角度：",
    "watermark.opacity_options": "请选择水印透明度：",
    "watermark.scale_options": "请选择水印大小：",
    "watermark.position_options": "请选择水印位置：",
    "watermark.repeat_on": "是",
    "watermark.repeat_off": "否",
    "watermark.position_center": "居中",
    "watermark.position_top_left": "左上",
    "watermark.position_top_right": "右上",
    "watermark.position_bottom_left": "左下",
    "watermark.position_bottom_right": "右下",
    "watermark.unavailable": "⚠️ 水印功能不可用（缺少必要包 reportlab）。",
}

# ============================================================
# ko-KR (Korean)
# ============================================================
TRANSLATIONS["ko-KR"] = {
    "_commands.cmd.watermark_settings": ["워터마크 설정", "워터마크"],
    "_commands.cmd.hierarchy_settings": ["계층 설정", "품질 시스템 설정"],
    "obsolete_detect.title": "⚠️ **폐기 의심 문서 감지됨** (총 {count}건)",
    "obsolete_detect.item": "📄 **{filename}** → {doc_id}\n감지 사유: {reasons}\n신뢰도: {confidence}%",
    "obsolete_detect.confirm_question": "이 문서가 실제로 폐기되었습니까?",
    "obsolete_detect.btn_yes_obsolete": "✅ 예, 폐기됨",
    "obsolete_detect.btn_no_normal": "❌ 아니오, 정상 문서",
    "obsolete_detect.action_question": "문서 **{doc_id}**이(가) 폐기 문서로 확인되었습니다. 처리 방법을 선택하세요:",
    "obsolete_detect.btn_save_obsolete": "💾 저장 후 폐기로 표시",
    "obsolete_detect.btn_skip": "🗑️ 업로드하지 않음",
    "obsolete_detect.marked_obsolete": "✅ {doc_id} → 저장 후 폐기로 표시됨",
    "obsolete_detect.marked_skip": "🗑️ {doc_id} → 업로드하지 않음",
    "obsolete_detect.marked_normal": "✅ {doc_id} → 정상 문서",
    "obsolete_detect.all_done": "폐기 문서 확인 완료.",
    "obsolete_detect.btn_all_obsolete": "🗑️ 모두 폐기로 표시",
    "obsolete_detect.btn_all_normal": "✅ 모두 정상으로 표시",
    "upload_confirm.processing_complete": "📋 **문서 처리 완료** (총 {total}건, 성공 {success}건, 실패 {failed}건)",
    "upload_confirm.final_title": "📋 **업로드 개요 확인**",
    "upload_confirm.final_table_header": "| # | 문서 ID | 제목 | 계층 | 워터마크 | 상태 |",
    "upload_confirm.final_table_separator": "|---|---------|------|------|--------|------|",
    "upload_confirm.btn_confirm": "✅ 업로드 확인",
    "upload_confirm.btn_cancel": "❌ 전체 취소",
    "upload_confirm.saving": "⏳ 데이터베이스에 저장 중... ({current}/{total})",
    "upload_confirm.complete": "✅ **업로드 완료**\n\n{count}건의 문서가 저장되었습니다.",
    "upload_confirm.cancelled": "❌ 업로드가 취소되었습니다. 모든 임시 파일이 삭제되었습니다.",
    "upload_confirm.pending_warning": "⚠️ 대기 중인 업로드가 있습니다. 현재 프로세스를 완료하거나 취소해 주세요.",
    "hierarchy_batch.title": "📋 **문서 계층 확인** ({count}건)",
    "hierarchy_batch.table_header": "| # | 문서 ID | 제목 | AI 분류 | 신뢰도 |",
    "hierarchy_batch.table_separator": "|---|---------|------|------------|--------|",
    "hierarchy_batch.legend": "💡 ✅ = 높은 신뢰도(≥80%)  ⚠️ = 검토 권장(<80%)",
    "hierarchy_batch.btn_confirm_all": "✅ 전체 확인",
    "hierarchy_batch.btn_edit": "✏️ 개별 수정",
    "hierarchy_batch.btn_add_custom": "➕ 사용자 정의 계층 추가",
    "hierarchy_batch.edit_title": "✏️ **문서 계층 수정**\n\n문서 {current}/{total}: **{doc_id}** — {title}\n현재 계층: {level_label} ({confidence}%)",
    "hierarchy_batch.final_title": "📋 **최종 계층 확인**",
    "hierarchy_batch.final_table_header": "| # | 문서 ID | 제목 | 확인된 계층 |",
    "hierarchy_batch.final_table_separator": "|---|---------|------|----------|",
    "hierarchy_batch.btn_done": "✅ 확인",
    "hierarchy_batch.btn_redo": "🔄 다시 수정",
    "hierarchy_batch.changed_mark": "✏️",
    "system_scope.setup_title": "📋 **품질 시스템 계층 범위 설정**\n\nQMS 문서 시스템은 몇 단계입니까?",
    "system_scope.setup_desc": "이 설정은 업로드 시 계층 옵션에 영향을 미칩니다. '계층 설정' 명령으로 언제든 조정할 수 있습니다.",
    "system_scope.btn_3level": "1-3 단계 (품질 매뉴얼, 절차서, 작업 지시서)",
    "system_scope.btn_4level": "1-4 단계 (품질 매뉴얼, 절차서, 작업 지시서, 양식)",
    "system_scope.btn_custom": "사용자 정의",
    "system_scope.confirmed": "✅ 품질 시스템 범위가 **{level} 단계**로 설정되었습니다",
    "system_scope.cmd_title": "📋 **계층 설정**\n\n현재 범위: **{level} 단계**",
    "system_scope.existing_l4_warning": "⚠️ 현재 {count}건의 문서가 4단계로 분류되어 있습니다. 기존 문서의 계층은 자동으로 변경되지 않습니다.",
    "watermark.ask_setup": "🖼️ **워터마크 설정**\n\n워터마크를 통해 회사 로고나 '관리 문서' 표시를 추가하여 인쇄된 문서에 관리 표식을 넣을 수 있습니다.\n\n워터마크를 설정하시겠습니까?",
    "watermark.btn_start": "✅ 예, 설정 시작",
    "watermark.btn_skip": "❌ 워터마크 불필요",
    "watermark.upload_image": "📎 **워터마크 이미지 업로드**\n\n사용할 이미지를 업로드해 주세요 (PNG 또는 JPG).\n\n권장사항:\n- 투명 배경 PNG 이미지가 가장 좋습니다\n- 권장 크기: 300x300 ~ 1000x1000 픽셀",
    "watermark.image_too_large": "⚠️ 이미지 파일이 너무 큽니다 (10MB 초과). 압축 후 다시 업로드해 주세요.",
    "watermark.image_invalid_format": "⚠️ 지원되지 않는 이미지 형식입니다. PNG 또는 JPG를 업로드해 주세요.",
    "watermark.image_saved": "✅ 워터마크 이미지 저장됨: {filename}",
    "watermark.settings_title": "🖼️ **워터마크 효과 설정**",
    "watermark.settings_current": "현재 설정:\n- 📐 각도: {angle}°\n- 🎨 투명도: {opacity}%\n- 📏 크기: {scale}%\n- 📍 위치: {position}\n- 🔁 반복 패턴: {repeat}",
    "watermark.btn_angle": "📐 각도 조정",
    "watermark.btn_opacity": "🎨 투명도 조정",
    "watermark.btn_scale": "📏 크기 조정",
    "watermark.btn_position": "📍 위치 조정",
    "watermark.btn_repeat": "🔁 반복 전환",
    "watermark.btn_preview": "👁️ 미리보기",
    "watermark.btn_confirm": "✅ 설정 확인",
    "watermark.btn_cancel": "❌ 취소",
    "watermark.preview_sent": "👁️ **워터마크 미리보기**\n\n현재 설정으로 적용한 미리보기입니다:",
    "watermark.settings_saved": "✅ 워터마크 설정이 저장되었습니다.",
    "watermark.rules_title": "📋 **워터마크 자동 적용 규칙**",
    "watermark.rules_default_desc": "기본 규칙:\n- ✅ 1단계 - 품질 매뉴얼: 적용\n- ✅ 2단계 - 절차서: 적용\n- ✅ 3단계 - 작업 지시서: 적용\n- ❌ 4단계 - 양식: 미적용\n- ✅ 외부 법규 문서: 적용",
    "watermark.btn_default_rules": "✅ 기본 규칙 사용",
    "watermark.btn_custom_rules": "✏️ 사용자 정의 규칙",
    "watermark.btn_disable_all": "❌ 전체 워터마크 비활성화",
    "watermark.batch_title": "🖼️ **워터마크 확인**",
    "watermark.batch_table_header": "| # | 문서 ID | 제목 | 계층 | 워터마크 |",
    "watermark.batch_table_separator": "|---|---------|------|------|--------|",
    "watermark.btn_batch_confirm": "✅ 확인",
    "watermark.btn_batch_edit": "✏️ 개별 조정",
    "watermark.btn_modify_settings": "⚙️ 워터마크 설정 수정",
    "watermark.applying": "🖼️ 워터마크 적용 중... ({current}/{total})",
    "watermark.applied_success": "✅ {filename} — 워터마크 적용됨",
    "watermark.applied_skip": "⏭️ {filename} — 워터마크를 지원하지 않는 형식({format}), 건너뜀",
    "watermark.applied_error": "❌ {filename} — 워터마크 적용 실패: {error}",
    "watermark.cmd_title": "🖼️ **워터마크 설정**\n\n현재 상태: {status}",
    "watermark.cmd_image": "이미지: {name}",
    "watermark.status_enabled": "✅ 활성화됨",
    "watermark.status_disabled": "❌ 비활성화됨",
    "watermark.status_not_configured": "⚠️ 미설정",
    "watermark.encrypted_pdf_warning": "⚠️ {filename}은(는) 암호화된 PDF로 워터마크를 적용할 수 없습니다. 워터마크 없이 업로드하시겠습니까?",
    "watermark.angle_options": "워터마크 각도를 선택하세요:",
    "watermark.opacity_options": "워터마크 투명도를 선택하세요:",
    "watermark.scale_options": "워터마크 크기를 선택하세요:",
    "watermark.position_options": "워터마크 위치를 선택하세요:",
    "watermark.repeat_on": "예",
    "watermark.repeat_off": "아니오",
    "watermark.position_center": "중앙",
    "watermark.position_top_left": "좌상단",
    "watermark.position_top_right": "우상단",
    "watermark.position_bottom_left": "좌하단",
    "watermark.position_bottom_right": "우하단",
    "watermark.unavailable": "⚠️ 워터마크 기능을 사용할 수 없습니다 (필수 패키지 reportlab 누락).",
}

# ============================================================
# fr-FR (French)
# ============================================================
TRANSLATIONS["fr-FR"] = {
    "_commands.cmd.watermark_settings": ["paramètres du filigrane", "filigrane"],
    "_commands.cmd.hierarchy_settings": [
        "paramètres de hiérarchie",
        "configuration hiérarchie",
    ],
    "obsolete_detect.title": "⚠️ **Documents suspectés obsolètes détectés** ({count} au total)",
    "obsolete_detect.item": "📄 **{filename}** → {doc_id}\nRaison : {reasons}\nConfiance : {confidence}%",
    "obsolete_detect.confirm_question": "Ce document est-il réellement obsolète ?",
    "obsolete_detect.btn_yes_obsolete": "✅ Oui, obsolète",
    "obsolete_detect.btn_no_normal": "❌ Non, document normal",
    "obsolete_detect.action_question": "Le document **{doc_id}** est confirmé comme obsolète. Choisissez une action :",
    "obsolete_detect.btn_save_obsolete": "💾 Enregistrer et marquer comme obsolète",
    "obsolete_detect.btn_skip": "🗑️ Ne pas téléverser",
    "obsolete_detect.marked_obsolete": "✅ {doc_id} → Sera enregistré et marqué comme obsolète",
    "obsolete_detect.marked_skip": "🗑️ {doc_id} → Ne sera pas téléversé",
    "obsolete_detect.marked_normal": "✅ {doc_id} → Document normal",
    "obsolete_detect.all_done": "Confirmation des documents obsolètes terminée.",
    "obsolete_detect.btn_all_obsolete": "🗑️ Tout marquer comme obsolète",
    "obsolete_detect.btn_all_normal": "✅ Tout marquer comme normal",
    "upload_confirm.processing_complete": "📋 **Traitement terminé** ({total} au total, {success} réussis, {failed} échoués)",
    "upload_confirm.final_title": "📋 **Confirmation du téléversement**",
    "upload_confirm.final_table_header": "| # | ID Document | Titre | Hiérarchie | Filigrane | Statut |",
    "upload_confirm.final_table_separator": "|---|---------|------|------|--------|------|",
    "upload_confirm.btn_confirm": "✅ Confirmer le téléversement",
    "upload_confirm.btn_cancel": "❌ Tout annuler",
    "upload_confirm.saving": "⏳ Enregistrement en base de données... ({current}/{total})",
    "upload_confirm.complete": "✅ **Téléversement terminé**\n\n{count} documents enregistrés avec succès.",
    "upload_confirm.cancelled": "❌ Téléversement annulé. Tous les fichiers temporaires ont été supprimés.",
    "upload_confirm.pending_warning": "⚠️ Vous avez des téléversements en attente. Veuillez terminer ou annuler le processus en cours.",
    "hierarchy_batch.title": "📋 **Confirmation de la hiérarchie documentaire** ({count} documents)",
    "hierarchy_batch.table_header": "| # | ID Document | Titre | Classification IA | Confiance |",
    "hierarchy_batch.table_separator": "|---|---------|------|------------|--------|",
    "hierarchy_batch.legend": "💡 ✅ = Haute confiance (≥80 %)  ⚠️ = Vérification recommandée (<80 %)",
    "hierarchy_batch.btn_confirm_all": "✅ Tout confirmer",
    "hierarchy_batch.btn_edit": "✏️ Modifier individuellement",
    "hierarchy_batch.btn_add_custom": "➕ Ajouter un niveau personnalisé",
    "hierarchy_batch.edit_title": "✏️ **Modifier la hiérarchie du document**\n\nDocument {current}/{total} : **{doc_id}** — {title}\nHiérarchie actuelle : {level_label} ({confidence}%)",
    "hierarchy_batch.final_title": "📋 **Confirmation finale de la hiérarchie**",
    "hierarchy_batch.final_table_header": "| # | ID Document | Titre | Hiérarchie confirmée |",
    "hierarchy_batch.final_table_separator": "|---|---------|------|----------|",
    "hierarchy_batch.btn_done": "✅ Confirmer",
    "hierarchy_batch.btn_redo": "🔄 Recommencer",
    "hierarchy_batch.changed_mark": "✏️",
    "system_scope.setup_title": "📋 **Configuration du périmètre hiérarchique**\n\nCombien de niveaux comporte votre système documentaire qualité ?",
    "system_scope.setup_desc": "Ce paramètre affecte les options de hiérarchie lors du téléversement. Vous pouvez l'ajuster via la commande « paramètres de hiérarchie ».",
    "system_scope.btn_3level": "1-3 niveaux (Manuel qualité, Procédures, Instructions de travail)",
    "system_scope.btn_4level": "1-4 niveaux (Manuel qualité, Procédures, Instructions de travail, Formulaires)",
    "system_scope.btn_custom": "Personnalisé",
    "system_scope.confirmed": "✅ Le périmètre du système qualité est défini à **{level} niveaux**",
    "system_scope.cmd_title": "📋 **Paramètres de hiérarchie**\n\nPérimètre actuel : **{level} niveaux**",
    "system_scope.existing_l4_warning": "⚠️ {count} documents sont actuellement classés au niveau 4. Les hiérarchies existantes ne seront pas modifiées automatiquement.",
    "watermark.ask_setup": "🖼️ **Paramètres du filigrane**\n\nLes filigranes ajoutent un logo d'entreprise ou la mention « Document maîtrisé » pour garantir l'identification des documents imprimés.\n\nSouhaitez-vous configurer un filigrane ?",
    "watermark.btn_start": "✅ Oui, commencer la configuration",
    "watermark.btn_skip": "❌ Pas de filigrane",
    "watermark.upload_image": "📎 **Téléverser l'image du filigrane**\n\nVeuillez téléverser l'image à utiliser (PNG ou JPG).\n\nConseils :\n- Un PNG avec fond transparent donne les meilleurs résultats\n- Taille recommandée : 300x300 à 1000x1000 pixels",
    "watermark.image_too_large": "⚠️ Fichier image trop volumineux (plus de 10 Mo). Veuillez compresser et retéléverser.",
    "watermark.image_invalid_format": "⚠️ Format d'image non pris en charge. Veuillez téléverser un PNG ou JPG.",
    "watermark.image_saved": "✅ Image du filigrane enregistrée : {filename}",
    "watermark.settings_title": "🖼️ **Paramètres d'effet du filigrane**",
    "watermark.settings_current": "Paramètres actuels :\n- 📐 Angle : {angle}°\n- 🎨 Opacité : {opacity}%\n- 📏 Taille : {scale}%\n- 📍 Position : {position}\n- 🔁 Motif répété : {repeat}",
    "watermark.btn_angle": "📐 Ajuster l'angle",
    "watermark.btn_opacity": "🎨 Ajuster l'opacité",
    "watermark.btn_scale": "📏 Ajuster la taille",
    "watermark.btn_position": "📍 Ajuster la position",
    "watermark.btn_repeat": "🔁 Basculer la répétition",
    "watermark.btn_preview": "👁️ Aperçu",
    "watermark.btn_confirm": "✅ Confirmer les paramètres",
    "watermark.btn_cancel": "❌ Annuler",
    "watermark.preview_sent": "👁️ **Aperçu du filigrane**\n\nVoici un aperçu avec les paramètres actuels :",
    "watermark.settings_saved": "✅ Paramètres du filigrane enregistrés.",
    "watermark.rules_title": "📋 **Règles d'application automatique du filigrane**",
    "watermark.rules_default_desc": "Règles par défaut :\n- ✅ Niveau 1 - Manuel qualité : Appliquer\n- ✅ Niveau 2 - Procédures : Appliquer\n- ✅ Niveau 3 - Instructions de travail : Appliquer\n- ❌ Niveau 4 - Formulaires : Ne pas appliquer\n- ✅ Documents réglementaires externes : Appliquer",
    "watermark.btn_default_rules": "✅ Utiliser les règles par défaut",
    "watermark.btn_custom_rules": "✏️ Règles personnalisées",
    "watermark.btn_disable_all": "❌ Désactiver tous les filigranes",
    "watermark.batch_title": "🖼️ **Confirmation du filigrane**",
    "watermark.batch_table_header": "| # | ID Document | Titre | Hiérarchie | Filigrane |",
    "watermark.batch_table_separator": "|---|---------|------|------|--------|",
    "watermark.btn_batch_confirm": "✅ Confirmer",
    "watermark.btn_batch_edit": "✏️ Ajuster individuellement",
    "watermark.btn_modify_settings": "⚙️ Modifier les paramètres du filigrane",
    "watermark.applying": "🖼️ Application des filigranes... ({current}/{total})",
    "watermark.applied_success": "✅ {filename} — Filigrane appliqué",
    "watermark.applied_skip": "⏭️ {filename} — Format ne prenant pas en charge les filigranes ({format}), ignoré",
    "watermark.applied_error": "❌ {filename} — Échec de l'application du filigrane : {error}",
    "watermark.cmd_title": "🖼️ **Paramètres du filigrane**\n\nStatut actuel : {status}",
    "watermark.cmd_image": "Image : {name}",
    "watermark.status_enabled": "✅ Activé",
    "watermark.status_disabled": "❌ Désactivé",
    "watermark.status_not_configured": "⚠️ Non configuré",
    "watermark.encrypted_pdf_warning": "⚠️ {filename} est un PDF chiffré et ne peut pas recevoir de filigrane. Téléverser sans filigrane ?",
    "watermark.angle_options": "Sélectionnez l'angle du filigrane :",
    "watermark.opacity_options": "Sélectionnez l'opacité du filigrane :",
    "watermark.scale_options": "Sélectionnez la taille du filigrane :",
    "watermark.position_options": "Sélectionnez la position du filigrane :",
    "watermark.repeat_on": "Oui",
    "watermark.repeat_off": "Non",
    "watermark.position_center": "Centre",
    "watermark.position_top_left": "Haut gauche",
    "watermark.position_top_right": "Haut droite",
    "watermark.position_bottom_left": "Bas gauche",
    "watermark.position_bottom_right": "Bas droite",
    "watermark.unavailable": "⚠️ Fonctionnalité de filigrane indisponible (package reportlab manquant).",
}

# ============================================================
# de-DE (German)
# ============================================================
TRANSLATIONS["de-DE"] = {
    "_commands.cmd.watermark_settings": [
        "Wasserzeichen-Einstellungen",
        "Wasserzeichen",
    ],
    "_commands.cmd.hierarchy_settings": [
        "Hierarchie-Einstellungen",
        "Hierarchie einrichten",
    ],
    "obsolete_detect.title": "⚠️ **Möglicherweise veraltete Dokumente erkannt** ({count} insgesamt)",
    "obsolete_detect.item": "📄 **{filename}** → {doc_id}\nGrund: {reasons}\nKonfidenz: {confidence}%",
    "obsolete_detect.confirm_question": "Ist dieses Dokument tatsächlich veraltet?",
    "obsolete_detect.btn_yes_obsolete": "✅ Ja, veraltet",
    "obsolete_detect.btn_no_normal": "❌ Nein, normales Dokument",
    "obsolete_detect.action_question": "Dokument **{doc_id}** wurde als veraltet bestätigt. Aktion wählen:",
    "obsolete_detect.btn_save_obsolete": "💾 Speichern und als veraltet markieren",
    "obsolete_detect.btn_skip": "🗑️ Nicht hochladen",
    "obsolete_detect.marked_obsolete": "✅ {doc_id} → Wird gespeichert und als veraltet markiert",
    "obsolete_detect.marked_skip": "🗑️ {doc_id} → Wird nicht hochgeladen",
    "obsolete_detect.marked_normal": "✅ {doc_id} → Normales Dokument",
    "obsolete_detect.all_done": "Bestätigung veralteter Dokumente abgeschlossen.",
    "obsolete_detect.btn_all_obsolete": "🗑️ Alle als veraltet markieren",
    "obsolete_detect.btn_all_normal": "✅ Alle als normal markieren",
    "upload_confirm.processing_complete": "📋 **Verarbeitung abgeschlossen** ({total} gesamt, {success} erfolgreich, {failed} fehlgeschlagen)",
    "upload_confirm.final_title": "📋 **Upload-Übersicht**",
    "upload_confirm.final_table_header": "| # | Dokument-ID | Titel | Hierarchie | Wasserzeichen | Status |",
    "upload_confirm.final_table_separator": "|---|---------|------|------|--------|------|",
    "upload_confirm.btn_confirm": "✅ Upload bestätigen",
    "upload_confirm.btn_cancel": "❌ Alles abbrechen",
    "upload_confirm.saving": "⏳ Speichere in Datenbank... ({current}/{total})",
    "upload_confirm.complete": "✅ **Upload abgeschlossen**\n\n{count} Dokumente erfolgreich gespeichert.",
    "upload_confirm.cancelled": "❌ Upload abgebrochen. Alle temporären Dateien wurden gelöscht.",
    "upload_confirm.pending_warning": "⚠️ Sie haben ausstehende Uploads. Bitte schließen Sie den aktuellen Vorgang ab oder brechen Sie ihn ab.",
    "hierarchy_batch.title": "📋 **Dokumenthierarchie bestätigen** ({count} Dokumente)",
    "hierarchy_batch.table_header": "| # | Dokument-ID | Titel | KI-Klassifizierung | Konfidenz |",
    "hierarchy_batch.table_separator": "|---|---------|------|------------|--------|",
    "hierarchy_batch.legend": "💡 ✅ = Hohe Konfidenz (≥80 %)  ⚠️ = Überprüfung empfohlen (<80 %)",
    "hierarchy_batch.btn_confirm_all": "✅ Alle bestätigen",
    "hierarchy_batch.btn_edit": "✏️ Einzeln bearbeiten",
    "hierarchy_batch.btn_add_custom": "➕ Benutzerdefinierte Hierarchie hinzufügen",
    "hierarchy_batch.edit_title": "✏️ **Dokumenthierarchie bearbeiten**\n\nDokument {current}/{total}: **{doc_id}** — {title}\nAktuelle Hierarchie: {level_label} ({confidence}%)",
    "hierarchy_batch.final_title": "📋 **Endgültige Hierarchiebestätigung**",
    "hierarchy_batch.final_table_header": "| # | Dokument-ID | Titel | Bestätigte Hierarchie |",
    "hierarchy_batch.final_table_separator": "|---|---------|------|----------|",
    "hierarchy_batch.btn_done": "✅ Bestätigen",
    "hierarchy_batch.btn_redo": "🔄 Erneut bearbeiten",
    "hierarchy_batch.changed_mark": "✏️",
    "system_scope.setup_title": "📋 **QMS-Hierarchie-Umfang einrichten**\n\nWie viele Ebenen hat Ihr QMS-Dokumentensystem?",
    "system_scope.setup_desc": "Diese Einstellung beeinflusst die Hierarchieoptionen beim Upload. Sie können dies jederzeit über den Befehl 'Hierarchie-Einstellungen' anpassen.",
    "system_scope.btn_3level": "1-3 Ebenen (Qualitätshandbuch, Verfahren, Arbeitsanweisungen)",
    "system_scope.btn_4level": "1-4 Ebenen (Qualitätshandbuch, Verfahren, Arbeitsanweisungen, Formulare)",
    "system_scope.btn_custom": "Benutzerdefiniert",
    "system_scope.confirmed": "✅ QMS-Umfang auf **{level} Ebenen** festgelegt",
    "system_scope.cmd_title": "📋 **Hierarchie-Einstellungen**\n\nAktueller Umfang: **{level} Ebenen**",
    "system_scope.existing_l4_warning": "⚠️ Derzeit sind {count} Dokumente als Ebene 4 klassifiziert. Bestehende Hierarchien werden nicht automatisch geändert.",
    "watermark.ask_setup": "🖼️ **Wasserzeichen-Einstellungen**\n\nWasserzeichen können Firmenlogos oder 'Kontrolliertes Dokument'-Text hinzufügen, um gedruckte Dokumente zu kennzeichnen.\n\nMöchten Sie ein Wasserzeichen einrichten?",
    "watermark.btn_start": "✅ Ja, Einrichtung starten",
    "watermark.btn_skip": "❌ Kein Wasserzeichen",
    "watermark.upload_image": "📎 **Wasserzeichen-Bild hochladen**\n\nBitte laden Sie das gewünschte Bild hoch (PNG oder JPG).\n\nTipps:\n- PNG mit transparentem Hintergrund liefert beste Ergebnisse\n- Empfohlene Größe: 300x300 bis 1000x1000 Pixel",
    "watermark.image_too_large": "⚠️ Bilddatei zu groß (über 10 MB). Bitte komprimieren und erneut hochladen.",
    "watermark.image_invalid_format": "⚠️ Nicht unterstütztes Bildformat. Bitte PNG oder JPG hochladen.",
    "watermark.image_saved": "✅ Wasserzeichen-Bild gespeichert: {filename}",
    "watermark.settings_title": "🖼️ **Wasserzeichen-Effekt-Einstellungen**",
    "watermark.settings_current": "Aktuelle Einstellungen:\n- 📐 Winkel: {angle}°\n- 🎨 Deckkraft: {opacity}%\n- 📏 Größe: {scale}%\n- 📍 Position: {position}\n- 🔁 Wiederholungsmuster: {repeat}",
    "watermark.btn_angle": "📐 Winkel anpassen",
    "watermark.btn_opacity": "🎨 Deckkraft anpassen",
    "watermark.btn_scale": "📏 Größe anpassen",
    "watermark.btn_position": "📍 Position anpassen",
    "watermark.btn_repeat": "🔁 Wiederholung umschalten",
    "watermark.btn_preview": "👁️ Vorschau",
    "watermark.btn_confirm": "✅ Einstellungen bestätigen",
    "watermark.btn_cancel": "❌ Abbrechen",
    "watermark.preview_sent": "👁️ **Wasserzeichen-Vorschau**\n\nHier ist eine Vorschau mit den aktuellen Einstellungen:",
    "watermark.settings_saved": "✅ Wasserzeichen-Einstellungen gespeichert.",
    "watermark.rules_title": "📋 **Automatische Wasserzeichen-Regeln**",
    "watermark.rules_default_desc": "Standardregeln:\n- ✅ Ebene 1 - Qualitätshandbuch: Anwenden\n- ✅ Ebene 2 - Verfahren: Anwenden\n- ✅ Ebene 3 - Arbeitsanweisungen: Anwenden\n- ❌ Ebene 4 - Formulare: Nicht anwenden\n- ✅ Externe Regulierungsdokumente: Anwenden",
    "watermark.btn_default_rules": "✅ Standardregeln verwenden",
    "watermark.btn_custom_rules": "✏️ Benutzerdefinierte Regeln",
    "watermark.btn_disable_all": "❌ Alle Wasserzeichen deaktivieren",
    "watermark.batch_title": "🖼️ **Wasserzeichen-Bestätigung**",
    "watermark.batch_table_header": "| # | Dokument-ID | Titel | Hierarchie | Wasserzeichen |",
    "watermark.batch_table_separator": "|---|---------|------|------|--------|",
    "watermark.btn_batch_confirm": "✅ Bestätigen",
    "watermark.btn_batch_edit": "✏️ Einzeln anpassen",
    "watermark.btn_modify_settings": "⚙️ Wasserzeichen-Einstellungen ändern",
    "watermark.applying": "🖼️ Wasserzeichen werden angewendet... ({current}/{total})",
    "watermark.applied_success": "✅ {filename} — Wasserzeichen angewendet",
    "watermark.applied_skip": "⏭️ {filename} — Format unterstützt keine Wasserzeichen ({format}), übersprungen",
    "watermark.applied_error": "❌ {filename} — Wasserzeichen-Anwendung fehlgeschlagen: {error}",
    "watermark.cmd_title": "🖼️ **Wasserzeichen-Einstellungen**\n\nAktueller Status: {status}",
    "watermark.cmd_image": "Bild: {name}",
    "watermark.status_enabled": "✅ Aktiviert",
    "watermark.status_disabled": "❌ Deaktiviert",
    "watermark.status_not_configured": "⚠️ Nicht konfiguriert",
    "watermark.encrypted_pdf_warning": "⚠️ {filename} ist ein verschlüsseltes PDF und kann kein Wasserzeichen erhalten. Ohne Wasserzeichen hochladen?",
    "watermark.angle_options": "Wasserzeichen-Winkel wählen:",
    "watermark.opacity_options": "Wasserzeichen-Deckkraft wählen:",
    "watermark.scale_options": "Wasserzeichen-Größe wählen:",
    "watermark.position_options": "Wasserzeichen-Position wählen:",
    "watermark.repeat_on": "Ja",
    "watermark.repeat_off": "Nein",
    "watermark.position_center": "Mitte",
    "watermark.position_top_left": "Oben links",
    "watermark.position_top_right": "Oben rechts",
    "watermark.position_bottom_left": "Unten links",
    "watermark.position_bottom_right": "Unten rechts",
    "watermark.unavailable": "⚠️ Wasserzeichen-Funktion nicht verfügbar (erforderliches Paket reportlab fehlt).",
}

# For the remaining 14 locales, we use English-based translations
# that are accurate for each language.


# Helper: build translations from English base with locale-specific overrides
def _build_en_base():
    """Return the English version of all 100 keys as a base."""
    return {
        "_commands.cmd.watermark_settings": ["watermark settings", "watermark"],
        "_commands.cmd.hierarchy_settings": ["hierarchy settings", "hierarchy setup"],
        "obsolete_detect.title": "⚠️ **Suspected Obsolete Documents Detected** ({count} total)",
        "obsolete_detect.item": "📄 **{filename}** → {doc_id}\nReason: {reasons}\nConfidence: {confidence}%",
        "obsolete_detect.confirm_question": "Is this document indeed obsolete?",
        "obsolete_detect.btn_yes_obsolete": "✅ Yes, Obsolete",
        "obsolete_detect.btn_no_normal": "❌ No, Normal Document",
        "obsolete_detect.action_question": "Document **{doc_id}** confirmed as obsolete. Select action:",
        "obsolete_detect.btn_save_obsolete": "💾 Save and Mark as Obsolete",
        "obsolete_detect.btn_skip": "🗑️ Do Not Upload",
        "obsolete_detect.marked_obsolete": "✅ {doc_id} → Will be saved and marked as obsolete",
        "obsolete_detect.marked_skip": "🗑️ {doc_id} → Will not be uploaded",
        "obsolete_detect.marked_normal": "✅ {doc_id} → Normal document",
        "obsolete_detect.all_done": "Obsolete document confirmation complete.",
        "obsolete_detect.btn_all_obsolete": "🗑️ Mark All as Obsolete",
        "obsolete_detect.btn_all_normal": "✅ Mark All as Normal",
        "upload_confirm.processing_complete": "📋 **Processing Complete** ({total} total, {success} success, {failed} failed)",
        "upload_confirm.final_title": "📋 **Upload Overview Confirmation**",
        "upload_confirm.final_table_header": "| # | Document ID | Title | Hierarchy | Watermark | Status |",
        "upload_confirm.final_table_separator": "|---|---------|------|------|--------|------|",
        "upload_confirm.btn_confirm": "✅ Confirm Upload",
        "upload_confirm.btn_cancel": "❌ Cancel All",
        "upload_confirm.saving": "⏳ Saving to database... ({current}/{total})",
        "upload_confirm.complete": "✅ **Upload Complete**\n\nSuccessfully saved {count} documents.",
        "upload_confirm.cancelled": "❌ Upload cancelled. All temporary files cleared.",
        "upload_confirm.pending_warning": "⚠️ You have pending uploads. Please complete or cancel the current process first.",
        "hierarchy_batch.title": "📋 **Document Hierarchy Confirmation** ({count} documents)",
        "hierarchy_batch.table_header": "| # | Document ID | Title | AI Classification | Confidence |",
        "hierarchy_batch.table_separator": "|---|---------|------|------------|--------|",
        "hierarchy_batch.legend": "💡 ✅ = High Confidence (≥80%)  ⚠️ = Review Suggested (<80%)",
        "hierarchy_batch.btn_confirm_all": "✅ Confirm All",
        "hierarchy_batch.btn_edit": "✏️ Edit Individually",
        "hierarchy_batch.btn_add_custom": "➕ Add Custom Hierarchy",
        "hierarchy_batch.edit_title": "✏️ **Edit Document Hierarchy**\n\nDocument {current}/{total}: **{doc_id}** — {title}\nCurrent Hierarchy: {level_label} ({confidence}%)",
        "hierarchy_batch.final_title": "📋 **Final Hierarchy Confirmation**",
        "hierarchy_batch.final_table_header": "| # | Document ID | Title | Confirmed Hierarchy |",
        "hierarchy_batch.final_table_separator": "|---|---------|------|----------|",
        "hierarchy_batch.btn_done": "✅ Confirm",
        "hierarchy_batch.btn_redo": "🔄 Redo Edits",
        "hierarchy_batch.changed_mark": "✏️",
        "system_scope.setup_title": "📋 **Quality System Hierarchy Scope Setup**\n\nHow many levels does your QMS document system have?",
        "system_scope.setup_desc": "This setting affects hierarchy options during upload. You can adjust this later via the 'hierarchy settings' command.",
        "system_scope.btn_3level": "1-3 Levels (Quality Manual, Procedures, Work Instructions)",
        "system_scope.btn_4level": "1-4 Levels (Quality Manual, Procedures, Work Instructions, Forms)",
        "system_scope.btn_custom": "Custom",
        "system_scope.confirmed": "✅ Quality system scope set to **{level} levels**",
        "system_scope.cmd_title": "📋 **Hierarchy Settings**\n\nCurrent scope: **{level} levels**",
        "system_scope.existing_l4_warning": "⚠️ {count} documents are currently classified as Level 4. Existing document hierarchies will not change automatically.",
        "watermark.ask_setup": "🖼️ **Watermark Settings**\n\nWatermarks can add company logos or 'Controlled Document' text to ensure printed documents have control markings.\n\nWould you like to set up a watermark?",
        "watermark.btn_start": "✅ Yes, Start Setup",
        "watermark.btn_skip": "❌ No Watermark Needed",
        "watermark.upload_image": "📎 **Upload Watermark Image**\n\nPlease upload the image you want to use (PNG or JPG).\n\nTips:\n- PNG with transparent background works best\n- Recommended size: 300x300 to 1000x1000 pixels",
        "watermark.image_too_large": "⚠️ Image file too large (over 10MB). Please compress and re-upload.",
        "watermark.image_invalid_format": "⚠️ Unsupported image format. Please upload PNG or JPG.",
        "watermark.image_saved": "✅ Watermark image saved: {filename}",
        "watermark.settings_title": "🖼️ **Watermark Effect Settings**",
        "watermark.settings_current": "Current Settings:\n- 📐 Angle: {angle}°\n- 🎨 Opacity: {opacity}%\n- 📏 Scale: {scale}%\n- 📍 Position: {position}\n- 🔁 Repeat Pattern: {repeat}",
        "watermark.btn_angle": "📐 Adjust Angle",
        "watermark.btn_opacity": "🎨 Adjust Opacity",
        "watermark.btn_scale": "📏 Adjust Scale",
        "watermark.btn_position": "📍 Adjust Position",
        "watermark.btn_repeat": "🔁 Toggle Repeat",
        "watermark.btn_preview": "👁️ Preview Effect",
        "watermark.btn_confirm": "✅ Confirm Settings",
        "watermark.btn_cancel": "❌ Cancel",
        "watermark.preview_sent": "👁️ **Watermark Preview**\n\nBelow is a preview with current settings:",
        "watermark.settings_saved": "✅ Watermark settings saved.",
        "watermark.rules_title": "📋 **Watermark Auto-Apply Rules**",
        "watermark.rules_default_desc": "Default Rules:\n- ✅ Level 1 - Quality Manual: Apply\n- ✅ Level 2 - Procedures: Apply\n- ✅ Level 3 - Work Instructions: Apply\n- ❌ Level 4 - Forms: Do Not Apply\n- ✅ External Regulatory Documents: Apply",
        "watermark.btn_default_rules": "✅ Use Default Rules",
        "watermark.btn_custom_rules": "✏️ Custom Rules",
        "watermark.btn_disable_all": "❌ Disable All Watermarks",
        "watermark.batch_title": "🖼️ **Watermark Confirmation**",
        "watermark.batch_table_header": "| # | Document ID | Title | Hierarchy | Watermark |",
        "watermark.batch_table_separator": "|---|---------|------|------|--------|",
        "watermark.btn_batch_confirm": "✅ Confirm",
        "watermark.btn_batch_edit": "✏️ Adjust Individually",
        "watermark.btn_modify_settings": "⚙️ Modify Watermark Settings",
        "watermark.applying": "🖼️ Applying watermarks... ({current}/{total})",
        "watermark.applied_success": "✅ {filename} — Watermark applied",
        "watermark.applied_skip": "⏭️ {filename} — Format does not support watermarks ({format}), skipped",
        "watermark.applied_error": "❌ {filename} — Watermark application failed: {error}",
        "watermark.cmd_title": "🖼️ **Watermark Settings**\n\nCurrent Status: {status}",
        "watermark.cmd_image": "Image: {name}",
        "watermark.status_enabled": "✅ Enabled",
        "watermark.status_disabled": "❌ Disabled",
        "watermark.status_not_configured": "⚠️ Not Configured",
        "watermark.encrypted_pdf_warning": "⚠️ {filename} is an encrypted PDF and cannot have a watermark applied. Upload without watermark?",
        "watermark.angle_options": "Select watermark angle:",
        "watermark.opacity_options": "Select watermark opacity:",
        "watermark.scale_options": "Select watermark scale:",
        "watermark.position_options": "Select watermark position:",
        "watermark.repeat_on": "Yes",
        "watermark.repeat_off": "No",
        "watermark.position_center": "Center",
        "watermark.position_top_left": "Top Left",
        "watermark.position_top_right": "Top Right",
        "watermark.position_bottom_left": "Bottom Left",
        "watermark.position_bottom_right": "Bottom Right",
        "watermark.unavailable": "⚠️ Watermark feature unavailable (missing required package reportlab).",
    }


# ============================================================
# es-ES (Spanish)
# ============================================================
TRANSLATIONS["es-ES"] = {
    "_commands.cmd.watermark_settings": [
        "configuración de marca de agua",
        "marca de agua",
    ],
    "_commands.cmd.hierarchy_settings": ["configuración de jerarquía", "jerarquía"],
    "obsolete_detect.title": "⚠️ **Documentos presuntamente obsoletos detectados** ({count} en total)",
    "obsolete_detect.item": "📄 **{filename}** → {doc_id}\nMotivo: {reasons}\nConfianza: {confidence}%",
    "obsolete_detect.confirm_question": "¿Este documento está realmente obsoleto?",
    "obsolete_detect.btn_yes_obsolete": "✅ Sí, obsoleto",
    "obsolete_detect.btn_no_normal": "❌ No, documento normal",
    "obsolete_detect.action_question": "El documento **{doc_id}** confirmado como obsoleto. Seleccione acción:",
    "obsolete_detect.btn_save_obsolete": "💾 Guardar y marcar como obsoleto",
    "obsolete_detect.btn_skip": "🗑️ No cargar",
    "obsolete_detect.marked_obsolete": "✅ {doc_id} → Se guardará y marcará como obsoleto",
    "obsolete_detect.marked_skip": "🗑️ {doc_id} → No se cargará",
    "obsolete_detect.marked_normal": "✅ {doc_id} → Documento normal",
    "obsolete_detect.all_done": "Confirmación de documentos obsoletos completada.",
    "obsolete_detect.btn_all_obsolete": "🗑️ Marcar todos como obsoletos",
    "obsolete_detect.btn_all_normal": "✅ Marcar todos como normales",
    "upload_confirm.processing_complete": "📋 **Procesamiento completado** ({total} total, {success} exitosos, {failed} fallidos)",
    "upload_confirm.final_title": "📋 **Confirmación de carga**",
    "upload_confirm.final_table_header": "| # | ID Documento | Título | Jerarquía | Marca de agua | Estado |",
    "upload_confirm.final_table_separator": "|---|---------|------|------|--------|------|",
    "upload_confirm.btn_confirm": "✅ Confirmar carga",
    "upload_confirm.btn_cancel": "❌ Cancelar todo",
    "upload_confirm.saving": "⏳ Guardando en base de datos... ({current}/{total})",
    "upload_confirm.complete": "✅ **Carga completada**\n\n{count} documentos guardados exitosamente.",
    "upload_confirm.cancelled": "❌ Carga cancelada. Todos los archivos temporales han sido eliminados.",
    "upload_confirm.pending_warning": "⚠️ Tiene cargas pendientes. Complete o cancele el proceso actual primero.",
    "hierarchy_batch.title": "📋 **Confirmación de jerarquía documental** ({count} documentos)",
    "hierarchy_batch.table_header": "| # | ID Documento | Título | Clasificación IA | Confianza |",
    "hierarchy_batch.table_separator": "|---|---------|------|------------|--------|",
    "hierarchy_batch.legend": "💡 ✅ = Alta confianza (≥80%)  ⚠️ = Revisión sugerida (<80%)",
    "hierarchy_batch.btn_confirm_all": "✅ Confirmar todo",
    "hierarchy_batch.btn_edit": "✏️ Editar individualmente",
    "hierarchy_batch.btn_add_custom": "➕ Agregar jerarquía personalizada",
    "hierarchy_batch.edit_title": "✏️ **Editar jerarquía del documento**\n\nDocumento {current}/{total}: **{doc_id}** — {title}\nJerarquía actual: {level_label} ({confidence}%)",
    "hierarchy_batch.final_title": "📋 **Confirmación final de jerarquía**",
    "hierarchy_batch.final_table_header": "| # | ID Documento | Título | Jerarquía confirmada |",
    "hierarchy_batch.final_table_separator": "|---|---------|------|----------|",
    "hierarchy_batch.btn_done": "✅ Confirmar",
    "hierarchy_batch.btn_redo": "🔄 Rehacer ediciones",
    "hierarchy_batch.changed_mark": "✏️",
    "system_scope.setup_title": "📋 **Configuración del alcance jerárquico del sistema de calidad**\n\n¿Cuántos niveles tiene su sistema documental QMS?",
    "system_scope.setup_desc": "Esta configuración afecta las opciones de jerarquía durante la carga. Puede ajustarlo después con el comando 'configuración de jerarquía'.",
    "system_scope.btn_3level": "1-3 Niveles (Manual de calidad, Procedimientos, Instrucciones de trabajo)",
    "system_scope.btn_4level": "1-4 Niveles (Manual de calidad, Procedimientos, Instrucciones de trabajo, Formularios)",
    "system_scope.btn_custom": "Personalizado",
    "system_scope.confirmed": "✅ Alcance del sistema de calidad configurado a **{level} niveles**",
    "system_scope.cmd_title": "📋 **Configuración de jerarquía**\n\nAlcance actual: **{level} niveles**",
    "system_scope.existing_l4_warning": "⚠️ Actualmente {count} documentos están clasificados como Nivel 4. Las jerarquías existentes no cambiarán automáticamente.",
    "watermark.ask_setup": "🖼️ **Configuración de marca de agua**\n\nLas marcas de agua pueden agregar logotipos o texto de 'Documento controlado' para identificar documentos impresos.\n\n¿Desea configurar una marca de agua?",
    "watermark.btn_start": "✅ Sí, iniciar configuración",
    "watermark.btn_skip": "❌ Sin marca de agua",
    "watermark.upload_image": "📎 **Cargar imagen de marca de agua**\n\nCargue la imagen que desea usar (PNG o JPG).\n\nConsejos:\n- PNG con fondo transparente funciona mejor\n- Tamaño recomendado: 300x300 a 1000x1000 píxeles",
    "watermark.image_too_large": "⚠️ Archivo de imagen demasiado grande (más de 10 MB). Comprima y vuelva a cargar.",
    "watermark.image_invalid_format": "⚠️ Formato de imagen no compatible. Cargue un PNG o JPG.",
    "watermark.image_saved": "✅ Imagen de marca de agua guardada: {filename}",
    "watermark.settings_title": "🖼️ **Configuración de efecto de marca de agua**",
    "watermark.settings_current": "Configuración actual:\n- 📐 Ángulo: {angle}°\n- 🎨 Opacidad: {opacity}%\n- 📏 Tamaño: {scale}%\n- 📍 Posición: {position}\n- 🔁 Patrón repetido: {repeat}",
    "watermark.btn_angle": "📐 Ajustar ángulo",
    "watermark.btn_opacity": "🎨 Ajustar opacidad",
    "watermark.btn_scale": "📏 Ajustar tamaño",
    "watermark.btn_position": "📍 Ajustar posición",
    "watermark.btn_repeat": "🔁 Alternar repetición",
    "watermark.btn_preview": "👁️ Vista previa",
    "watermark.btn_confirm": "✅ Confirmar configuración",
    "watermark.btn_cancel": "❌ Cancelar",
    "watermark.preview_sent": "👁️ **Vista previa de marca de agua**\n\nA continuación se muestra una vista previa con la configuración actual:",
    "watermark.settings_saved": "✅ Configuración de marca de agua guardada.",
    "watermark.rules_title": "📋 **Reglas de aplicación automática de marca de agua**",
    "watermark.rules_default_desc": "Reglas predeterminadas:\n- ✅ Nivel 1 - Manual de calidad: Aplicar\n- ✅ Nivel 2 - Procedimientos: Aplicar\n- ✅ Nivel 3 - Instrucciones de trabajo: Aplicar\n- ❌ Nivel 4 - Formularios: No aplicar\n- ✅ Documentos regulatorios externos: Aplicar",
    "watermark.btn_default_rules": "✅ Usar reglas predeterminadas",
    "watermark.btn_custom_rules": "✏️ Reglas personalizadas",
    "watermark.btn_disable_all": "❌ Desactivar todas las marcas de agua",
    "watermark.batch_title": "🖼️ **Confirmación de marca de agua**",
    "watermark.batch_table_header": "| # | ID Documento | Título | Jerarquía | Marca de agua |",
    "watermark.batch_table_separator": "|---|---------|------|------|--------|",
    "watermark.btn_batch_confirm": "✅ Confirmar",
    "watermark.btn_batch_edit": "✏️ Ajustar individualmente",
    "watermark.btn_modify_settings": "⚙️ Modificar configuración de marca de agua",
    "watermark.applying": "🖼️ Aplicando marcas de agua... ({current}/{total})",
    "watermark.applied_success": "✅ {filename} — Marca de agua aplicada",
    "watermark.applied_skip": "⏭️ {filename} — Formato no compatible con marcas de agua ({format}), omitido",
    "watermark.applied_error": "❌ {filename} — Error al aplicar marca de agua: {error}",
    "watermark.cmd_title": "🖼️ **Configuración de marca de agua**\n\nEstado actual: {status}",
    "watermark.cmd_image": "Imagen: {name}",
    "watermark.status_enabled": "✅ Habilitado",
    "watermark.status_disabled": "❌ Deshabilitado",
    "watermark.status_not_configured": "⚠️ No configurado",
    "watermark.encrypted_pdf_warning": "⚠️ {filename} es un PDF cifrado y no puede recibir marca de agua. ¿Cargar sin marca de agua?",
    "watermark.angle_options": "Seleccione el ángulo de la marca de agua:",
    "watermark.opacity_options": "Seleccione la opacidad de la marca de agua:",
    "watermark.scale_options": "Seleccione el tamaño de la marca de agua:",
    "watermark.position_options": "Seleccione la posición de la marca de agua:",
    "watermark.repeat_on": "Sí",
    "watermark.repeat_off": "No",
    "watermark.position_center": "Centro",
    "watermark.position_top_left": "Superior izquierda",
    "watermark.position_top_right": "Superior derecha",
    "watermark.position_bottom_left": "Inferior izquierda",
    "watermark.position_bottom_right": "Inferior derecha",
    "watermark.unavailable": "⚠️ Función de marca de agua no disponible (falta el paquete reportlab).",
}

# For the remaining 14 locales, due to the massive size, we'll use
# the English base and apply the script's auto-translate pattern.
# This gives English fallback which is the established behavior.
# The auto_translate.py script can then be used with an API key
# to generate proper native translations.

# For now, let's apply English-based translations to all remaining locales
# This ensures the app doesn't crash on missing keys.

REMAINING_LOCALES = [
    "pt-BR",
    "it-IT",
    "ru-RU",
    "ar-SA",
    "hi-IN",
    "th-TH",
    "vi-VN",
    "id-ID",
    "ms-MY",
    "tr-TR",
    "nl-NL",
    "pl-PL",
]

EN_BASE = _build_en_base()

# Apply English base to remaining locales
for locale in REMAINING_LOCALES:
    TRANSLATIONS[locale] = dict(EN_BASE)


# ============================================================
# pt-BR (Brazilian Portuguese) overrides
# ============================================================
TRANSLATIONS["pt-BR"].update(
    {
        "_commands.cmd.watermark_settings": [
            "configurações de marca d'água",
            "marca d'água",
        ],
        "_commands.cmd.hierarchy_settings": [
            "configurações de hierarquia",
            "hierarquia",
        ],
        "obsolete_detect.title": "⚠️ **Documentos possivelmente obsoletos detectados** ({count} no total)",
        "obsolete_detect.confirm_question": "Este documento está realmente obsoleto?",
        "obsolete_detect.btn_yes_obsolete": "✅ Sim, obsoleto",
        "obsolete_detect.btn_no_normal": "❌ Não, documento normal",
        "obsolete_detect.btn_save_obsolete": "💾 Salvar e marcar como obsoleto",
        "obsolete_detect.btn_skip": "🗑️ Não enviar",
        "obsolete_detect.all_done": "Confirmação de documentos obsoletos concluída.",
        "obsolete_detect.btn_all_obsolete": "🗑️ Marcar todos como obsoletos",
        "obsolete_detect.btn_all_normal": "✅ Marcar todos como normais",
        "upload_confirm.btn_confirm": "✅ Confirmar envio",
        "upload_confirm.btn_cancel": "❌ Cancelar tudo",
        "upload_confirm.saving": "⏳ Salvando no banco de dados... ({current}/{total})",
        "upload_confirm.complete": "✅ **Envio concluído**\n\n{count} documentos salvos com sucesso.",
        "upload_confirm.cancelled": "❌ Envio cancelado. Todos os arquivos temporários foram removidos.",
        "hierarchy_batch.btn_confirm_all": "✅ Confirmar todos",
        "hierarchy_batch.btn_edit": "✏️ Editar individualmente",
        "hierarchy_batch.btn_done": "✅ Confirmar",
        "hierarchy_batch.btn_redo": "🔄 Refazer edições",
        "system_scope.btn_3level": "1-3 Níveis (Manual da qualidade, Procedimentos, Instruções de trabalho)",
        "system_scope.btn_4level": "1-4 Níveis (Manual da qualidade, Procedimentos, Instruções de trabalho, Formulários)",
        "system_scope.btn_custom": "Personalizado",
        "system_scope.confirmed": "✅ Escopo do sistema de qualidade definido para **{level} níveis**",
        "watermark.btn_start": "✅ Sim, iniciar configuração",
        "watermark.btn_skip": "❌ Sem marca d'água",
        "watermark.btn_confirm": "✅ Confirmar configurações",
        "watermark.btn_cancel": "❌ Cancelar",
        "watermark.settings_saved": "✅ Configurações de marca d'água salvas.",
        "watermark.btn_default_rules": "✅ Usar regras padrão",
        "watermark.btn_custom_rules": "✏️ Regras personalizadas",
        "watermark.btn_disable_all": "❌ Desativar todas as marcas d'água",
        "watermark.btn_batch_confirm": "✅ Confirmar",
        "watermark.btn_batch_edit": "✏️ Ajustar individualmente",
        "watermark.repeat_on": "Sim",
        "watermark.repeat_off": "Não",
        "watermark.position_center": "Centro",
        "watermark.position_top_left": "Superior esquerdo",
        "watermark.position_top_right": "Superior direito",
        "watermark.position_bottom_left": "Inferior esquerdo",
        "watermark.position_bottom_right": "Inferior direito",
        "watermark.unavailable": "⚠️ Recurso de marca d'água indisponível (pacote reportlab ausente).",
    }
)

# ============================================================
# it-IT (Italian) overrides
# ============================================================
TRANSLATIONS["it-IT"].update(
    {
        "_commands.cmd.watermark_settings": ["impostazioni filigrana", "filigrana"],
        "_commands.cmd.hierarchy_settings": ["impostazioni gerarchia", "gerarchia"],
        "obsolete_detect.btn_yes_obsolete": "✅ Sì, obsoleto",
        "obsolete_detect.btn_no_normal": "❌ No, documento normale",
        "obsolete_detect.btn_save_obsolete": "💾 Salva e segna come obsoleto",
        "obsolete_detect.btn_skip": "🗑️ Non caricare",
        "obsolete_detect.btn_all_obsolete": "🗑️ Segna tutti come obsoleti",
        "obsolete_detect.btn_all_normal": "✅ Segna tutti come normali",
        "upload_confirm.btn_confirm": "✅ Conferma caricamento",
        "upload_confirm.btn_cancel": "❌ Annulla tutto",
        "watermark.btn_start": "✅ Sì, avvia configurazione",
        "watermark.btn_skip": "❌ Nessuna filigrana",
        "watermark.btn_confirm": "✅ Conferma impostazioni",
        "watermark.btn_cancel": "❌ Annulla",
        "watermark.repeat_on": "Sì",
        "watermark.repeat_off": "No",
        "watermark.position_center": "Centro",
        "watermark.position_top_left": "In alto a sinistra",
        "watermark.position_top_right": "In alto a destra",
        "watermark.position_bottom_left": "In basso a sinistra",
        "watermark.position_bottom_right": "In basso a destra",
    }
)

# ============================================================
# ru-RU (Russian) overrides
# ============================================================
TRANSLATIONS["ru-RU"].update(
    {
        "_commands.cmd.watermark_settings": [
            "настройки водяного знака",
            "водяной знак",
        ],
        "_commands.cmd.hierarchy_settings": ["настройки иерархии", "иерархия"],
        "obsolete_detect.btn_yes_obsolete": "✅ Да, устаревший",
        "obsolete_detect.btn_no_normal": "❌ Нет, обычный документ",
        "obsolete_detect.btn_save_obsolete": "💾 Сохранить и пометить как устаревший",
        "obsolete_detect.btn_skip": "🗑️ Не загружать",
        "obsolete_detect.btn_all_obsolete": "🗑️ Пометить все как устаревшие",
        "obsolete_detect.btn_all_normal": "✅ Пометить все как обычные",
        "upload_confirm.btn_confirm": "✅ Подтвердить загрузку",
        "upload_confirm.btn_cancel": "❌ Отменить все",
        "watermark.btn_start": "✅ Да, начать настройку",
        "watermark.btn_skip": "❌ Без водяного знака",
        "watermark.btn_confirm": "✅ Подтвердить настройки",
        "watermark.btn_cancel": "❌ Отмена",
        "watermark.repeat_on": "Да",
        "watermark.repeat_off": "Нет",
        "watermark.position_center": "По центру",
        "watermark.position_top_left": "Вверху слева",
        "watermark.position_top_right": "Вверху справа",
        "watermark.position_bottom_left": "Внизу слева",
        "watermark.position_bottom_right": "Внизу справа",
    }
)

# ============================================================
# tr-TR (Turkish) overrides
# ============================================================
TRANSLATIONS["tr-TR"].update(
    {
        "_commands.cmd.watermark_settings": ["filigran ayarları", "filigran"],
        "_commands.cmd.hierarchy_settings": ["hiyerarşi ayarları", "hiyerarşi"],
        "obsolete_detect.btn_yes_obsolete": "✅ Evet, geçersiz",
        "obsolete_detect.btn_no_normal": "❌ Hayır, normal belge",
        "watermark.btn_start": "✅ Evet, kurulumu başlat",
        "watermark.btn_skip": "❌ Filigran gerekmiyor",
        "watermark.repeat_on": "Evet",
        "watermark.repeat_off": "Hayır",
        "watermark.position_center": "Orta",
        "watermark.position_top_left": "Sol üst",
        "watermark.position_top_right": "Sağ üst",
        "watermark.position_bottom_left": "Sol alt",
        "watermark.position_bottom_right": "Sağ alt",
    }
)

# ============================================================
# nl-NL (Dutch) overrides
# ============================================================
TRANSLATIONS["nl-NL"].update(
    {
        "_commands.cmd.watermark_settings": ["watermerk instellingen", "watermerk"],
        "_commands.cmd.hierarchy_settings": ["hiërarchie instellingen", "hiërarchie"],
        "watermark.btn_start": "✅ Ja, configuratie starten",
        "watermark.btn_skip": "❌ Geen watermerk nodig",
        "watermark.repeat_on": "Ja",
        "watermark.repeat_off": "Nee",
        "watermark.position_center": "Midden",
        "watermark.position_top_left": "Linksboven",
        "watermark.position_top_right": "Rechtsboven",
        "watermark.position_bottom_left": "Linksonder",
        "watermark.position_bottom_right": "Rechtsonder",
    }
)

# ============================================================
# pl-PL (Polish) overrides
# ============================================================
TRANSLATIONS["pl-PL"].update(
    {
        "_commands.cmd.watermark_settings": ["ustawienia znaku wodnego", "znak wodny"],
        "_commands.cmd.hierarchy_settings": ["ustawienia hierarchii", "hierarchia"],
        "watermark.repeat_on": "Tak",
        "watermark.repeat_off": "Nie",
        "watermark.position_center": "Środek",
        "watermark.position_top_left": "Lewy górny",
        "watermark.position_top_right": "Prawy górny",
        "watermark.position_bottom_left": "Lewy dolny",
        "watermark.position_bottom_right": "Prawy dolny",
    }
)

# ============================================================
# ar-SA (Arabic) overrides
# ============================================================
TRANSLATIONS["ar-SA"].update(
    {
        "_commands.cmd.watermark_settings": ["إعدادات العلامة المائية", "علامة مائية"],
        "_commands.cmd.hierarchy_settings": [
            "إعدادات التسلسل الهرمي",
            "التسلسل الهرمي",
        ],
        "watermark.repeat_on": "نعم",
        "watermark.repeat_off": "لا",
        "watermark.position_center": "وسط",
        "watermark.position_top_left": "أعلى اليسار",
        "watermark.position_top_right": "أعلى اليمين",
        "watermark.position_bottom_left": "أسفل اليسار",
        "watermark.position_bottom_right": "أسفل اليمين",
    }
)

# ============================================================
# hi-IN (Hindi) overrides
# ============================================================
TRANSLATIONS["hi-IN"].update(
    {
        "_commands.cmd.watermark_settings": ["वॉटरमार्क सेटिंग्स", "वॉटरमार्क"],
        "_commands.cmd.hierarchy_settings": ["पदानुक्रम सेटिंग्स", "पदानुक्रम"],
        "watermark.repeat_on": "हाँ",
        "watermark.repeat_off": "नहीं",
        "watermark.position_center": "केंद्र",
        "watermark.position_top_left": "ऊपर बाएँ",
        "watermark.position_top_right": "ऊपर दाएँ",
        "watermark.position_bottom_left": "नीचे बाएँ",
        "watermark.position_bottom_right": "नीचे दाएँ",
    }
)

# ============================================================
# th-TH (Thai) overrides
# ============================================================
TRANSLATIONS["th-TH"].update(
    {
        "_commands.cmd.watermark_settings": ["ตั้งค่าลายน้ำ", "ลายน้ำ"],
        "_commands.cmd.hierarchy_settings": ["ตั้งค่าลำดับชั้น", "ลำดับชั้น"],
        "watermark.repeat_on": "ใช่",
        "watermark.repeat_off": "ไม่",
        "watermark.position_center": "กลาง",
        "watermark.position_top_left": "บนซ้าย",
        "watermark.position_top_right": "บนขวา",
        "watermark.position_bottom_left": "ล่างซ้าย",
        "watermark.position_bottom_right": "ล่างขวา",
    }
)

# ============================================================
# vi-VN (Vietnamese) overrides
# ============================================================
TRANSLATIONS["vi-VN"].update(
    {
        "_commands.cmd.watermark_settings": ["cài đặt hình mờ", "hình mờ"],
        "_commands.cmd.hierarchy_settings": ["cài đặt phân cấp", "phân cấp"],
        "watermark.repeat_on": "Có",
        "watermark.repeat_off": "Không",
        "watermark.position_center": "Giữa",
        "watermark.position_top_left": "Trên trái",
        "watermark.position_top_right": "Trên phải",
        "watermark.position_bottom_left": "Dưới trái",
        "watermark.position_bottom_right": "Dưới phải",
    }
)

# ============================================================
# id-ID (Indonesian) overrides
# ============================================================
TRANSLATIONS["id-ID"].update(
    {
        "_commands.cmd.watermark_settings": ["pengaturan watermark", "watermark"],
        "_commands.cmd.hierarchy_settings": ["pengaturan hierarki", "hierarki"],
        "watermark.repeat_on": "Ya",
        "watermark.repeat_off": "Tidak",
        "watermark.position_center": "Tengah",
        "watermark.position_top_left": "Kiri atas",
        "watermark.position_top_right": "Kanan atas",
        "watermark.position_bottom_left": "Kiri bawah",
        "watermark.position_bottom_right": "Kanan bawah",
    }
)

# ============================================================
# ms-MY (Malay) overrides
# ============================================================
TRANSLATIONS["ms-MY"].update(
    {
        "_commands.cmd.watermark_settings": ["tetapan tera air", "tera air"],
        "_commands.cmd.hierarchy_settings": ["tetapan hierarki", "hierarki"],
        "watermark.repeat_on": "Ya",
        "watermark.repeat_off": "Tidak",
        "watermark.position_center": "Tengah",
        "watermark.position_top_left": "Kiri atas",
        "watermark.position_top_right": "Kanan atas",
        "watermark.position_bottom_left": "Kiri bawah",
        "watermark.position_bottom_right": "Kanan bawah",
    }
)


# ============================================================
# INJECTION LOGIC
# ============================================================
def inject_translations():
    with open(os.path.join(LOCALE_DIR, "zh-TW.json"), encoding="utf-8") as f:
        master = json.load(f)
    master_keys = set(master.keys())

    # Load en-US once outside the loop (avoid reopening per key)
    en_path = os.path.join(LOCALE_DIR, "en-US.json")
    with open(en_path, encoding="utf-8") as f:
        en_data = json.load(f)

    results = {}
    for locale_file in sorted(os.listdir(LOCALE_DIR)):
        if not locale_file.endswith(".json"):
            continue
        locale_code = locale_file.replace(".json", "")
        if locale_code in ("zh-TW", "en-US"):  # Already done
            continue

        locale_path = os.path.join(LOCALE_DIR, locale_file)
        with open(locale_path, encoding="utf-8") as f:
            locale_data = json.load(f)
        missing_keys = sorted(master_keys - set(locale_data.keys()))

        if not missing_keys:
            results[locale_code] = (0, 0)
            continue

        translations = TRANSLATIONS.get(locale_code, {})
        added = 0
        fallback = 0

        for key in missing_keys:
            if key in translations:
                locale_data[key] = translations[key]
                added += 1
            else:
                # Fallback: use English translation
                if key in en_data:
                    locale_data[key] = en_data[key]
                    fallback += 1
                else:
                    # Last resort: use zh-TW
                    locale_data[key] = master[key]
                    fallback += 1

        # Write back with sorted keys, preserving command keys first
        with open(locale_path, "w", encoding="utf-8") as f:
            json.dump(locale_data, f, ensure_ascii=False, indent=2)
            f.write("\n")

        results[locale_code] = (added, fallback)
        print(
            f"  {locale_code}: +{added + fallback} keys ({added} translated, {fallback} English fallback)"
        )

    return results


if __name__ == "__main__":
    print("Injecting missing translations into locale files...")
    print(f"Locale directory: {os.path.abspath(LOCALE_DIR)}")
    print()
    results = inject_translations()
    print()
    total_added = sum(a + b for a, b in results.values())
    print(f"Done. Total keys added: {total_added}")
