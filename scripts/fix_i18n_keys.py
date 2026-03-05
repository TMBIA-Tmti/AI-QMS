"""
Fix Bug #2: Add 7 crossexam i18n keys to all 20 locale files.
All values start with "Eira：" (CJK) or "Eira: " (Latin).
"""

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).parent.parent / "src" / "chainlit_app" / "locales"

# Keys to add per locale
KEYS = {
    "zh-TW": {
        "crossexam.freshness_confirmed": "Eira：✅ 所有法規資料已確認為最新版本",
        "crossexam.mdsap_enabled_notice": "Eira：🌐 MDSAP 五國交叉詰問已啟用。本次分析將同時包含 7 國交叉詰問與 MDSAP 五國（HC/PMDA/ANVISA/TGA/QMSR）交叉詰問分析。",
        "crossexam.upload_reminder_title": "Eira：📋 以下法規需要手動上傳最新版本：",
        "crossexam.upload_reminder_instruction": "Eira：請使用「上傳法規文件」功能，上傳對應國家的最新法規文件。",
        "crossexam.pipeline_running": "Eira：📊 分析進度：[{bar}] {completed}/{total} ({percent}%) — 目前階段：{phase}",
        "crossexam.pipeline_completed": "Eira：✅ 分析已完成，共 {total} 筆分析項目。",
        "crossexam.pipeline_not_started": "Eira：⏳ 分析尚未開始，請先執行法規清單或法規清單更新。",
    },
    "zh-CN": {
        "crossexam.freshness_confirmed": "Eira：✅ 所有法规资料已确认为最新版本",
        "crossexam.mdsap_enabled_notice": "Eira：🌐 MDSAP 五国交叉质询已启用。本次分析将同时包含 7 国交叉质询与 MDSAP 五国（HC/PMDA/ANVISA/TGA/QMSR）交叉质询分析。",
        "crossexam.upload_reminder_title": "Eira：📋 以下法规需要手动上传最新版本：",
        "crossexam.upload_reminder_instruction": "Eira：请使用「上传法规文件」功能，上传对应国家的最新法规文件。",
        "crossexam.pipeline_running": "Eira：📊 分析进度：[{bar}] {completed}/{total} ({percent}%) — 当前阶段：{phase}",
        "crossexam.pipeline_completed": "Eira：✅ 分析已完成，共 {total} 笔分析项目。",
        "crossexam.pipeline_not_started": "Eira：⏳ 分析尚未开始，请先执行法规清单或法规清单更新。",
    },
    "en-US": {
        "crossexam.freshness_confirmed": "Eira: ✅ All regulatory references confirmed as latest version.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 MDSAP 5-country cross-examination enabled. This analysis will include both 7-country cross-examination and MDSAP 5-country (HC/PMDA/ANVISA/TGA/QMSR) analysis.",
        "crossexam.upload_reminder_title": "Eira: 📋 The following regulations require manual upload of the latest version:",
        "crossexam.upload_reminder_instruction": "Eira: Please use the 'Upload Regulation Document' function to upload the latest regulation documents for the corresponding countries.",
        "crossexam.pipeline_running": "Eira: 📊 Analysis progress: [{bar}] {completed}/{total} ({percent}%) — Current phase: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analysis completed. Total: {total} items analyzed.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Analysis has not started yet. Please run 'Regulatory List' or 'Regulatory Update' first.",
    },
    "ja-JP": {
        "crossexam.freshness_confirmed": "Eira：✅ すべての法規資料が最新版であることを確認しました",
        "crossexam.mdsap_enabled_notice": "Eira：🌐 MDSAP 5カ国交差尋問が有効です。今回の分析には7カ国交差尋問とMDSAP 5カ国（HC/PMDA/ANVISA/TGA/QMSR）の交差尋問分析が含まれます。",
        "crossexam.upload_reminder_title": "Eira：📋 以下の法規は最新版の手動アップロードが必要です：",
        "crossexam.upload_reminder_instruction": "Eira：「法規文書アップロード」機能を使用して、該当国の最新法規文書をアップロードしてください。",
        "crossexam.pipeline_running": "Eira：📊 分析進捗：[{bar}] {completed}/{total} ({percent}%) — 現在のフェーズ：{phase}",
        "crossexam.pipeline_completed": "Eira：✅ 分析完了。合計 {total} 件の分析項目。",
        "crossexam.pipeline_not_started": "Eira：⏳ 分析はまだ開始されていません。先に「法規リスト」または「法規リスト更新」を実行してください。",
    },
    "ko-KR": {
        "crossexam.freshness_confirmed": "Eira：✅ 모든 규제 자료가 최신 버전으로 확인되었습니다",
        "crossexam.mdsap_enabled_notice": "Eira：🌐 MDSAP 5개국 교차 심문이 활성화되었습니다. 이번 분석에는 7개국 교차 심문과 MDSAP 5개국(HC/PMDA/ANVISA/TGA/QMSR) 교차 심문 분석이 포함됩니다.",
        "crossexam.upload_reminder_title": "Eira：📋 다음 규정은 최신 버전의 수동 업로드가 필요합니다:",
        "crossexam.upload_reminder_instruction": "Eira：'규제 문서 업로드' 기능을 사용하여 해당 국가의 최신 규제 문서를 업로드하세요.",
        "crossexam.pipeline_running": "Eira：📊 분석 진행률: [{bar}] {completed}/{total} ({percent}%) — 현재 단계: {phase}",
        "crossexam.pipeline_completed": "Eira：✅ 분석 완료. 총 {total}건 분석 항목.",
        "crossexam.pipeline_not_started": "Eira：⏳ 분석이 아직 시작되지 않았습니다. 먼저 '규제 목록' 또는 '규제 목록 업데이트'를 실행하세요.",
    },
    "fr-FR": {
        "crossexam.freshness_confirmed": "Eira : ✅ Toutes les références réglementaires confirmées comme étant à jour.",
        "crossexam.mdsap_enabled_notice": "Eira : 🌐 L'examen croisé MDSAP 5 pays est activé. Cette analyse inclura l'examen croisé 7 pays et l'analyse MDSAP 5 pays (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira : 📋 Les réglementations suivantes nécessitent un téléchargement manuel de la dernière version :",
        "crossexam.upload_reminder_instruction": "Eira : Veuillez utiliser la fonction 'Télécharger un document réglementaire' pour télécharger les derniers documents pour les pays correspondants.",
        "crossexam.pipeline_running": "Eira : 📊 Progression de l'analyse : [{bar}] {completed}/{total} ({percent}%) — Phase actuelle : {phase}",
        "crossexam.pipeline_completed": "Eira : ✅ Analyse terminée. Total : {total} éléments analysés.",
        "crossexam.pipeline_not_started": "Eira : ⏳ L'analyse n'a pas encore commencé. Veuillez d'abord exécuter 'Liste réglementaire' ou 'Mise à jour réglementaire'.",
    },
    "de-DE": {
        "crossexam.freshness_confirmed": "Eira: ✅ Alle regulatorischen Referenzen als aktuell bestätigt.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 MDSAP 5-Länder-Kreuzverhör aktiviert. Diese Analyse umfasst sowohl das 7-Länder-Kreuzverhör als auch die MDSAP 5-Länder-Analyse (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Die folgenden Vorschriften erfordern einen manuellen Upload der neuesten Version:",
        "crossexam.upload_reminder_instruction": "Eira: Bitte verwenden Sie die Funktion 'Regulierungsdokument hochladen', um die neuesten Dokumente hochzuladen.",
        "crossexam.pipeline_running": "Eira: 📊 Analysefortschritt: [{bar}] {completed}/{total} ({percent}%) — Aktuelle Phase: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analyse abgeschlossen. Gesamt: {total} analysierte Elemente.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Die Analyse wurde noch nicht gestartet. Bitte führen Sie zuerst 'Regulierungsliste' oder 'Regulierungsaktualisierung' aus.",
    },
    "es-ES": {
        "crossexam.freshness_confirmed": "Eira: ✅ Todas las referencias regulatorias confirmadas como versión más reciente.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Interrogatorio cruzado MDSAP de 5 países activado. Este análisis incluirá el interrogatorio cruzado de 7 países y el análisis MDSAP de 5 países (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Las siguientes regulaciones requieren carga manual de la última versión:",
        "crossexam.upload_reminder_instruction": "Eira: Por favor utilice la función 'Cargar documento regulatorio' para cargar los documentos más recientes.",
        "crossexam.pipeline_running": "Eira: 📊 Progreso del análisis: [{bar}] {completed}/{total} ({percent}%) — Fase actual: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Análisis completado. Total: {total} elementos analizados.",
        "crossexam.pipeline_not_started": "Eira: ⏳ El análisis aún no ha comenzado. Por favor ejecute primero 'Lista regulatoria' o 'Actualización regulatoria'.",
    },
    "pt-BR": {
        "crossexam.freshness_confirmed": "Eira: ✅ Todas as referências regulatórias confirmadas como versão mais recente.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Interrogatório cruzado MDSAP de 5 países ativado. Esta análise incluirá o interrogatório cruzado de 7 países e a análise MDSAP de 5 países (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Os seguintes regulamentos requerem upload manual da versão mais recente:",
        "crossexam.upload_reminder_instruction": "Eira: Por favor utilize a função 'Carregar documento regulatório' para carregar os documentos mais recentes.",
        "crossexam.pipeline_running": "Eira: 📊 Progresso da análise: [{bar}] {completed}/{total} ({percent}%) — Fase atual: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Análise concluída. Total: {total} itens analisados.",
        "crossexam.pipeline_not_started": "Eira: ⏳ A análise ainda não foi iniciada. Por favor execute primeiro 'Lista regulatória' ou 'Atualização regulatória'.",
    },
    "it-IT": {
        "crossexam.freshness_confirmed": "Eira: ✅ Tutti i riferimenti normativi confermati come versione più recente.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Interrogatorio incrociato MDSAP 5 paesi attivato. Questa analisi includerà l'interrogatorio incrociato di 7 paesi e l'analisi MDSAP di 5 paesi (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Le seguenti normative richiedono il caricamento manuale dell'ultima versione:",
        "crossexam.upload_reminder_instruction": "Eira: Si prega di utilizzare la funzione 'Carica documento normativo' per caricare i documenti più recenti.",
        "crossexam.pipeline_running": "Eira: 📊 Progresso analisi: [{bar}] {completed}/{total} ({percent}%) — Fase attuale: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analisi completata. Totale: {total} elementi analizzati.",
        "crossexam.pipeline_not_started": "Eira: ⏳ L'analisi non è ancora iniziata. Si prega di eseguire prima 'Lista normativa' o 'Aggiornamento normativo'.",
    },
    "ru-RU": {
        "crossexam.freshness_confirmed": "Eira: ✅ Все нормативные ссылки подтверждены как актуальная версия.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Перекрёстный допрос MDSAP по 5 странам активирован. Этот анализ будет включать перекрёстный допрос по 7 странам и анализ MDSAP по 5 странам (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Следующие нормативные акты требуют ручной загрузки последней версии:",
        "crossexam.upload_reminder_instruction": "Eira: Пожалуйста, используйте функцию 'Загрузить нормативный документ' для загрузки последних документов.",
        "crossexam.pipeline_running": "Eira: 📊 Прогресс анализа: [{bar}] {completed}/{total} ({percent}%) — Текущая фаза: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Анализ завершён. Всего: {total} проанализированных элементов.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Анализ ещё не начат. Пожалуйста, сначала выполните 'Список нормативов' или 'Обновление нормативов'.",
    },
    "ar-SA": {
        "crossexam.freshness_confirmed": "Eira: ✅ تم تأكيد جميع المراجع التنظيمية كأحدث إصدار.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 تم تفعيل الاستجواب المتقاطع MDSAP لـ 5 دول. سيشمل هذا التحليل الاستجواب المتقاطع لـ 7 دول وتحليل MDSAP لـ 5 دول (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 اللوائح التالية تتطلب رفع يدوي لأحدث إصدار:",
        "crossexam.upload_reminder_instruction": "Eira: يرجى استخدام وظيفة 'رفع مستند تنظيمي' لرفع أحدث المستندات.",
        "crossexam.pipeline_running": "Eira: 📊 تقدم التحليل: [{bar}] {completed}/{total} ({percent}%) — المرحلة الحالية: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ اكتمل التحليل. الإجمالي: {total} عنصر تم تحليله.",
        "crossexam.pipeline_not_started": "Eira: ⏳ لم يبدأ التحليل بعد. يرجى تنفيذ 'قائمة اللوائح' أو 'تحديث اللوائح' أولاً.",
    },
    "hi-IN": {
        "crossexam.freshness_confirmed": "Eira: ✅ सभी नियामक संदर्भ नवीनतम संस्करण के रूप में पुष्टि किए गए।",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 MDSAP 5-देश क्रॉस-एग्जामिनेशन सक्रिय। इस विश्लेषण में 7-देश क्रॉस-एग्जामिनेशन और MDSAP 5-देश (HC/PMDA/ANVISA/TGA/QMSR) विश्लेषण शामिल होगा।",
        "crossexam.upload_reminder_title": "Eira: 📋 निम्नलिखित नियमों के नवीनतम संस्करण का मैनुअल अपलोड आवश्यक है:",
        "crossexam.upload_reminder_instruction": "Eira: कृपया संबंधित देशों के नवीनतम नियामक दस्तावेज़ अपलोड करने के लिए 'नियामक दस्तावेज़ अपलोड' फ़ंक्शन का उपयोग करें।",
        "crossexam.pipeline_running": "Eira: 📊 विश्लेषण प्रगति: [{bar}] {completed}/{total} ({percent}%) — वर्तमान चरण: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ विश्लेषण पूर्ण। कुल: {total} आइटम विश्लेषित।",
        "crossexam.pipeline_not_started": "Eira: ⏳ विश्लेषण अभी शुरू नहीं हुआ है। कृपया पहले 'नियामक सूची' या 'नियामक अपडेट' चलाएं।",
    },
    "th-TH": {
        "crossexam.freshness_confirmed": "Eira: ✅ การอ้างอิงกฎระเบียบทั้งหมดได้รับการยืนยันว่าเป็นเวอร์ชันล่าสุด",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 เปิดใช้งานการตรวจสอบไขว้ MDSAP 5 ประเทศแล้ว การวิเคราะห์นี้จะรวมการตรวจสอบไขว้ 7 ประเทศและการวิเคราะห์ MDSAP 5 ประเทศ (HC/PMDA/ANVISA/TGA/QMSR)",
        "crossexam.upload_reminder_title": "Eira: 📋 กฎระเบียบต่อไปนี้ต้องการการอัปโหลดเวอร์ชันล่าสุดด้วยตนเอง:",
        "crossexam.upload_reminder_instruction": "Eira: กรุณาใช้ฟังก์ชัน 'อัปโหลดเอกสารกฎระเบียบ' เพื่ออัปโหลดเอกสารล่าสุด",
        "crossexam.pipeline_running": "Eira: 📊 ความคืบหน้าการวิเคราะห์: [{bar}] {completed}/{total} ({percent}%) — ขั้นตอนปัจจุบัน: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ การวิเคราะห์เสร็จสมบูรณ์ ทั้งหมด: {total} รายการที่วิเคราะห์",
        "crossexam.pipeline_not_started": "Eira: ⏳ การวิเคราะห์ยังไม่เริ่มต้น กรุณาเรียกใช้ 'รายการกฎระเบียบ' หรือ 'อัปเดตกฎระเบียบ' ก่อน",
    },
    "vi-VN": {
        "crossexam.freshness_confirmed": "Eira: ✅ Tất cả tham chiếu quy định đã được xác nhận là phiên bản mới nhất.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Đã kích hoạt kiểm tra chéo MDSAP 5 quốc gia. Phân tích này sẽ bao gồm kiểm tra chéo 7 quốc gia và phân tích MDSAP 5 quốc gia (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Các quy định sau yêu cầu tải lên thủ công phiên bản mới nhất:",
        "crossexam.upload_reminder_instruction": "Eira: Vui lòng sử dụng chức năng 'Tải lên tài liệu quy định' để tải lên các tài liệu mới nhất.",
        "crossexam.pipeline_running": "Eira: 📊 Tiến độ phân tích: [{bar}] {completed}/{total} ({percent}%) — Giai đoạn hiện tại: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Phân tích hoàn tất. Tổng cộng: {total} mục đã phân tích.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Phân tích chưa bắt đầu. Vui lòng chạy 'Danh sách quy định' hoặc 'Cập nhật quy định' trước.",
    },
    "id-ID": {
        "crossexam.freshness_confirmed": "Eira: ✅ Semua referensi regulasi telah dikonfirmasi sebagai versi terbaru.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Pemeriksaan silang MDSAP 5 negara diaktifkan. Analisis ini akan mencakup pemeriksaan silang 7 negara dan analisis MDSAP 5 negara (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Regulasi berikut memerlukan unggahan manual versi terbaru:",
        "crossexam.upload_reminder_instruction": "Eira: Silakan gunakan fungsi 'Unggah Dokumen Regulasi' untuk mengunggah dokumen terbaru.",
        "crossexam.pipeline_running": "Eira: 📊 Kemajuan analisis: [{bar}] {completed}/{total} ({percent}%) — Fase saat ini: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analisis selesai. Total: {total} item dianalisis.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Analisis belum dimulai. Silakan jalankan 'Daftar Regulasi' atau 'Pembaruan Regulasi' terlebih dahulu.",
    },
    "ms-MY": {
        "crossexam.freshness_confirmed": "Eira: ✅ Semua rujukan peraturan disahkan sebagai versi terkini.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Pemeriksaan silang MDSAP 5 negara diaktifkan. Analisis ini akan merangkumi pemeriksaan silang 7 negara dan analisis MDSAP 5 negara (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Peraturan berikut memerlukan muat naik manual versi terkini:",
        "crossexam.upload_reminder_instruction": "Eira: Sila gunakan fungsi 'Muat Naik Dokumen Peraturan' untuk memuat naik dokumen terkini.",
        "crossexam.pipeline_running": "Eira: 📊 Kemajuan analisis: [{bar}] {completed}/{total} ({percent}%) — Fasa semasa: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analisis selesai. Jumlah: {total} item dianalisis.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Analisis belum bermula. Sila jalankan 'Senarai Peraturan' atau 'Kemas Kini Peraturan' terlebih dahulu.",
    },
    "tr-TR": {
        "crossexam.freshness_confirmed": "Eira: ✅ Tüm düzenleyici referanslar en güncel sürüm olarak doğrulandı.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 MDSAP 5 ülke çapraz sorgulaması etkinleştirildi. Bu analiz hem 7 ülke çapraz sorgulamasını hem de MDSAP 5 ülke (HC/PMDA/ANVISA/TGA/QMSR) analizini içerecektir.",
        "crossexam.upload_reminder_title": "Eira: 📋 Aşağıdaki düzenlemeler en son sürümün manuel yüklenmesini gerektirmektedir:",
        "crossexam.upload_reminder_instruction": "Eira: Lütfen en güncel belgeleri yüklemek için 'Düzenleyici Belge Yükle' işlevini kullanın.",
        "crossexam.pipeline_running": "Eira: 📊 Analiz ilerlemesi: [{bar}] {completed}/{total} ({percent}%) — Mevcut aşama: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analiz tamamlandı. Toplam: {total} öğe analiz edildi.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Analiz henüz başlamadı. Lütfen önce 'Düzenleme Listesi' veya 'Düzenleme Güncellemesi' çalıştırın.",
    },
    "nl-NL": {
        "crossexam.freshness_confirmed": "Eira: ✅ Alle regelgevingsreferenties bevestigd als nieuwste versie.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 MDSAP 5-landen kruisverhoor geactiveerd. Deze analyse omvat zowel het 7-landen kruisverhoor als de MDSAP 5-landen (HC/PMDA/ANVISA/TGA/QMSR) analyse.",
        "crossexam.upload_reminder_title": "Eira: 📋 De volgende regelgeving vereist handmatige upload van de nieuwste versie:",
        "crossexam.upload_reminder_instruction": "Eira: Gebruik de functie 'Regelgevingsdocument uploaden' om de nieuwste documenten te uploaden.",
        "crossexam.pipeline_running": "Eira: 📊 Analysevoortgang: [{bar}] {completed}/{total} ({percent}%) — Huidige fase: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analyse voltooid. Totaal: {total} items geanalyseerd.",
        "crossexam.pipeline_not_started": "Eira: ⏳ De analyse is nog niet gestart. Voer eerst 'Regelgevingslijst' of 'Regelgevingsupdate' uit.",
    },
    "pl-PL": {
        "crossexam.freshness_confirmed": "Eira: ✅ Wszystkie odniesienia regulacyjne potwierdzone jako najnowsza wersja.",
        "crossexam.mdsap_enabled_notice": "Eira: 🌐 Przesłuchanie krzyżowe MDSAP 5 krajów aktywowane. Ta analiza obejmie przesłuchanie krzyżowe 7 krajów oraz analizę MDSAP 5 krajów (HC/PMDA/ANVISA/TGA/QMSR).",
        "crossexam.upload_reminder_title": "Eira: 📋 Następujące przepisy wymagają ręcznego przesłania najnowszej wersji:",
        "crossexam.upload_reminder_instruction": "Eira: Proszę użyć funkcji 'Prześlij dokument regulacyjny' aby przesłać najnowsze dokumenty.",
        "crossexam.pipeline_running": "Eira: 📊 Postęp analizy: [{bar}] {completed}/{total} ({percent}%) — Bieżąca faza: {phase}",
        "crossexam.pipeline_completed": "Eira: ✅ Analiza zakończona. Łącznie: {total} przeanalizowanych elementów.",
        "crossexam.pipeline_not_started": "Eira: ⏳ Analiza jeszcze się nie rozpoczęła. Proszę najpierw uruchomić 'Listę przepisów' lub 'Aktualizację przepisów'.",
    },
}


def main():
    updated = 0
    for json_path in sorted(LOCALES_DIR.glob("*.json")):
        lang = json_path.stem
        if lang not in KEYS:
            print(f"SKIP: {lang} — no translations defined")
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))

        # Remove old incorrect keys (without Eira prefix) if they exist
        changed = False
        for key, value in KEYS[lang].items():
            if key not in data or data[key] != value:
                data[key] = value
                changed = True

        if changed:
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            updated += 1
            print(f"UPDATED: {lang}")
        else:
            print(f"OK: {lang} — already correct")

    print(f"\nDone. Updated {updated} files.")


if __name__ == "__main__":
    main()
